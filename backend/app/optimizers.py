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
from .realtime import DEVICE_HISTORY, DEVICE_META

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


# 优化目标候选（策略模型「优化目标」设定；方向均为最小化）
# 全流程指标：覆盖完整流程的碳排 / 综合能耗 / 电耗，随实时传感系数折算
OBJECTIVE_OPTIONS: List[Dict[str, str]] = [
    {"key": "intensity", "label": "吨钢碳强度", "unit": "kgCO₂/t", "group": "全流程指标"},
    {"key": "energy_intensity", "label": "吨钢综合能耗", "unit": "kgce/t", "group": "全流程指标"},
    {"key": "co2_total", "label": "全流程碳排放总量", "unit": "t/h", "group": "全流程指标"},
    {"key": "energy_total", "label": "全流程综合能耗", "unit": "GJ/h", "group": "全流程指标"},
    {"key": "elec", "label": "全流程电耗", "unit": "MWh/h", "group": "全流程指标"},
]

# 工艺实时指标：unit:{unit_id}:{metric} —— 每个工艺的实时碳排放 / 实时能耗 / 实时电耗
UNIT_METRIC_OPTIONS: List[Dict[str, str]] = [
    {"key": "co2_total", "label": "实时碳排放", "unit": "t/h"},
    {"key": "energy_total", "label": "实时能耗", "unit": "GJ/h"},
    {"key": "elec", "label": "实时电耗", "unit": "MWh/h"},
]


def _objective_options(model: Optional["ProcessModel"] = None) -> List[Dict[str, Any]]:
    """全流程指标 + 每个工艺的实时指标（工艺随流程模型动态生成）。"""
    out: List[Dict[str, Any]] = [dict(o) for o in OBJECTIVE_OPTIONS]
    if model is not None:
        for u in model.units:
            if not u.enabled:
                continue
            for m in UNIT_METRIC_OPTIONS:
                out.append({
                    "key": f"unit:{u.id}:{m['key']}",
                    "label": f"{u.name}·{m['label']}",
                    "unit": m["unit"],
                    "group": "工艺实时指标",
                    "unit_id": u.id,
                })
    return out


