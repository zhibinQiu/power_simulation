"""AI 优化模型引擎：遗传算法（GA）/ 粒子群（PSO）/ 强化学习（RL，简化在线策略梯度）。

产品语义（数据驱动、后台定时训练、模型逐渐变优）：
1. 优化空间 = 当前流程模型中所有「可优化参数」（PARAM_SCHEMA kind='optim'）。
2. 适应度   = 全厂吨钢碳强度（kgCO₂/t，越小越好），由 cached_simulate 计算；
   实时传感器读数（DEVICE_HISTORY）对目标做小幅工况调制（负荷系数），
   使优化方向随现场实时数据漂移 —— 体现「数据驱动、越训越贴近现场」。
3. 三种模型共用同一套接口：setup / step / reset / set_hyper / apply / state。
4. 后台调度线程（TrainingScheduler）按各模型的自训练设置调度：
   频率（interval，秒）与可选训练时段（window，HH:MM-HH:MM）；
   训练样本量（samples）= 传感器累计采集点数，随实时数据持续增长。
5. 模型版本管理：只有新模型的评估指标（吨钢碳强度）优于当前版本时才
   自动替换为新版本；历史版本全部保留，可随时切换 / 手动存档 / 应用。
6. 控制模式：
   - 自动化控制（auto_control）：模型变优后自动把新版本参数下发到可调设备；
   - 手动模式：训练取得进展时生成系统提醒（reminder），引导用户手动调优。
7. 训练轨迹、超参数、最优参数建议、版本列表、提醒经 REST 暴露，前端轮询渲染，
   形成「实时数据采集 → 后台定时训练 → 模型逐渐变优 → 应用/控制」的闭环。
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from .carbon_engine import DEFAULT_PARAMS, cached_simulate
from .models import ProcessModel
from .param_schema import PARAM_SCHEMA
from .realtime import DEVICE_HISTORY

TRAIN_INTERVAL = 2.0   # 调度线程唤醒周期（秒）：按各模型的训练频率/时段分发迭代
HISTORY_KEEP = 240     # 每模型保留的最大训练轨迹点数（超出抽稀）
ARCHIVE_GAIN = 0.05    # 版本自动存档的最小相对提升（%）：只有更优才替换为新版本
ARCHIVE_MIN_ITER_GAP = 8  # 自动存档最小迭代间隔：避免连续迭代产生过密版本
REMINDER_GAIN = 0.3    # 手动模式提醒阈值（%）：相对提升超过该值生成系统提醒


def _time_in_window(cur: str, start: str, end: str) -> bool:
    """判断当前 "HH:MM" 是否落在 [start, end] 时段内（支持跨午夜，如 22:00-06:00）。"""
    if start <= end:
        return start <= cur <= end
    return cur >= start or cur <= end


# ============================ 实时数据与目标函数 ============================

def _sensor_samples() -> int:
    """当前传感器累计采集点数（实时数据流量的度量，驱动训练样本量展示）。"""
    return sum(len(b) for b in DEVICE_HISTORY.values())


def _live_load_factor() -> float:
    """由最近 2 分钟传感器读数计算工况负荷系数（≈1.0，±4%）。

    把实时现场数据耦合进训练目标：传感器显示负荷上升时，同一组参数下
    单位碳强度目标会轻微变差，优化器随之调整方向 —— 体现「数据驱动、越训越准」。
    """
    n = 0
    s = 0.0
    tnow = time.time()
    for buf in DEVICE_HISTORY.values():
        if not buf:
            continue
        recent = [p["v"] for p in buf if tnow - p["t"] < 120]
        if len(recent) < 3:
            recent = [p["v"] for p in buf[-30:]]
        base_win = buf[-30:]
        if not recent or not base_win:
            continue
        base = sum(p["v"] for p in base_win) / len(base_win)
        if base <= 1e-9:
            continue
        cur = sum(recent) / len(recent)
        s += cur / base
        n += 1
    if n == 0:
        return 1.0
    return min(max(1.0 + 0.06 * (s / n - 1.0), 0.96), 1.04)


def _optim_space(model: ProcessModel) -> List[Dict[str, Any]]:
    """从当前流程模型提取可优化参数空间（kind='optim'）。"""
    space: List[Dict[str, Any]] = []
    for u in model.units:
        if not u.enabled:
            continue
        for p in PARAM_SCHEMA.get(u.type, []) or []:
            if p.get("kind") != "optim":
                continue
            key = p["key"]
            lo, hi = float(p.get("min", 0.0)), float(p.get("max", 1.0))
            if hi <= lo:
                hi = lo + 1e-6
            init = (u.params or {}).get(key)
            if init is None:
                init = (DEFAULT_PARAMS.get(u.type, {}) or {}).get(key)
            if init is None:
                init = (lo + hi) / 2.0
            init = min(max(float(init), lo), hi)
            space.append({
                "unit_id": u.id, "unit_type": u.type, "unit_name": u.name,
                "key": key, "label": p.get("label", key), "unit": p.get("unit", ""),
                "lo": lo, "hi": hi, "init": init,
            })
    return space


class _Workspace:
    """可变的仿真工作区：共享结构、独立参数 dict，避免每候选全量深拷贝。"""

    def __init__(self, model: ProcessModel):
        self.model = ProcessModel(**model.model_dump())
        self.by_id = {u.id: u for u in self.model.units}


# ============================ 优化器基类 ============================

class OptimizerBase:
    """优化器基类：状态 / 历史 / 日志 / 超参管理 + 评估内核。"""

    kind = "base"

    def __init__(self, oid: str, name: str, tagline: str, hyper_schema: Dict):
        self.id = oid
        self.name = name
        self.tagline = tagline
        self.hyper_schema = hyper_schema
        self.hyperparams: Dict[str, float] = {
            k: float(v["default"]) for k, v in hyper_schema.items()
        }
        self._lock = threading.RLock()
        self._ws: Optional[_Workspace] = None
        self._factors: Optional[Dict] = None
        self.space: List[Dict[str, Any]] = []
        self.running = False
        self.iteration = 0
        self.samples = 0
        self.samples_prev = 0
        self.start_fitness = 0.0
        self.best_fitness = 0.0
        self.best_values: List[float] = []
        self.history: List[Dict[str, float]] = []
        self.logs: List[str] = []
        self.archived: Dict[str, Any] = {}
        self.trained_at: Optional[float] = None
        self.error = ""
        # ---- 控制与训练设置 ----
        self.auto_control = False          # 自动化控制：变优后自动下发参数到可调设备
        self.schedule: Dict[str, Any] = {  # 自训练设置：频率（秒）+ 可选时段 HH:MM-HH:MM
            "interval": 30,
            "window": None,
        }
        self.next_train_at = 0.0           # 调度线程下一次可训练的时间戳
        # ---- 模型版本管理 ----
        self._fp: Optional[str] = None     # 当前训练上下文指纹
        self.versions: List[Dict[str, Any]] = []   # 历史版本（旧版本保留，可切换）
        self.active_version: Optional[str] = None  # 当前生效版本 id
        self.pending_auto_apply = False    # 自动化控制待下发标记（新版本已就绪）
        self.reminder: Optional[Dict[str, Any]] = None  # 手动调优系统提醒
        self._last_reminded: Optional[float] = None    # 上次提醒时的强度（提醒基线）

    # ---------- 状态 ----------
    @property
    def ready(self) -> bool:
        return self._ws is not None and bool(self.space)

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{ts}] {msg}")
        if len(self.logs) > 16:
            self.logs = self.logs[-16:]

    # ---------- 评估内核 ----------
    def _fitness(self, values: List[float]) -> float:
        """把归一化 values 写入工作区参数并仿真，返回调制后碳强度（越小越好）。"""
        ws = self._ws
        for p, v in zip(self.space, values):
            u = ws.by_id.get(p["unit_id"])
            if u is None:
                continue
            u.params[p["key"]] = p["lo"] + (p["hi"] - p["lo"]) * min(1.0, max(0.0, v))
        try:
            r = cached_simulate(ws.model, self._factors)
            fit = float(r.totals.intensity)
        except Exception:
            fit = 1e6
        if not math.isfinite(fit) or fit <= 0:
            fit = 1e6
        return fit * _live_load_factor()

    def _phys(self, values: List[float]) -> List[float]:
        return [p["lo"] + (p["hi"] - p["lo"]) * min(1.0, max(0.0, v))
                for p, v in zip(self.space, values)]

    # ---------- 生命周期 ----------
    def setup(self, model: ProcessModel, factors: Optional[Dict] = None):
        """用新的流程模型重建训练任务（保留 archived 最佳记录用于跨模型对比）。"""
        with self._lock:
            if self._ws is not None and self.iteration > 0 and self.best_fitness > 0:
                self.archived = {
                    "iteration": self.iteration,
                    "best_fitness": round(self.best_fitness, 2),
                    "samples": self.samples,
                }
            self._ws = _Workspace(model)
            self._factors = factors
            self._fp = _model_fp(model)
            self.space = _optim_space(model)
            self.iteration = 0
            self.history = []
            self.running = False
            self.error = ""
            self.reminder = None
            self.pending_auto_apply = False
            self.next_train_at = 0.0
            self.samples = _sensor_samples()
            self.samples_prev = self.samples
            if not self.space:
                self._log("当前流程无可优化参数（kind=optim），请先在流程编排中添加")
                return
            init_values = [(p["init"] - p["lo"]) / (p["hi"] - p["lo"]) for p in self.space]
            try:
                self.start_fitness = self._fitness(init_values)
            except Exception as e:  # pragma: no cover
                self.start_fitness = 0.0
                self.error = str(e)
            self.best_fitness = self.start_fitness
            self.best_values = list(init_values)
            self._last_reminded = self.start_fitness
            self.history.append({"iter": 0, "best": round(self.start_fitness, 2),
                                 "avg": round(self.start_fitness, 2)})
            self._init_search()
            if self.archived:
                self._log(f"流程模型已变更，训练重建（上一轮最优 {self.archived['best_fitness']} kgCO₂/t）")
            else:
                self._log(f"模型就绪：{len(self.space)} 个优化参数，初始强度 {self.start_fitness:.1f} kgCO₂/t")

    def _init_search(self):
        """子类覆写：初始化搜索结构（种群 / 粒子 / 策略均值）。"""
        pass

    def reset(self):
        with self._lock:
            model = self._ws.model if self._ws is not None else None
            factors = self._factors
            self.archived = {}
            self.history = []
            self.iteration = 0
            self.running = False
            self.reminder = None
            self.pending_auto_apply = False
            if model is not None:
                self.setup(model, factors)
            self._log("模型已重置（历史版本保留）")

    def set_hyper(self, patch: Dict[str, float]) -> Dict[str, float]:
        with self._lock:
            for k, v in patch.items():
                if k in self.hyperparams:
                    s = self.hyper_schema[k]
                    self.hyperparams[k] = float(min(max(float(v), s["min"]), s["max"]))
        return dict(self.hyperparams)

    # ---------- 训练 ----------
    def step(self):
        """执行一步训练（子类实现 _train_once），由调度线程或手动触发。"""
        with self._lock:
            if not self.ready:
                return
            try:
                best, avg = self._train_once()
            except Exception as e:
                self.error = str(e)
                self.running = False
                self._log(f"训练出错：{e}")
                return
            self.iteration += 1
            self.trained_at = time.time()
            if best < self.best_fitness - 1e-9:
                self.best_fitness = best
                self.best_values = self._current_best()
            # 累计最优曲线：单调递减，直观呈现「逐渐变优」
            self.history.append({
                "iter": self.iteration,
                "best": round(self.best_fitness, 2),
                "avg": round(avg, 2),
            })
            if len(self.history) > HISTORY_KEEP:
                self.history = self.history[::2]
            # 样本计数随实时数据增长
            self.samples = _sensor_samples()
            gain = self.samples - self.samples_prev
            self.samples_prev = self.samples
            improvement = (self.start_fitness - self.best_fitness) / max(self.start_fitness, 1e-9) * 100
            # ---- 版本管理与控制模式 ----
            # 比较基线：同上下文下当前版本的最优强度；无版本/上下文已变则回到初始强度
            active = self._active_fp_version()
            baseline = active["best_fitness"] if active else self.start_fitness
            if baseline > 0:
                gain_vs_active = (baseline - self.best_fitness) / baseline * 100
            else:
                gain_vs_active = 0.0
            # 只有评估指标（碳强度）超过当前版本、且距上一版本达到最小迭代间隔，
            # 才自动存档并替换为新版本（避免迭代初期版本过密）
            last_ver = self.versions[-1] if self.versions else None
            gap_ok = last_ver is None or (self.iteration - last_ver["iteration"]) >= ARCHIVE_MIN_ITER_GAP
            if gap_ok and self.best_fitness < baseline - 1e-9 and gain_vs_active >= ARCHIVE_GAIN:
                try:
                    self.archive(force=False)
                except Exception:  # pragma: no cover
                    pass
            if self.auto_control:
                self.reminder = None
            else:
                reminded_base = self._last_reminded if self._last_reminded else self.start_fitness
                if reminded_base > 0:
                    rg = (reminded_base - self.best_fitness) / reminded_base * 100
                    if rg >= REMINDER_GAIN:
                        self.reminder = {
                            "id": f"r{self.iteration}_{int(time.time())}",
                            "best_fitness": round(self.best_fitness, 2),
                            "improvement_pct": round(rg, 2),
                            "iteration": self.iteration,
                            "ts": time.time(),
                        }
                        self._last_reminded = self.best_fitness
                        self._log(f"训练取得进展：最优强度 {self.best_fitness:.2f} kgCO₂/t（提升 {rg:.1f}%），已生成手动调优提醒")
            if self.iteration == 1:
                self._log("训练开始：目标为最小化吨钢碳强度（随实时传感器数据持续优化）")
            if self.iteration % 8 == 0 or gain >= 200:
                msg = f"迭代 #{self.iteration}：最优强度 {self.best_fitness:.2f} kgCO₂/t（较初始 {improvement:.2f}%）"
                if gain > 0:
                    msg += f" · 传感器样本 +{gain}"
                self._log(msg)

    def _train_once(self) -> tuple:
        raise NotImplementedError

    def _current_best(self) -> List[float]:
        return list(self.best_values)

    # ---------- 应用 ----------
    def apply(self):
        """把「当前生效版本」的最优参数写入流程模型副本，返回 (model, sim)。

        存在版本时以所选版本为准（可切换任意历史版本后应用）；
        无版本时使用实时最优参数。
        """
        with self._lock:
            if not self.ready or not self.best_values:
                raise RuntimeError("模型尚未训练，无可应用的优化参数")
            m2 = ProcessModel(**self._ws.model.model_dump())
            rec = self._active_fp_version()
            if rec is not None:
                valmap = {(p["unit_id"], p["key"]): p["value"] for p in rec.get("params", [])}
                for p in self.space:
                    v = valmap.get((p["unit_id"], p["key"]))
                    if v is None:
                        continue
                    u = next((u for u in m2.units if u.id == p["unit_id"]), None)
                    if u is None:
                        continue
                    u.params[p["key"]] = v
                self._log(f"已按版本 {rec['id']} 的参数下发到流程（最优 {rec['best_fitness']} kgCO₂/t）")
            else:
                for p, v in zip(self.space, self.best_values):
                    u = next((u for u in m2.units if u.id == p["unit_id"]), None)
                    if u is None:
                        continue
                    u.params[p["key"]] = p["lo"] + (p["hi"] - p["lo"]) * min(1.0, max(0.0, v))
                self._log("已按实时最优参数下发到流程")
            sim = cached_simulate(m2, self._factors)
            return m2, sim

    # ---------- 版本管理 ----------
    def _snapshot_params(self, values_phys: List[float]) -> List[Dict[str, Any]]:
        return [
            {
                "unit_id": p["unit_id"], "unit_label": p["unit_name"],
                "unit_type": p["unit_type"],
                "key": p["key"], "label": p["label"], "unit": p["unit"],
                "value": round(pv, 3), "initial": round(p["init"], 3),
                "delta": round(pv - p["init"], 3),
            }
            for p, pv in zip(self.space, values_phys)
        ]

    def _active_fp_version(self) -> Optional[Dict[str, Any]]:
        """当前生效且与训练上下文同源的版本（跨上下文的历史版本仅作浏览/切换）。"""
        for v in reversed(self.versions):
            if v.get("active") and v.get("fp") == self._fp:
                return v
        return None

    def _make_version(self, promoted: bool) -> Dict[str, Any]:
        n = len(self.versions) + 1
        imp = ((self.start_fitness - self.best_fitness)
               / max(self.start_fitness, 1e-9) * 100) if self.start_fitness > 0 else 0.0
        return {
            "id": f"v{n}",
            "fp": self._fp,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "iteration": self.iteration,
            "samples": self.samples,
            "best_fitness": round(self.best_fitness, 2),
            "improvement_pct": round(imp, 2),
            "active": promoted,
            "params": self._snapshot_params(self._phys(self.best_values)),
        }

    def archive(self, force: bool = False) -> Dict[str, Any]:
        """把当前最优参数保存为版本。

        只有评估指标优于当前版本（同上下文）时才会替换为新版本并生效；
        未超过时仍可手动保存为候选版本（不替换）。旧版本一律保留。
        """
        with self._lock:
            if not self.ready or self.iteration <= 0 or not self.best_values:
                raise RuntimeError("模型尚未训练，无法保存版本")
            active = self._active_fp_version()
            baseline = active["best_fitness"] if active else self.start_fitness
            improved = self.best_fitness < baseline - 1e-9
            if not force and not improved:
                return {"ok": False, "promoted": False, "version": None}
            promoted = improved   # 只有评估指标超过当前版本才替换为新版本
            ver = self._make_version(promoted)
            if promoted:
                for v in self.versions:
                    v["active"] = False
                self.versions.append(ver)
                self.active_version = ver["id"]
                if self.auto_control:
                    self.pending_auto_apply = True
                self._log(f"模型升级：新版本 {ver['id']} 替换为当前版本（最优 {ver['best_fitness']} kgCO₂/t，提升 {ver['improvement_pct']:.2f}%）")
            else:
                self.versions.append(ver)
                self._log(f"已保存候选版本 {ver['id']}（最优 {ver['best_fitness']} kgCO₂/t，未超过当前版本，不替换）")
            return {"ok": True, "promoted": promoted, "version": ver}

    def switch_version(self, version_id: str):
        with self._lock:
            v = next((x for x in self.versions if x["id"] == version_id), None)
            if v is None:
                raise ValueError("版本不存在")
            for x in self.versions:
                x["active"] = False
            v["active"] = True
            self.active_version = version_id
            self._log(f"已切换为版本 {version_id}（最优 {v['best_fitness']} kgCO₂/t）")

    def ack(self):
        """确认提醒：清除手动调优提醒 / 自动控制待下发标记。"""
        with self._lock:
            self.reminder = None
            self.pending_auto_apply = False
            self._last_reminded = self.best_fitness

    # ---------- 控制与训练设置 ----------
    def in_window(self) -> bool:
        w = self.schedule.get("window")
        if not w:
            return True
        try:
            return _time_in_window(datetime.now().strftime("%H:%M"), w["start"], w["end"])
        except Exception:  # pragma: no cover
            return True

    def set_settings(self, patch: Dict[str, Any]):
        with self._lock:
            if "auto_control" in patch:
                self.auto_control = bool(patch["auto_control"])
                if self.auto_control:
                    self.reminder = None
                    self._log("已开启自动化控制：模型变优后自动把新版本参数下发到可调设备")
                else:
                    self._last_reminded = self.best_fitness or self.start_fitness
                    self._log("已关闭自动化控制：改为系统提醒手动调优")
            if "schedule" in patch:
                sc = patch["schedule"] or {}
                if "interval" in sc and sc["interval"] is not None:
                    self.schedule["interval"] = min(max(int(sc["interval"]), 5), 3600)
                w = sc.get("window")
                if w and w.get("start") and w.get("end"):
                    self.schedule["window"] = {"start": str(w["start"]), "end": str(w["end"])}
                else:
                    self.schedule["window"] = None
                self.next_train_at = 0.0
                window_desc = ""
                if self.schedule["window"]:
                    window_desc = f" · 训练时段 {self.schedule['window']['start']}-{self.schedule['window']['end']}"
                self._log(f"自训练设置已更新：每 {self.schedule['interval']} 秒{window_desc}")

    # ---------- 状态输出 ----------
    def state(self, full: bool = False) -> Dict[str, Any]:
        with self._lock:
            phys = self._phys(self.best_values) if self.best_values else []
            improvement = ((self.start_fitness - self.best_fitness)
                           / max(self.start_fitness, 1e-9) * 100) if self.start_fitness > 0 else 0.0
            hist = self.history
            if len(hist) > 200 and not full:
                step = max(1, len(hist) // 200)
                hist = [hist[i] for i in range(0, len(hist), step)][-200:]
            rec = self._active_fp_version()
            return {
                "id": self.id,
                "name": self.name,
                "kind": self.kind,
                "tagline": self.tagline,
                "running": self.running,
                "ready": self.ready,
                "iteration": self.iteration,
                "samples": self.samples,
                "start_fitness": round(self.start_fitness, 2),
                "best_fitness": round(self.best_fitness, 2),
                "improvement_pct": round(improvement, 2),
                "history": hist[-200:] if not full else hist,
                "hyperparams": {k: round(float(v), 4) for k, v in self.hyperparams.items()},
                "hyper_schema": self.hyper_schema,
                "best_params": [
                    {
                        "unit_id": p["unit_id"], "unit_label": p["unit_name"],
                        "unit_type": p["unit_type"],
                        "key": p["key"], "label": p["label"], "unit": p["unit"],
                        "value": round(pv, 3), "initial": round(p["init"], 3),
                        "delta": round(pv - p["init"], 3),
                    }
                    for p, pv in zip(self.space, phys)
                ],
                "archived": self.archived,
                "logs": list(self.logs),
                "trained_at": self.trained_at,
                "error": self.error,
                # 控制与训练设置
                "auto_control": self.auto_control,
                "schedule": {
                    "interval": self.schedule["interval"],
                    "window": dict(self.schedule["window"]) if self.schedule["window"] else None,
                },
                "in_window": self.in_window(),
                # 版本管理与提醒
                "versions": list(self.versions),
                "active_version": self.active_version,
                "pending_auto_apply": self.pending_auto_apply,
                "reminder": self.reminder,
                "recommended": {
                    "version_id": rec["id"],
                    "iteration": rec["iteration"],
                    "best_fitness": rec["best_fitness"],
                    "improvement_pct": rec["improvement_pct"],
                    "params": rec["params"],
                } if rec else None,
            }


# ============================ 遗传算法（GA） ============================

GA_HYPER: Dict[str, Dict] = {
    "pop_size":   {"label": "种群规模",   "min": 4,  "max": 60, "step": 2,  "default": 16},
    "generations":{"label": "每轮代数",   "min": 1,  "max": 10, "step": 1,  "default": 2},
    "crossover":  {"label": "交叉概率",   "min": 0.1, "max": 1.0, "step": 0.05, "default": 0.8},
    "mutation":   {"label": "变异概率",   "min": 0.01,"max": 0.6, "step": 0.01, "default": 0.12},
    "elite":      {"label": "精英保留数", "min": 1,  "max": 8,  "step": 1,  "default": 2},
}


class GeneticOptimizer(OptimizerBase):
    """遗传算法：锦标赛选择 + 单点交叉 + 高斯变异 + 精英保留，全局搜索最低碳排配置。"""

    kind = "ga"

    def _init_search(self):
        d = len(self.space)
        n = int(self.hyperparams["pop_size"])
        self._pop = [([random.random() for _ in range(d)], self._fitness([random.random() for _ in range(d)]))
                     for _ in range(n)]
        self._pop_best = list(min(self._pop, key=lambda t: t[1])[0])

    def _train_once(self):
        pop_size = int(self.hyperparams["pop_size"])
        gens = int(self.hyperparams["generations"])
        cr = float(self.hyperparams["crossover"])
        mr = float(self.hyperparams["mutation"])
        elite = max(1, int(self.hyperparams["elite"]))
        for _ in range(gens):
            self._pop.sort(key=lambda t: t[1])
            newpop = self._pop[:elite]
            while len(newpop) < pop_size:
                a = min(random.sample(self._pop, min(3, len(self._pop))), key=lambda t: t[1])
                b = min(random.sample(self._pop, min(3, len(self._pop))), key=lambda t: t[1])
                c = self._cross(a[0], b[0], cr)
                c = [min(1.0, max(0.0, v + random.gauss(0, 0.08)))
                     if random.random() < mr else v for v in c]
                newpop.append((c, self._fitness(c)))
            self._pop = newpop
        self._pop.sort(key=lambda t: t[1])
        self._pop_best = list(self._pop[0][0])
        best = self._pop[0][1]
        avg = sum(f for _, f in self._pop) / len(self._pop)
        return best, avg

    @staticmethod
    def _cross(a: List[float], b: List[float], cr: float) -> List[float]:
        if random.random() > cr or len(a) < 2:
            return list(a)
        cut = random.randint(1, len(a) - 1)
        return a[:cut] + b[cut:]

    def _current_best(self) -> List[float]:
        return list(self._pop_best)


# ============================ 粒子群优化（PSO） ============================

PSO_HYPER: Dict[str, Dict] = {
    "particles": {"label": "粒子数",         "min": 4,  "max": 60,  "step": 2,  "default": 20},
    "inertia":   {"label": "惯性权重 w",     "min": 0.2, "max": 1.2, "step": 0.05, "default": 0.7},
    "c1":        {"label": "个体学习因子 c1", "min": 0.5, "max": 2.5, "step": 0.1, "default": 1.5},
    "c2":        {"label": "群体学习因子 c2", "min": 0.5, "max": 2.5, "step": 0.1, "default": 1.5},
    "clip":      {"label": "单步速度上限",   "min": 0.05,"max": 0.5, "step": 0.05, "default": 0.2},
}


class ParticleSwarmOptimizer(OptimizerBase):
    """粒子群：粒子在参数空间协同飞行，个体最优 + 群体最优牵引，快速收敛。"""

    kind = "pso"

    def _init_search(self):
        n = int(self.hyperparams["particles"])
        d = len(self.space)
        self._xs = [[random.random() for _ in range(d)] for _ in range(n)]
        self._vs = [[random.uniform(-0.05, 0.05) for _ in range(d)] for _ in range(n)]
        self._pbest = [list(x) for x in self._xs]
        self._pbest_f = [self._fitness(x) for x in self._xs]
        bi = min(range(n), key=lambda i: self._pbest_f[i])
        self._gbest = (list(self._pbest[bi]), self._pbest_f[bi])

    def _train_once(self):
        w = float(self.hyperparams["inertia"])
        c1 = float(self.hyperparams["c1"])
        c2 = float(self.hyperparams["c2"])
        clip = float(self.hyperparams["clip"])
        d = len(self.space)
        gvals, gfit = self._gbest
        for i in range(len(self._xs)):
            for j in range(d):
                r1, r2 = random.random(), random.random()
                v = (w * self._vs[i][j]
                     + c1 * r1 * (self._pbest[i][j] - self._xs[i][j])
                     + c2 * r2 * (gvals[j] - self._xs[i][j]))
                self._vs[i][j] = min(max(v, -clip), clip)
            self._xs[i] = [min(1.0, max(0.0, x + vj)) for x, vj in zip(self._xs[i], self._vs[i])]
            f = self._fitness(self._xs[i])
            if f < self._pbest_f[i]:
                self._pbest[i] = list(self._xs[i])
                self._pbest_f[i] = f
            if f < gfit:
                gfit = f
                gvals = list(self._xs[i])
        self._gbest = (gvals, gfit)
        avg = sum(self._pbest_f) / len(self._pbest_f)
        return gfit, avg

    def _current_best(self) -> List[float]:
        return list(self._gbest[0])


# ============================ 强化学习（RL · 简化在线策略梯度） ============================

RL_HYPER: Dict[str, Dict] = {
    "lr":      {"label": "学习率",     "min": 0.005, "max": 0.5, "step": 0.005, "default": 0.06},
    "noise":   {"label": "探索噪声 σ", "min": 0.01,  "max": 0.3, "step": 0.01,  "default": 0.08},
    "samples": {"label": "每次采样数", "min": 2,     "max": 30,  "step": 1,     "default": 8},
    "decay":   {"label": "噪声衰减",   "min": 0.97,  "max": 1.0, "step": 0.001, "default": 0.998},
}


class ReinforcementOptimizer(OptimizerBase):
    """强化学习（简化在线策略梯度 / REINFORCE with baseline）。

    策略 = 参数均值向量 μ；每轮从 N(μ, σ) 采样若干候选参数并评估奖励
    （奖励 = 当前强度 − 候选强度，改善为正），以奖励加权平均更新 μ。
    探索噪声 σ 随衰减系数逐步收缩 → 先探索后利用，随数据积累逐渐收敛到优解。
    """

    kind = "rl"

    def _init_search(self):
        self._mu = [(p["init"] - p["lo"]) / (p["hi"] - p["lo"]) for p in self.space]
        self._mu_best = list(self._mu)

    def _train_once(self):
        lr = float(self.hyperparams["lr"])
        sigma = float(self.hyperparams["noise"]) * float(self.hyperparams["decay"]) ** self.iteration
        n = int(self.hyperparams["samples"])
        d = len(self.space)
        mu = self._mu
        base_f = self._fitness(mu)
        cands = []
        for _ in range(n):
            c = [min(1.0, max(0.0, mu[i] + random.gauss(0, sigma))) for i in range(d)]
            cands.append((c, self._fitness(c)))
        # 奖励 = 强度改善（正为优），基线加权策略更新（REINFORCE with baseline）
        ws = [max(base_f - f, 0.0) for _, f in cands]
        total = sum(ws)
        if total > 1e-12:
            for i in range(d):
                num = sum(w * (c[i] - mu[i]) for (c, _), w in zip(cands, ws))
                mu[i] = min(1.0, max(0.0, mu[i] + lr * num / total))
        self._mu = mu
        best = min(cands, key=lambda t: t[1])
        self._mu_best = list(best[0])
        avg = (base_f + sum(f for _, f in cands)) / (n + 1)
        return best[1], avg

    def _current_best(self) -> List[float]:
        return list(self._mu_best)


# ============================ 注册表与训练上下文 ============================

OPTIMIZERS: Dict[str, OptimizerBase] = {
    "ai::rl": ReinforcementOptimizer(
        "ai::rl",
        "强化学习优化",
        "在线策略梯度：随实时传感器数据持续更新参数策略，先探索后利用，越训越优",
        RL_HYPER,
    ),
    "ai::ga": GeneticOptimizer(
        "ai::ga",
        "遗传算法优化",
        "种群进化寻优：选择/交叉/变异，对关键工艺参数组合做全局搜索",
        GA_HYPER,
    ),
    "ai::pso": ParticleSwarmOptimizer(
        "ai::pso",
        "粒子群优化",
        "群体智能寻优：粒子在参数空间协同飞行，快速逼近最优运行点",
        PSO_HYPER,
    ),
}


def all_optimizers() -> List[OptimizerBase]:
    return list(OPTIMIZERS.values())


def get_optimizer(oid: str) -> Optional[OptimizerBase]:
    return OPTIMIZERS.get(oid)


# 训练上下文（当前流程模型 + 排放因子），由前端在流程变化后同步
_CTX_LOCK = threading.RLock()
_CTX: Dict[str, Any] = {"model": None, "factors": None, "fp": None}


def _model_fp(model: ProcessModel) -> str:
    try:
        raw = model.model_dump_json()
    except Exception:
        raw = json.dumps(model.model_dump(), sort_keys=True, default=str)
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def set_context(model: Optional[ProcessModel], factors: Optional[Dict] = None) -> Dict[str, Any]:
    """同步训练上下文；若流程模型发生实质变化，自动重建各优化器训练任务。"""
    with _CTX_LOCK:
        fp = _model_fp(model) if model else None
        changed = fp != _CTX["fp"]
        _CTX.update(model=model, factors=factors, fp=fp)
    if changed and model is not None:
        for o in all_optimizers():
            try:
                o.setup(model, factors)
            except Exception as e:  # pragma: no cover
                o.error = str(e)
    return {"model_changed": bool(changed), "ready": len(_optim_space(model)) if model else 0}


# ============================ 后台定时训练调度器 ============================

class TrainingScheduler:
    """后台定时训练线程：按各模型的自训练设置（频率/时段）驱动「运行中」的模型迭代。

    随实时传感器数据持续采集（DEVICE_HISTORY 每遥测 tick 追加采样点），
    调度线程以细粒度唤醒并对到期的模型执行一步迭代 ——
    对应产品语义「后台定时训练、模型逐渐变优」；频率与时段可在属性面板调整。
    """

    def __init__(self, wake: float = TRAIN_INTERVAL):
        self.wake = wake
        self._t: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self):
        if self._t and self._t.is_alive():
            return
        self._stop.clear()
        self._t = threading.Thread(target=self._loop, name="ai-optimizer-trainer", daemon=True)
        self._t.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            self._stop.wait(self.wake)
            if self._stop.is_set():
                break
            now = time.time()
            for o in all_optimizers():
                if not o.running or not o.ready:
                    continue
                if now < o.next_train_at:
                    continue
                # 训练时段之外：降低检查频率，进入时段后自动恢复
                if not o.in_window():
                    o.next_train_at = now + 30
                    continue
                try:
                    o.step()
                except Exception:  # pragma: no cover
                    pass
                finally:
                    o.next_train_at = now + float(o.schedule.get("interval", 30))


scheduler = TrainingScheduler()
scheduler.start()  # 模块导入即常驻后台（daemon 线程，进程退出自动终止）
