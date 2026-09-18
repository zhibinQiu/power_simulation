"""适配器注册表：外部数据源的「注册中心」（平台经 HTTP API 操作本模块）。

架构约定（用户诉求）：外部数据接入 = 平台向中间件注册一条数据源，中间件采集后
由输出桥（bridge）用 paho 直发 output.broker（服务器上即同机云端 Broker :41883），
与一体机上报同一 Broker、按主题前缀区分，平台经云端端点统一订阅。
因此本模块是中间件的运行核心：

- 数据源 = 一条 adapter 配置（id/type/name/box/type 专属参数），持久化在 config.json；
- 新增/修改/启停/删除立即热生效（运行中适配器 stop → 重建 → start），无需重启进程；
- box 前缀全局唯一：平台按前缀识别数据归属，不同数据源不得共用；
- 所有状态（running/readings/errors/last_*）经 status() 汇总，供平台轮询展示。
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from middleware.adapters import build, type_catalog
from middleware.adapters.base import BaseAdapter

_BOX_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")
# 保留前缀：避免外部源占用平台/协议保留语义（历史内置模拟源 sim 已移除，不再保留）
_RESERVED = ("box", "platform", "local", "data", "cloud", "state", "cmd", "$sys")


def normalize_box(box: str) -> str:
    return str(box or "").strip().lower().replace(" ", "-").replace("_", "-")


class AdapterRegistry:
    """线程安全的适配器注册表（HTTP API 与运行循环共用一把锁）。"""

    def __init__(self, config_path: str, bridge: Any,
                 logger: Any = None):
        self.config_path = os.path.abspath(config_path)
        self.bridge = bridge
        self.log = logger or (lambda *a: None)
        self._lock = threading.RLock()
        self._adapters: Dict[str, BaseAdapter] = {}      # id -> 运行中的适配器实例
        self._cfg: Dict[str, Any] = {"output": {}, "server": {}, "adapters": []}

    # ----------------------------- 持久化 -----------------------------
    def load_config(self) -> Dict[str, Any]:
        cfg: Dict[str, Any] = {"output": {}, "server": {}, "adapters": []}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f) or {}
            if isinstance(loaded, dict):
                cfg.update(loaded)
        except FileNotFoundError:
            pass
        except Exception as e:  # noqa: BLE001
            self.log("error", f"配置文件读取失败：{e}")
        if not isinstance(cfg.get("adapters"), list):
            cfg["adapters"] = []
        self._cfg = cfg
        return cfg

    def persist(self) -> None:
        with self._lock:
            cfg = json.loads(json.dumps(self._cfg))
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            tmp = self.config_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.config_path)
        except OSError as e:  # noqa: BLE001
            raise RuntimeError(f"配置写入失败：{e}") from e

    # ----------------------------- 启动/停止 -----------------------------
    def start_all(self) -> Dict[str, Any]:
        """加载配置并启动全部启用的适配器（进程启动时调用一次）。"""
        cfg = self.load_config()
        started, errors = [], []
        with self._lock:
            for item in cfg.get("adapters") or []:
                if item.get("enabled") is False:
                    continue
                try:
                    self._spawn(item)
                    started.append(item.get("id"))
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{item.get('id')}: {e}")
        return {"started": started, "errors": errors}

    def stop_all(self) -> None:
        with self._lock:
            for ad in list(self._adapters.values()):
                try:
                    ad.stop()
                except Exception:  # noqa: BLE001
                    pass
            self._adapters.clear()

    # ----------------------------- 内部：实例管理 -----------------------------
    def _spawn(self, cfg: Dict[str, Any]) -> BaseAdapter:
        """实例化并启动一个适配器（调用方持锁）。"""
        inst, errors = build(cfg, self.bridge, self.log)
        if inst is None:
            raise ValueError("；".join(errors) or "配置无效")
        inst.start()
        self._adapters[inst.id] = inst
        return inst

    def _kill(self, adapter_id: str) -> None:
        ad = self._adapters.pop(adapter_id, None)
        if ad is not None:
            try:
                ad.stop()
            except Exception:  # noqa: BLE001
                pass

    def _find_cfg(self, adapter_id: str) -> Optional[Dict[str, Any]]:
        for item in self._cfg.get("adapters") or []:
            if str(item.get("id")) == str(adapter_id):
                return item
        return None

    def _check_unique(self, cfg: Dict[str, Any], exclude_id: str = "") -> None:
        aid = str(cfg.get("id") or "")
        box = normalize_box(cfg.get("box"))
        if not aid:
            raise ValueError("数据源 id 不能为空")
        if not box:
            raise ValueError("发布前缀（box）不能为空，建议 ext- 开头，如 ext-weigh")
        if box in _RESERVED:
            raise ValueError(f"前缀「{box}」为保留名，请用 ext- 开头（如 ext-weigh）")
        if not _BOX_RE.match(box):
            raise ValueError("前缀仅允许小写字母/数字/连字符（如 ext-weigh）")
        for item in self._cfg.get("adapters") or []:
            if str(item.get("id")) == aid and str(item.get("id")) != exclude_id:
                raise ValueError(f"数据源 id「{aid}」已存在")
            if str(item.get("id")) == exclude_id:
                continue
            if normalize_box(item.get("box")) == box:
                raise ValueError(f"前缀「{box}」已被数据源「{item.get('name') or item.get('id')}」占用")

    # ----------------------------- CRUD -----------------------------
    def list(self) -> List[Dict[str, Any]]:
        """全部数据源（配置 + 运行状态）。"""
        with self._lock:
            out = []
            for item in self._cfg.get("adapters") or []:
                ad = self._adapters.get(str(item.get("id")))
                view = json.loads(json.dumps(item))
                view["status"] = ad.status() if ad is not None else {
                    "id": item.get("id"), "type": item.get("type"), "box": item.get("box"),
                    "running": False, "readings": 0, "skipped": 0, "errors": 0,
                    "last_at": None, "last_prop": None, "last_error": "",
                }
                out.append(view)
            return out

    def get(self, adapter_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            item = self._find_cfg(adapter_id)
            if item is None:
                return None
            ad = self._adapters.get(str(adapter_id))
            view = json.loads(json.dumps(item))
            view["status"] = ad.status() if ad is not None else {"running": False}
            return view

    def add(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        """注册一条数据源；校验通过即热启动并持久化。"""
        if not isinstance(cfg, dict):
            raise ValueError("数据源配置必须是 JSON 对象")
        item = json.loads(json.dumps(cfg))
        item["id"] = str(item.get("id") or "").strip() or new_id()
        item["box"] = normalize_box(item.get("box"))
        item["type"] = str(item.get("type") or "").strip()
        item["name"] = str(item.get("name") or "").strip() or item["id"]
        item["enabled"] = bool(item.get("enabled"))
        item["created_at"] = time.time()
        with self._lock:
            self._check_unique(item)
            if item["enabled"]:
                self._spawn(item)   # 配置非法在此抛出，不落盘
            self._cfg.setdefault("adapters", []).append(item)
            self.persist()
        self.log("info", f"数据源已注册：{item['id']}（{item['type']}，box={item['box']}）")
        return self.get(item["id"]) or item

    def update(self, adapter_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        """局部更新一条数据源（改名/改参数/改前缀）；改配置会热重启适配器。"""
        if not isinstance(patch, dict):
            raise ValueError("更新内容必须是 JSON 对象")
        with self._lock:
            item = self._find_cfg(adapter_id)
            if item is None:
                raise ValueError(f"数据源不存在：{adapter_id}")
            merged = json.loads(json.dumps(item))
            for k, v in patch.items():
                if k in ("id", "created_at"):
                    continue
                merged[k] = v
            if "box" in patch:
                merged["box"] = normalize_box(patch["box"])
            merged["type"] = str(merged.get("type") or item.get("type") or "").strip()
            merged["updated_at"] = time.time()
            self._check_unique(merged, exclude_id=str(adapter_id))
            # 先停旧的，再按新配置启动（失败则不落盘且旧实例也停 → 状态可见）
            self._kill(str(adapter_id))
            if merged.get("enabled") is not False:
                self._spawn(merged)
            for i, x in enumerate(self._cfg.get("adapters") or []):
                if str(x.get("id")) == str(adapter_id):
                    self._cfg["adapters"][i] = merged
                    break
            self.persist()
        return self.get(adapter_id) or merged

    def remove(self, adapter_id: str) -> None:
        with self._lock:
            item = self._find_cfg(adapter_id)
            if item is None:
                raise ValueError(f"数据源不存在：{adapter_id}")
            self._kill(str(adapter_id))
            self._cfg["adapters"] = [x for x in (self._cfg.get("adapters") or [])
                                     if str(x.get("id")) != str(adapter_id)]
            self.persist()
        self.log("info", f"数据源已删除：{adapter_id}")

    def set_enabled(self, adapter_id: str, enabled: bool) -> Dict[str, Any]:
        """启停一条数据源（停用即停止采集；启用即重新采集）。"""
        with self._lock:
            item = self._find_cfg(adapter_id)
            if item is None:
                raise ValueError(f"数据源不存在：{adapter_id}")
            enabled = bool(enabled)
            item["enabled"] = enabled
            self._kill(str(adapter_id))
            if enabled:
                self._spawn(item)
            self.persist()
        self.log("info", f"数据源已{'启用' if enabled else '停用'}：{adapter_id}")
        return self.get(adapter_id) or item

    # ----------------------------- 连通性测试 -----------------------------
    def test(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        """按给定配置做连通性/配置自检（不落盘、不启动）。"""
        if not isinstance(cfg, dict):
            raise ValueError("测试内容必须是 JSON 对象")
        probe = json.loads(json.dumps(cfg))
        probe.setdefault("id", "probe")
        probe["box"] = normalize_box(probe.get("box")) or "probe-box"
        inst, errors = build(probe, self.bridge, self.log)
        if inst is None:
            return {"ok": False, "message": "；".join(errors) or "配置无效"}
        try:
            res = inst.test()
        except Exception as e:  # noqa: BLE001
            res = {"ok": False, "message": f"测试异常：{e}"}
        finally:
            try:
                inst.stop()
            except Exception:  # noqa: BLE001
                pass
        return res

    # ----------------------------- 元信息 -----------------------------
    @staticmethod
    def types() -> List[Dict[str, Any]]:
        return type_catalog()

    def by_box(self, box: str) -> Optional[Dict[str, Any]]:
        b = normalize_box(box)
        with self._lock:
            for item in self._cfg.get("adapters") or []:
                if normalize_box(item.get("box")) == b:
                    return json.loads(json.dumps(item))
        return None


def new_id() -> str:
    return "ext_" + uuid.uuid4().hex[:6]