def _objective_unit(key: str) -> str:
    if isinstance(key, str) and key.startswith("unit:"):
        try:
            metric = key.split(":", 2)[2]
            m = next((x for x in UNIT_METRIC_OPTIONS if x["key"] == metric), None)
            if m:
                return m["unit"]
        except Exception:
            pass
        return "kgCO₂/t"
    for o in OBJECTIVE_OPTIONS:
        if o["key"] == key:
            return o["unit"]
    return "kgCO₂/t"


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
        # ---- 优化目标与决策变量 ----
        self.objective = "intensity"               # 优化目标（OBJECTIVE_OPTIONS key）
        self.objective_neg = True                  # 目标方向：True=该指标越低越好（fitness=原值）；False=该指标越高越好（fitness=取负）
        self.decisions: Dict[str, bool] = {}       # 决策变量启用集合：f"{unit_id}:{key}" -> bool
        self._init_norm: List[float] = []          # 归一化初始值（决策变量冻结基准）
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
    def _objective_value(self, r) -> float:
        """按当前优化目标从仿真结果取值：unit:{id}:{metric} 取该工艺实时指标，否则取全流程指标。"""
        key = self.objective
        if isinstance(key, str) and key.startswith("unit:"):
            try:
                _, uid, metric = key.split(":", 2)
                for un in r.units:
                    if un.id == uid:
                        return float(getattr(un, metric, 1e6))
            except Exception:
                pass
            return 1e6
        return float(getattr(r.totals, key, getattr(r.totals, "intensity", 1e6)))

    def _fitness(self, values: List[float]) -> float:
        """把归一化 values 写入工作区参数并仿真，返回调制后优化目标值（越小越好）。"""
        ws = self._ws
        for p, v in zip(self.space, values):
            u = ws.by_id.get(p["unit_id"])
            if u is None:
                continue
            u.params[p["key"]] = p["lo"] + (p["hi"] - p["lo"]) * min(1.0, max(0.0, v))
        try:
            r = cached_simulate(ws.model, self._factors)
            fit = self._objective_value(r)
        except Exception:
            fit = 1e6
        if not math.isfinite(fit) or fit <= 0:
            fit = 1e6
        if self.objective_neg is False and fit < 1e6:
            fit = -fit                # 指标越高越好：目标值取负进入统一的最小化框架
        return fit * _live_load_factor()

    def _phys(self, values: List[float]) -> List[float]:
        return [p["lo"] + (p["hi"] - p["lo"]) * min(1.0, max(0.0, v))
                for p, v in zip(self.space, values)]

    # ---------- 决策变量与优化目标 ----------
    def _active_mask(self) -> List[bool]:
        """与 space 对齐的决策变量启用掩码。"""
        return [bool(self.decisions.get(f"{p['unit_id']}:{p['key']}", True)) for p in self.space]

    def _freeze(self, vals: List[float], base: Optional[List[float]] = None) -> List[float]:
        """决策变量未启用（active=False）的维度冻结为 base（默认初始值），不参与寻优。"""
        base = base if base is not None else self._init_norm
        return [v if a else b for v, b, a in zip(vals, base, self._active_mask())]

    def _obj_unit(self) -> str:
        return _objective_unit(self.objective)

    # ---------- 生命周期 ----------
    def setup(self, model: ProcessModel, factors: Optional[Dict] = None):
        """用新的流程模型重建训练任务（保留 archived 最佳记录用于跨模型对比）。"""
        with self._lock:
            if self._ws is not None and self.iteration > 0 and self.best_fitness != 0:
                self.archived = {
                    "iteration": self.iteration,
                    "best_fitness": round(self.best_fitness, 2),
                    "samples": self.samples,
                }
            self._ws = _Workspace(model)
            self._factors = factors
            self._fp = _model_fp(model)
            self.space = _optim_space(model)
            self.decisions = {f"{p['unit_id']}:{p['key']}": True for p in self.space}
            self._init_norm = [(p["init"] - p["lo"]) / (p["hi"] - p["lo"]) for p in self.space]
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
            init_values = list(self._init_norm)
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
                self._log(f"流程模型已变更，训练重建（上一轮最优 {self.archived['best_fitness']} {self._obj_unit()}）")
            else:
                self._log(f"模型就绪：{len(self.space)} 个优化参数，初始目标值 {self.start_fitness:.1f} {self._obj_unit()}")

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
            improvement = ((self.start_fitness - self.best_fitness)
                           / abs(self.start_fitness) * 100) if self.start_fitness else 0.0
            # ---- 版本管理与控制模式 ----
            # 比较基线：同上下文下当前版本的最优强度；无版本/上下文已变则回到初始强度
            active = self._active_fp_version()
            baseline = active["best_fitness"] if active else self.start_fitness
            if baseline != 0:
                gain_vs_active = (baseline - self.best_fitness) / abs(baseline) * 100
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
                if reminded_base != 0:
                    rg = (reminded_base - self.best_fitness) / abs(reminded_base) * 100
                    if rg >= REMINDER_GAIN:
                        self.reminder = {
                            "id": f"r{self.iteration}_{int(time.time())}",
                            "best_fitness": round(self.best_fitness, 2),
                            "improvement_pct": round(rg, 2),
                            "iteration": self.iteration,
                            "ts": time.time(),
                        }
                        self._last_reminded = self.best_fitness
                        self._log(f"训练取得进展：最优目标值 {self.best_fitness:.2f} {self._obj_unit()}（提升 {rg:.1f}%），已生成手动调优提醒")
            if self.iteration == 1:
                obj_label = self.objective
                opt = next((o for o in _objective_options(self._ws.model if self._ws else None) if o["key"] == self.objective), None)
                if opt is not None:
                    obj_label = opt["label"]
                self._log(f"训练开始：目标为最小化{obj_label}（随实时传感器数据持续优化）")
            if self.iteration % 8 == 0 or gain >= 200:
                msg = f"迭代 #{self.iteration}：最优目标值 {self.best_fitness:.2f} {self._obj_unit()}（较初始 {improvement:.2f}%）"
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
                self._log(f"已按版本 {rec['id']} 的参数下发到流程（最优 {rec['best_fitness']} {self._obj_unit()}）")
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
               / abs(self.start_fitness) * 100) if self.start_fitness else 0.0
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
                self._log(f"模型升级：新版本 {ver['id']} 替换为当前版本（最优 {ver['best_fitness']} {self._obj_unit()}，提升 {ver['improvement_pct']:.2f}%）")
            else:
                self.versions.append(ver)
                self._log(f"已保存候选版本 {ver['id']}（最优 {ver['best_fitness']} {self._obj_unit()}，未超过当前版本，不替换）")
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
            self._log(f"已切换为版本 {version_id}（最优 {v['best_fitness']} {self._obj_unit()}）")

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
            if "objective" in patch:
                key = str(patch["objective"] or "intensity")
                opts = _objective_options(self._ws.model if self._ws else None)
                opt = next((o for o in opts if o["key"] == key), None)
                if opt is not None and opt["key"] != self.objective:
                    self.objective = opt["key"]
                    self._log(f"优化目标已切换：{opt['label']}（{opt['unit']}）")
            if "objective_neg" in patch:
                self.objective_neg = bool(patch["objective_neg"])
                self._log(f"优化目标方向：{'取负值（该指标越低越好）' if self.objective_neg else '不取负（该指标越高越好）'}")
            if "decisions" in patch:
                want = set(str(x) for x in (patch["decisions"] or []))
                keys = {f"{p['unit_id']}:{p['key']}" for p in self.space}
                self.decisions = {k: (k in want) for k in keys}
                cnt = sum(1 for v in self.decisions.values() if v)
                self._log(f"决策变量已设定：{cnt}/{len(self.decisions)} 个参数参与优化")
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
                           / abs(self.start_fitness) * 100) if self.start_fitness else 0.0
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
                "objective_neg": bool(self.objective_neg),
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
                # 优化目标与决策变量（属性面板「优化目标 / 决策变量」设定）
                "objective": self.objective,
                "objective_unit": self._obj_unit(),
                "objectives": _objective_options(self._ws.model if self._ws else None),
                "decisions": dict(self.decisions),
                "space": [
                    {
                        "dkey": f"{p['unit_id']}:{p['key']}",
                        "unit_id": p["unit_id"], "unit_name": p["unit_name"],
                        "unit_type": p["unit_type"],
                        "key": p["key"], "label": p["label"], "unit": p["unit"],
                        "lo": p["lo"], "hi": p["hi"],
                        "value": round(pv, 3), "initial": round(p["init"], 3),
                        "active": bool(self.decisions.get(f"{p['unit_id']}:{p['key']}", True)),
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
        self._pop = []
        for _ in range(n):
            x = self._freeze([random.random() for _ in range(d)])
            self._pop.append((x, self._fitness(x)))
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
                c = self._freeze(c)
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
        self._xs = [self._freeze([random.random() for _ in range(d)]) for _ in range(n)]
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
            self._xs[i] = self._freeze([min(1.0, max(0.0, x + vj)) for x, vj in zip(self._xs[i], self._vs[i])])
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
            c = self._freeze([min(1.0, max(0.0, mu[i] + random.gauss(0, sigma))) for i in range(d)], mu)
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


# ============================ 序列预测算法（SEQ · 预测未来工况寻优） ============================

SEQ_HYPER: Dict[str, Dict] = {
    "horizon": {"label": "预测窗口(秒)", "min": 1,  "max": 60, "step": 1,  "default": 15},
    "smooth":  {"label": "平滑系数 α",   "min": 0.1, "max": 0.9, "step": 0.05, "default": 0.5},
    "samples": {"label": "每次采样数",   "min": 2,  "max": 30, "step": 1,  "default": 8},
    "lr":      {"label": "调节步长",     "min": 0.01,"max": 0.5, "step": 0.01, "default": 0.08},
}

# 序列预测算法可选模型（属性面板下拉选择；llm 暂不实现，选择后训练挂起并提示）
SEQ_MODELS: List[Dict[str, str]] = [
    {"id": "lstm", "label": "LSTM 长短期记忆网络"},
    {"id": "lightgbm", "label": "LightGBM 梯度提升"},
    {"id": "xgboost", "label": "XGBoost 梯度提升"},
    {"id": "llm", "label": "时间序列大模型（暂不实现）"},
]


class SequencePredictOptimizer(OptimizerBase):
    """序列预测算法（时序外推 + 参数寻优）。

    适用于预测未来工况、设定最佳策略或调节变量进行仿真分析的场景。属性面板可
    选择预测模型：LSTM / LightGBM / XGBoost（可运行的简化实现）与时间序列大模型
    （暂不实现，选择后训练挂起并提示）。先基于最近传感器读数按所选模型外推未来
    窗口的工况负荷，再在该预测工况下采样调节变量做仿真评估，按「预测工况碳强度
    改善」加权更新策略。
    """

    kind = "seq"

    def _init_search(self):
        self._mu = [(p["init"] - p["lo"]) / (p["hi"] - p["lo"]) for p in self.space]
        self._mu_best = list(self._mu)
        self._pred = 1.0
        self.model = "lstm"
        self._llm_warned = False
        # 预测目标（'load' = 全厂工况负荷；设备 id = 只预测该设备指标）与影响变量
        # （空列表 = 全部设备参与预测；非空 = 仅列出的设备参与）
        self.forecast_target = "load"
        self.impact_vars: List[str] = []

    # ---------- 时序预测（按所选模型分派） ----------
    def _forecast(self) -> Optional[float]:
        """按预测目标 / 影响变量聚合传感器序列预测未来工况负荷因子（llm 暂不实现返回 None）。"""
        if self.model == "llm":
            return None
        n = 0
        s = 0.0
        tnow = time.time()
        alpha = float(self.hyperparams["smooth"])
        horizon = float(self.hyperparams["horizon"])
        for did, buf in DEVICE_HISTORY.items():
            # 影响变量过滤：非空时只取列出的设备
            if self.impact_vars and did not in self.impact_vars:
                continue
            # 预测目标过滤：指定具体设备时只预测该设备
            if self.forecast_target != "load" and self.forecast_target != did:
                continue
            pts = sorted((p for p in buf if tnow - p["t"] < 360), key=lambda p: p["t"])
            if len(pts) < 5:
                continue
            base = pts[0]["v"]
            if base <= 1e-9:
                continue
            fut = self._predict_series(pts, alpha, horizon)
            s += fut / base
            n += 1
        if n == 0:
            return 1.0
        return min(max(s / n, 0.9), 1.15)

    def _predict_series(self, pts: List[Dict], alpha: float, horizon: float) -> float:
        """对单个传感器序列做未来预测（LSTM / LightGBM / XGBoost 的可运行简化实现）。"""
        ts = [p["t"] for p in pts]
        vs = [p["v"] for p in pts]
        span = max(ts[-1] - ts[0], 1e-9)
        if self.model == "lstm":
            # LSTM 风格：门控记忆细胞（遗忘门随变化率自适应）+ 近端趋势外推
            cell = vs[0]
            mem = abs(vs[0])
            for i in range(1, len(vs)):
                dt = max(1e-9, ts[i] - ts[i - 1])
                rate = abs((vs[i] - vs[i - 1]) / dt)
                gate = min(1.0, alpha * (1.0 + 0.5 * rate / max(mem, 1e-9)))
                cell = gate * vs[i] + (1 - gate) * cell
                mem = max(mem, abs(vs[i]))
            slope = (vs[-1] - cell) / span
            return max(cell + slope * horizon, 1e-9)
        if self.model == "lightgbm":
            # LightGBM 风格：线性趋势基准 + 近端残差提升项（梯度提升）
            mx = sum(ts) / len(ts)
            my = sum(vs) / len(vs)
            sxx = sum((x - mx) ** 2 for x in ts)
            sxy = sum((x - mx) * (y - my) for x, y in zip(ts, vs))
            k = sxy / sxx if sxx > 1e-12 else 0.0
            b = my - k * mx
            res = [v - (k * t + b) for t, v in zip(ts, vs)]
            boost = sum(res[-3:]) / min(3, len(res))
            return max(k * (ts[-1] + horizon) + b + boost, 1e-9)
        # XGBoost 风格：分段树（段均值）+ 学习率收缩的段间梯度外推
        seg = max(1, len(vs) // 4)
        means = [sum(vs[i:i + seg]) / len(vs[i:i + seg]) for i in range(0, len(vs), seg)]
        last_m = means[-1]
        prev_m = means[-2] if len(means) > 1 else last_m
        grad = (last_m - prev_m) / max(span / max(len(means), 1), 1e-9)
        return max(last_m + alpha * grad * horizon, 1e-9)

    def step(self):
        with self._lock:
            if not self.ready:
                return
            if self.model == "llm":
                if not self._llm_warned:
                    self._llm_warned = True
                    self._log("时间序列大模型暂不实现：请选择 LSTM / LightGBM / XGBoost 模型后训练")
                return
        super().step()

    def set_settings(self, patch: Dict[str, Any]):
        with self._lock:
            if "model" in patch:
                mid = str(patch["model"] or "").strip().lower()
                m = next((m for m in SEQ_MODELS if m["id"] == mid), None)
                if m and m["id"] != self.model:
                    self.model = m["id"]
                    self._llm_warned = False
                    self._log(f"已切换预测模型：{m['label']}")
                    if m["id"] == "llm":
                        self._log("时间序列大模型暂不实现：请选择 LSTM / LightGBM / XGBoost 模型后训练")
            if "forecast_target" in patch:
                t = str(patch["forecast_target"] or "load").strip()
                if t != self.forecast_target:
                    self.forecast_target = t
                    label = "全厂工况负荷" if t == "load" else (DEVICE_META.get(t, {}).get("label") or t)
                    self._log(f"预测目标已设定：{label}")
            if "impact_vars" in patch:
                want = set(str(x) for x in (patch["impact_vars"] or []))
                known = set(DEVICE_META.keys())
                if not want or not known:
                    self.impact_vars = []
                else:
                    self.impact_vars = sorted(known & want)
                desc = "全部设备" if not self.impact_vars else f"{len(self.impact_vars)} 个设备"
                self._log(f"影响变量已设定：{desc}参与预测")
            super().set_settings({k: v for k, v in patch.items()
                                  if k not in ("model", "forecast_target", "impact_vars")})

    def state(self, full: bool = False) -> Dict[str, Any]:
        st = super().state(full)
        st["model"] = getattr(self, "model", "lstm")
        st["models"] = [dict(m) for m in SEQ_MODELS]
        st["forecast_target"] = getattr(self, "forecast_target", "load")
        st["forecast_targets"] = [{"id": "load", "label": "全厂工况负荷", "unit": "负荷系数"}] + [
            {"id": did, "label": m.get("label") or did, "unit": m.get("unit") or "",
             "unit_name": m.get("unit_name") or ""}
            for did, m in sorted(DEVICE_META.items())
        ]
        st["impact_vars"] = list(getattr(self, "impact_vars", []) or [])
        st["impact_candidates"] = [
            {"id": did, "label": m.get("label") or did, "unit": m.get("unit") or "",
             "unit_name": m.get("unit_name") or "", "unit_type": m.get("unit_type") or ""}
            for did, m in sorted(DEVICE_META.items())
        ]
        return st

    def _train_once(self):
        lr = float(self.hyperparams["lr"])
        n = int(self.hyperparams["samples"])
        d = len(self.space)
        pred = self._forecast()
        if pred is None:
            pred = 1.0
        self._pred = pred
        # 预测波动越大 → 探索强度越大（未来工况不确定时多尝试调节变量）
        sigma = lr * (1.0 + 1.5 * abs(pred - 1.0))
        mu = self._mu
        live = _live_load_factor()
        # 基线也换算到预测工况下评估，保证奖励（相对改善）基于同一工况
        base_f = self._fitness(mu) * (pred / live)
        cands = []
        for _ in range(n):
            c = self._freeze([min(1.0, max(0.0, mu[i] + random.gauss(0, sigma))) for i in range(d)], mu)
            # 在预测的未来工况下做仿真评估（预测因子替代实时因子）
            fit = self._fitness(c) * (pred / live)
            cands.append((c, fit))
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


# ============================ 聚类工况识别（CLU · 无监督工况聚类） ============================

CLU_HYPER: Dict[str, Dict] = {
    "k":       {"label": "工况簇数 K", "min": 2,  "max": 8,  "step": 1,  "default": 3},
    "eps":     {"label": "邻域半径 ε", "min": 0.05, "max": 0.6, "step": 0.05, "default": 0.25},
    "min_pts": {"label": "最小样本数", "min": 3,  "max": 20, "step": 1,  "default": 5},
    "samples": {"label": "每次采样数", "min": 8,  "max": 80, "step": 2,  "default": 24},
}

# 聚类算法可选（属性面板下拉选择）
CLU_MODELS: List[Dict[str, str]] = [
    {"id": "kmeans", "label": "K-Means 均值聚类"},
    {"id": "dbscan", "label": "DBSCAN 密度聚类"},
    {"id": "hierarchical", "label": "层次聚类"},
]


class ClusteringOptimizer(OptimizerBase):
    """聚类工况识别（无监督聚类）。

    适用于历史工况的自动聚类与模式划分：基于最近传感器读数构造「工况快照」
    （各聚类特征设备归一化读数 + 全厂负荷因子），按所选算法（K-Means / DBSCAN /
    层次聚类）识别典型运行工况簇（如低/中/高负荷），输出各工况占比与代表负荷，
    辅助制定分工况调节策略。聚类本身不直接寻优，故不产出最优参数版本；
    训练迭代实时反映当前运行工况分布。
    """

    kind = "clu"

    def _init_search(self):
        self._mu = [(p["init"] - p["lo"]) / (p["hi"] - p["lo"]) for p in self.space]
        self._mu_best = list(self._mu)
        self.method = "kmeans"
        # 聚类特征变量（空列表 = 全部设备参与聚类）
        self.feature_vars: List[str] = []
        self._clusters: List[Dict[str, Any]] = []
        self._compact = 0.0
        self._clusters_ready = False

    # ---------- 工况快照构造 ----------
    def _snapshots(self) -> List[List[float]]:
        """构造工况快照特征向量：n 个时间桶 ×（特征设备归一化读数 + 全厂负荷因子）。"""
        n = int(self.hyperparams.get("samples", 24))
        n = min(max(n, 4), 120)
        tnow = time.time()
        win = 600.0
        feat = [d for d in (self.feature_vars or sorted(DEVICE_HISTORY.keys()))
                if d in DEVICE_HISTORY and DEVICE_HISTORY[d]]
        if not feat:
            return []
        per = {}
        for d in feat:
            pts = sorted((p for p in DEVICE_HISTORY[d] if tnow - p["t"] <= win), key=lambda p: p["t"])
            if not pts:
                continue
            vs = [p["v"] for p in pts]
            lo = min(vs)
            span = max(vs) - lo
            per[d] = {"pts": pts, "lo": lo, "span": span if span > 1e-9 else 1.0,
                      "base": (sum(vs) / len(vs)) or 1.0}
        feat = [d for d in feat if d in per]
        if not feat:
            return []
        rows = []
        for i in range(n):
            tk = tnow - win * (n - 1 - i) / n
            row = []
            for d in feat:
                pd = per[d]
                row.append((self._val_at(pd["pts"], tk) - pd["lo"]) / pd["span"])
            load = sum(self._val_at(per[d]["pts"], tk) / per[d]["base"] for d in feat) / len(feat)
            row.append(min(max(load, 0.85), 1.15))
            rows.append(row)
        return rows

    @staticmethod
    def _val_at(pts: List[Dict], t: float) -> float:
        """时刻 t 的前向填充取值（最后满足 p.t <= t 的读数）。"""
        if t <= pts[0]["t"]:
            return pts[0]["v"]
        if t >= pts[-1]["t"]:
            return pts[-1]["v"]
        lo, hi = 0, len(pts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if pts[mid]["t"] <= t:
                lo = mid
            else:
                hi = mid - 1
        return pts[lo]["v"]

    # ---------- 聚类算法 ----------
    @staticmethod
    def _dist(a: List[float], b: List[float]) -> float:
        return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5

    def _cluster(self, X: List[List[float]], method: str) -> List[int]:
        m = len(X)
        if m < 2:
            return [0] * m
        if method == "dbscan":
            return self._dbscan(X)
        k = min(max(int(self.hyperparams.get("k", 3)), 2), min(8, m))
        if method == "hierarchical":
            return self._hierarchical(X, k)
        return self._kmeans(X, k)

    def _kmeans(self, X: List[List[float]], k: int) -> List[int]:
        """K-Means：k-means++ 初始化 + Lloyd 迭代（≤ 40 轮）。"""
        m = len(X)
        centers = [list(X[random.randrange(m)])]
        for _ in range(1, k):
            d2 = [min(self._dist(x, c) ** 2 for c in centers) for x in X]
            tot = sum(d2)
            if tot <= 1e-12:
                break
            r = random.random() * tot
            acc = 0.0
            chosen = 0
            for i, di in enumerate(d2):
                acc += di
                if acc >= r:
                    chosen = i
                    break
            centers.append(list(X[chosen]))
        labels = [0] * m
        for _ in range(40):
            new = [min(range(len(centers)), key=lambda j: self._dist(x, centers[j])) for x in X]
            if new == labels:
                break
            labels = new
            for j in range(len(centers)):
                members = [X[i] for i in range(m) if labels[i] == j]
                if members:
                    centers[j] = [sum(col) / len(col) for col in zip(*members)]
        return labels

    def _dbscan(self, X: List[List[float]]) -> List[int]:
        """DBSCAN：邻域密度聚类（-1 = 噪声，其余为簇号）。"""
        m = len(X)
        eps = float(self.hyperparams.get("eps", 0.25))
        min_pts = int(self.hyperparams.get("min_pts", 5))
        neigh = [[j for j in range(m) if i != j and self._dist(X[i], X[j]) <= eps] for i in range(m)]
        labels = [-2] * m  # -2 未访问 / -1 噪声 / >=0 簇号
        cid = 0
        for i in range(m):
            if labels[i] != -2:
                continue
            if len(neigh[i]) < min_pts:
                labels[i] = -1
                continue
            stack = [i]
            labels[i] = cid
            while stack:
                p = stack.pop()
                if len(neigh[p]) < min_pts:
                    continue  # 边界点不扩展
                for q in neigh[p]:
                    if labels[q] == -2:
                        labels[q] = cid
                        stack.append(q)
            cid += 1
        return labels

    def _hierarchical(self, X: List[List[float]], k: int) -> List[int]:
        """层次聚类：单连接自底向上合并，直到剩余 k 簇。"""
        m = len(X)
        cl = [[i] for i in range(m)]
        while len(cl) > k:
            best = (0, 1)
            bd = float("inf")
            for a in range(len(cl)):
                for b in range(a + 1, len(cl)):
                    d = min(self._dist(X[i], X[j]) for i in cl[a] for j in cl[b])
                    if d < bd:
                        bd = d
                        best = (a, b)
            a, b = best
            cl[a].extend(cl[b])
            del cl[b]
        labels = [0] * m
        for cid, members in enumerate(cl):
            for i in members:
                labels[i] = cid
        return labels

    @staticmethod
    def _cluster_names(k: int) -> List[str]:
        # clusters 已按代表负荷降序排列：第一个 = 最高负荷
        if k == 2:
            return ["高负荷工况", "低负荷工况"]
        if k == 3:
            return ["高负荷工况", "中负荷工况", "低负荷工况"]
        if k == 4:
            return ["高负荷工况", "偏高负荷工况", "偏低负荷工况", "低负荷工况"]
        return [f"工况 {i}" for i in range(1, k + 1)]

    # ---------- 训练迭代 ----------
    def _train_once(self):
        X = self._snapshots()
        if len(X) < 2:
            return self.best_fitness, self.best_fitness
        labels = self._cluster(X, self.method)
        m = len(X)
        stat = {}
        for i, lab in enumerate(labels):
            st = stat.setdefault(lab, {"size": 0, "sum": [0.0] * len(X[i])})
            st["size"] += 1
            for j, v in enumerate(X[i]):
                st["sum"][j] += v
        clusters = []
        for lab, st in stat.items():
            center = [s / st["size"] for s in st["sum"]]
            clusters.append({"id": lab, "size": st["size"],
                             "pct": round(st["size"] / m * 100, 1),
                             "load": center[-1] if center else 0.0, "center": center})
        clusters.sort(key=lambda c: c["load"], reverse=True)
        for c, nm in zip(clusters, self._cluster_names(len(clusters))):
            c["name"] = nm
        self._clusters = clusters
        by_id = {c["id"]: c for c in clusters}
        compact = sum(self._dist(X[i], by_id[lab]["center"])
                      for i, lab in enumerate(labels) if lab in by_id) / m
        self._compact = compact
        if self.iteration % 8 == 0 or not self._clusters_ready:
            desc = "、".join(f"{c['name']} {c['pct']}%" for c in clusters)
            self._log(f"工况聚类：识别 {len(clusters)} 个工况簇（{desc}），类内紧凑度 {compact:.3f}")
            self._clusters_ready = True
        return self.best_fitness, round(compact, 4)

    def set_settings(self, patch: Dict[str, Any]):
        with self._lock:
            if "method" in patch:
                mid = str(patch["method"] or "").strip().lower()
                m = next((x for x in CLU_MODELS if x["id"] == mid), None)
                if m and m["id"] != self.method:
                    self.method = m["id"]
                    self._log(f"已切换聚类算法：{m['label']}")
            if "feature_vars" in patch:
                want = set(str(x) for x in (patch["feature_vars"] or []))
                known = set(DEVICE_META.keys())
                if not want or not known:
                    self.feature_vars = []
                else:
                    self.feature_vars = sorted(known & want)
                desc = "全部设备" if not self.feature_vars else f"{len(self.feature_vars)} 个设备"
                self._log(f"聚类特征已设定：{desc}参与工况聚类")
            super().set_settings({k: v for k, v in patch.items()
                                  if k not in ("method", "feature_vars")})

    def state(self, full: bool = False) -> Dict[str, Any]:
        st = super().state(full)
        st["method"] = getattr(self, "method", "kmeans")
        st["methods"] = [dict(m) for m in CLU_MODELS]
        st["feature_vars"] = list(getattr(self, "feature_vars", []) or [])
        st["feature_candidates"] = [
            {"id": did, "label": m.get("label") or did, "unit": m.get("unit") or "",
             "unit_name": m.get("unit_name") or "", "unit_type": m.get("unit_type") or ""}
            for did, m in sorted(DEVICE_META.items())
        ]
        st["clusters"] = [dict(c) for c in (getattr(self, "_clusters", []) or [])]
        st["compactness"] = round(getattr(self, "_compact", 0.0), 4)
        return st


# ============================ 数据拟合（FIT） ============================

FIT_MODELS: List[Dict[str, str]] = [
    {"id": "poly",  "label": "多项式拟合", "desc": "y = c0 + c1·x + c2·x² + …（线性最小二乘）"},
    {"id": "exp",   "label": "指数拟合",   "desc": "y = a·e^(b·x)"},
    {"id": "log",   "label": "对数拟合",   "desc": "y = a + b·ln(x)"},
    {"id": "power", "label": "幂函数拟合", "desc": "y = a·x^b"},
]

FIT_HYPER: Dict[str, Dict] = {
    "order":  {"label": "多项式阶数", "min": 1,  "max": 6,  "step": 1,  "default": 2},
    "window": {"label": "样本窗口",   "min": 20, "max": 240, "step": 10, "default": 80},
    "future": {"label": "外推步数",   "min": 0,  "max": 60,  "step": 5,  "default": 10},
}


class DataFitOptimizer(OptimizerBase):
    """数据拟合：对目标序列做多项式 / 指数 / 对数 / 幂函数曲线拟合，
    输出拟合方程与 R² 拟合优度（不寻优、不下发参数，仅建模分析）。"""

    kind = "fit"

    def _init_search(self):
        self.method = "poly"
        self.target = "load"          # 'load' = 全厂工况负荷；否则 = 设备 id
        self.fit_vars: List[str] = [] # 拟合变量（参与拟合的设备序列，空 = 未指定/全部）
        self._fit: Optional[Dict[str, Any]] = None
        self._curve: List[Dict[str, float]] = []
        self._r2 = 0.0

    # ---------- 序列构造 ----------
    def _targets(self) -> List[Dict[str, str]]:
        out = [{"id": "load", "label": "全厂工况负荷", "unit": "负荷系数",
                "unit_name": "", "unit_type": ""}]
        for did, m in sorted(DEVICE_META.items()):
            out.append({
                "id": did,
                "label": m.get("label") or did,
                "unit": m.get("unit") or "",
                "unit_name": m.get("unit_name") or "",
                "unit_type": m.get("unit_type") or "",
            })
        return out

    def _series(self) -> List[float]:
        """取拟合序列：目标序列最近 window 个采样点（负荷系数或设备读数）。"""
        tnow = time.time()
        win_s = 900.0
        window = min(max(int(self.hyperparams.get("window", 80)), 20), 240)
        if self.target == "load":
            devs = [d for d in sorted(DEVICE_HISTORY.keys()) if DEVICE_HISTORY[d]]
            if not devs:
                return []
            per = {}
            for d in devs:
                pts = sorted((p for p in DEVICE_HISTORY[d] if tnow - p["t"] <= win_s), key=lambda p: p["t"])
                if not pts:
                    continue
                vs = [p["v"] for p in pts]
                per[d] = {"pts": pts, "base": (sum(vs) / len(vs)) or 1.0}
            devs = [d for d in devs if d in per]
            if not devs:
                return []
            # 时间桶：最近 window 个采样时刻，每桶取全厂负荷系数
            out = []
            for i in range(window):
                tk = tnow - win_s + (win_s * (i + 1)) / (window + 1)
                load = sum(ClusteringOptimizer._val_at(per[d]["pts"], tk) / per[d]["base"]
                           for d in devs) / len(devs)
                out.append(min(max(load, 0.85), 1.15))
            return out
        pts = sorted((p for p in DEVICE_HISTORY.get(self.target, [])
                      if tnow - p["t"] <= win_s), key=lambda p: p["t"])
        return [p["v"] for p in pts][-window:]

    # ---------- 拟合核心 ----------
    @staticmethod
    def _lsolve(a: List[List[float]], b: List[float]) -> List[float]:
        """高斯消元求解线性方程组 A x = b（n ≤ 8）。"""
        n = len(a)
        m = [row[:] + [b[i]] for i, row in enumerate(a)]
        for col in range(n):
            piv = max(range(col, n), key=lambda r: abs(m[r][col]))
            if abs(m[piv][col]) < 1e-12:
                continue
            m[col], m[piv] = m[piv], m[col]
            for r in range(col + 1, n):
                f = m[r][col] / m[col][col]
                for c in range(col, n + 1):
                    m[r][c] -= f * m[col][c]
        x = [0.0] * n
        for i in range(n - 1, -1, -1):
            if abs(m[i][i]) < 1e-12:
                continue
            x[i] = (m[i][n] - sum(m[i][j] * x[j] for j in range(i + 1, n))) / m[i][i]
        return x

    @staticmethod
    def _eval(coeffs: List[float], x: float, method: str) -> float:
        try:
            if method == "poly":
                return sum(c * x ** p for p, c in enumerate(coeffs))
            if method == "exp":
                return coeffs[0] * math.exp(coeffs[1] * x)
            if method == "log":
                return coeffs[0] + coeffs[1] * math.log(max(x, 1.0))
            return coeffs[0] * max(x, 1.0) ** coeffs[1]
        except Exception:  # pragma: no cover
            return 0.0

    def _fit_once(self, ys: List[float], method: str, order: int):
        """对序列 ys（x = 0..n-1）做拟合，返回 (coeffs, yfit, eq, r2)。"""
        n = len(ys)
        if n < 3:
            return [], [], "", 0.0
        xs = [float(i) for i in range(n)]
        coeffs: List[float] = []
        yfit: List[float] = []
        if method == "poly":
            order = min(max(int(order), 1), 6)
            if order >= n:
                order = max(1, n - 2)
            k = order + 1
            # 正规方程 (AᵀA)c = Aᵀy，A[i][p] = x^p
            ata = [[sum(xs[i] ** (r + c) for i in range(n)) for c in range(k)] for r in range(k)]
            aty = [sum(xs[i] ** r * ys[i] for i in range(n)) for r in range(k)]
            coeffs = self._lsolve(ata, aty)
            yfit = [sum(coeffs[p] * x ** p for p in range(k)) for x in xs]
            terms = []
            for p in range(k - 1, -1, -1):
                c = coeffs[p]
                if abs(c) < 1e-6:
                    continue
                if p == 0:
                    terms.append(f"{c:.4g}")
                elif p == 1:
                    terms.append(f"{c:.4g}·x")
                else:
                    terms.append(f"{c:.4g}·x^{p}")
            eq = "y = " + " + ".join(terms) if terms else "y = 0"
        elif method == "exp":
            if any(v <= 0 for v in ys):
                return [], [], "", 0.0
            ly = [math.log(v) for v in ys]
            mx = sum(xs) / n
            my = sum(ly) / n
            cov = sum((xs[i] - mx) * (ly[i] - my) for i in range(n))
            var = sum((xs[i] - mx) ** 2 for i in range(n))
            b = cov / var if var > 1e-12 else 0.0
            a = math.exp(my - b * mx)
            coeffs = [a, b]
            yfit = [a * math.exp(b * x) for x in xs]
            eq = f"y = {a:.4g}·e^({b:.4g}·x)"
        elif method == "log":
            lx = [math.log(i + 1) for i in range(n)]
            mx = sum(lx) / n
            my = sum(ys) / n
            cov = sum((lx[i] - mx) * (ys[i] - my) for i in range(n))
            var = sum((lx[i] - mx) ** 2 for i in range(n))
            b = cov / var if var > 1e-12 else 0.0
            a = my - b * mx
            coeffs = [a, b]
            yfit = [a + b * math.log(i + 1) for i in range(n)]
            eq = f"y = {a:.4g} + {b:.4g}·ln(x)"
        else:  # power: y = a·x^b
            if any(v <= 0 for v in ys):
                return [], [], "", 0.0
            ly = [math.log(v) for v in ys]
            lx = [math.log(i + 1) for i in range(n)]
            mx = sum(lx) / n
            my = sum(ly) / n
            cov = sum((lx[i] - mx) * (ly[i] - my) for i in range(n))
            var = sum((lx[i] - mx) ** 2 for i in range(n))
            b = cov / var if var > 1e-12 else 0.0
            a = math.exp(my - b * mx)
            coeffs = [a, b]
            yfit = [a * (i + 1) ** b for i in range(n)]
            eq = f"y = {a:.4g}·x^{b:.4g}"
        mean_y = sum(ys) / n
        ss_tot = sum((v - mean_y) ** 2 for v in ys)
        ss_res = sum((ys[i] - yfit[i]) ** 2 for i in range(n))
        r2 = 1.0 if ss_tot <= 1e-12 else max(0.0, 1.0 - ss_res / ss_tot)
        return coeffs, yfit, eq, r2

    def _train_once(self):
        ys = self._series()
        if len(ys) < 3:
            self._log("拟合样本不足（<3 个点），等待实时数据")
            return self.best_fitness, self.best_fitness
        coeffs, yfit, eq, r2 = self._fit_once(ys, self.method, int(self.hyperparams.get("order", 2)))
        self._r2 = r2
        n = len(ys)
        fut = min(max(int(self.hyperparams.get("future", 0)), 0), 60)
        total = n + fut
        step = max(1, total // 120)
        curve = []
        for i in range(0, total, step):
            x = float(i)
            if i < n:
                curve.append({"x": round(x, 1), "y": round(ys[i], 4),
                              "yfit": round(yfit[i], 4)})
            else:
                curve.append({"x": round(x, 1), "y": None,
                              "yfit": round(self._eval(coeffs, x, self.method), 4)})
        self._curve = curve
        self._fit = {
            "method": self.method,
            "method_label": next((m["label"] for m in FIT_MODELS if m["id"] == self.method), self.method),
            "equation": eq,
            "r2": round(r2, 4),
            "params": [{"name": f"c{i}", "value": round(c, 4)} for i, c in enumerate(coeffs)],
            "n": n,
        }
        if self.iteration == 1 or self.iteration % 8 == 0:
            self._log(f"数据拟合：{self._fit['method_label']} R²={r2:.4f}，方程 {eq}")
        return self.best_fitness, round(r2, 4)

    def set_settings(self, patch: Dict[str, Any]):
        with self._lock:
            if "method" in patch:
                mid = str(patch["method"] or "").strip().lower()
                m = next((x for x in FIT_MODELS if x["id"] == mid), None)
                if m and m["id"] != self.method:
                    self.method = m["id"]
                    self._log(f"已切换拟合方法：{m['label']}")
            if "target" in patch:
                t = str(patch["target"] or "load")
                known = {"load"} | set(DEVICE_META.keys())
                if t in known and t != self.target:
                    self.target = t
                    label = "全厂工况负荷" if t == "load" else (DEVICE_META.get(t, {}).get("label") or t)
                    self._log(f"已切换拟合对象：{label}")
            if "fit_vars" in patch:
                fv = [str(x) for x in (patch["fit_vars"] or [])]
                self.fit_vars = [d for d in fv if d in DEVICE_META]
                self._log(f"拟合变量已设定：{'全部设备' if not self.fit_vars else str(len(self.fit_vars)) + ' 个设备序列'}")
            super().set_settings({k: v for k, v in patch.items()
                                  if k not in ("method", "target", "fit_vars")})

    def state(self, full: bool = False) -> Dict[str, Any]:
        st = super().state(full)
        st["method"] = getattr(self, "method", "poly")
        st["methods"] = [dict(m) for m in FIT_MODELS]
        st["target"] = getattr(self, "target", "load")
        st["targets"] = self._targets()
        st["fit_vars"] = list(getattr(self, "fit_vars", []))
        st["fit_var_candidates"] = self._targets()
        st["fit"] = dict(self._fit) if getattr(self, "_fit", None) else None
        st["curve"] = [dict(c) for c in (getattr(self, "_curve", []) or [])]
        st["best_r2"] = round(getattr(self, "_r2", 0.0), 4)
        return st


# ============================ 注册表与训练上下文 ============================

OPTIMIZERS: Dict[str, OptimizerBase] = {
    "ai::seq": SequencePredictOptimizer(
        "ai::seq",
        "序列预测算法",
        "预测未来工况：内置 LSTM / LightGBM / XGBoost（时间序列大模型暂不实现），设定最佳策略或调节变量进行仿真分析",
        SEQ_HYPER,
    ),
    "ai::rl": ReinforcementOptimizer(
        "ai::rl",
        "强化学习优化策略",
        "在线策略梯度：随实时传感器数据持续更新参数策略，先探索后利用，越训越优",
        RL_HYPER,
    ),
    "ai::ga": GeneticOptimizer(
        "ai::ga",
        "遗传算法优化策略",
        "适用于设备启停与连续参数复合的混合场景：对设备启停开关与喷煤比、焦比等连续参数组合做选择/交叉/变异，全局搜索最低碳排配置",
        GA_HYPER,
    ),
    "ai::pso": ParticleSwarmOptimizer(
        "ai::pso",
        "粒子群优化策略",
        "适用于连续参数空间下最优解的探索：粒子在参数空间协同飞行，快速逼近最优运行点",
        PSO_HYPER,
    ),
    "ai::clu": ClusteringOptimizer(
        "ai::clu",
        "聚类工况识别",
        "适用于历史工况的自动聚类与模式划分：内置 K-Means / DBSCAN / 层次聚类，自动识别典型运行工况（低/中/高负荷）及其占比，辅助制定分工况调节策略",
        CLU_HYPER,
    ),
    "ai::fit": DataFitOptimizer(
        "ai::fit",
        "数据拟合分析",
        "对历史工况数据做曲线拟合建模：内置多项式 / 指数 / 对数 / 幂函数拟合，输出拟合方程与 R² 拟合优度，辅助洞察负荷趋势与关联规律",
        FIT_HYPER,
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
