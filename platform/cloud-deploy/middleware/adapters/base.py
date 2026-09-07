"""适配器基类：任何「外部数据形态」→ 标准读数事件的统一入口。

子类实现 start()（采集循环/订阅），通过 emit / emit_flat 把读数交给输出桥，
由 bridge 按平台标准规范发布（topic/payload/前缀规则集中在一处）。
"""
from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional

from middleware.bridge import normalize_ts, now_ms

# 消息里可能承载设备 id 的字段（按顺序取第一个非空）
DEFAULT_DEVICE_KEYS = ("device", "deviceId", "device_id", "sensor", "devId", "id")

# 时间字段候选（秒或毫秒皆可，发布前归一）
DEFAULT_TS_KEYS = ("ts", "timestamp", "time", "millis")


def numeric(value: Any) -> Optional[float]:
    """字符串→数值尽力转换；无法解析/布尔/None/NaN/inf 返回 None。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, (int, float)):
            v = float(value)
        elif isinstance(value, str):
            s = value.strip()
            if not s:
                return None
            v = float(s)
        else:
            return None
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


class BaseAdapter:
    """采集适配器基类。cfg 至少含 id/type/box；可选 enabled/device/fieldMap。"""

    def __init__(self, cfg: Dict[str, Any], bridge: Any, logger: Any = None):
        self.cfg = cfg or {}
        self.bridge = bridge
        self.id = str(self.cfg.get("id") or "adapter")
        self.type = str(self.cfg.get("type") or "?")
        self.name = str(self.cfg.get("name") or self.id)
        self.box = str((self.cfg.get("box") or "").strip().lower())
        self.device_keys = list(self.cfg.get("deviceKeys") or DEFAULT_DEVICE_KEYS)
        self.ts_keys = list(self.cfg.get("timeKeys") or DEFAULT_TS_KEYS)
        self.field_map = {str(k).strip(): str(v).strip()
                          for k, v in (self.cfg.get("fieldMap") or {}).items()
                          if str(k).strip() and str(v).strip()}
        self.log = logger or (lambda *a: None)
        self.running = False
        self.stats: Dict[str, Any] = {
            "started_at": None, "readings": 0, "skipped": 0, "errors": 0,
            "last_at": None, "last_prop": None, "last_error": "",
        }

    # ---- 校验 ----
    def validate(self) -> List[str]:
        errors = []
        if not self.id:
            errors.append("adapter.id 不能为空")
        if not self.box:
            errors.append(f"adapter[{self.id}].box 不能为空（须与平台登记的外部源前缀一致，如 ext-weigh）")
        if not self.box.replace("-", "").replace("_", "").isalnum():
            errors.append(f"adapter[{self.id}].box「{self.box}」仅允许小写字母/数字/连字符")
        if not self.device_keys and not self.cfg.get("device"):
            errors.append(f"adapter[{self.id}] 缺少默认 device 且未配置 deviceKeys")
        return errors

    # ---- 读数出口 ----
    def emit(self, prop: str, value: Any,
             device: Optional[str] = None, ts: Optional[Any] = None) -> bool:
        """发布一条读数。非数值自动跳过（计 skipped）。"""
        v = numeric(value)
        dev = str(device or self.cfg.get("device") or "").strip()
        p = str(prop or "").strip()
        if not p:
            return False
        if v is None:
            self.stats["skipped"] += 1
            return False
        if not dev:
            self.stats["skipped"] += 1
            self.stats["last_error"] = f"消息缺 device，已跳过属性 {p}"
            return False
        ok = self.bridge.publish(self.box, dev, self.field_map.get(p, p),
                                 v, normalize_ts(ts))
        self.stats["readings"] += 1
        self.stats["last_at"] = time.time()
        self.stats["last_prop"] = p
        return ok

    def emit_flat(self, obj: Dict[str, Any],
                  device: Optional[str] = None, ts: Optional[Any] = None) -> int:
        """把外部消息（JSON 对象）展平后逐数值字段发布；返回发布条数。

        - 嵌套 dict 递归展平为 a.b；
        - 设备 id 优先取消息里 deviceKeys 字段，其次调用方传入的 device，
          再其次配置默认 device；
        - 时间取消息 ts 类字段，其次参数 ts，再其次当前时刻；
        - fieldMap 在发布时自动改名（emit 内完成）。
        """
        if not isinstance(obj, dict):
            return 0
        flat = flatten(obj)
        # 时间/设备字段只作来源元数据，不作为数值属性发布
        for k in set(self.ts_keys) | set(self.device_keys):
            flat.pop(k, None)
        dev = device or self._pick_device(obj)
        ts_v = ts if ts is not None else self._pick_ts(obj)
        n = 0
        for key, val in flat.items():
            if self.emit(key, val, device=dev, ts=ts_v):
                n += 1
        return n

    def _pick_device(self, obj: Dict[str, Any]) -> Optional[str]:
        for k in self.device_keys:
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
            if isinstance(v, (int, float)):
                return str(v)
        return None

    def _pick_ts(self, obj: Dict[str, Any]) -> Optional[Any]:
        for k in self.ts_keys:
            v = obj.get(k)
            if isinstance(v, (int, float, str)) and str(v).strip():
                return v
        return None

    # ---- 连通性自检（平台「测试连接」按钮调用）----
    def test(self) -> Dict[str, Any]:
        """校验配置并探测外部可达性；返回 {ok, message}。默认只做配置校验。"""
        errors = self.validate()
        if errors:
            return {"ok": False, "message": "；".join(errors)}
        return {"ok": True, "message": "配置校验通过（该类型无外部连接可探测）"}

    # ---- 生命周期 ----
    def start(self) -> None:
        raise NotImplementedError

    def request_stop(self) -> None:
        self.running = False

    def stop(self) -> None:
        self.request_stop()

    def status(self) -> Dict[str, Any]:
        return {
            "id": self.id, "type": self.type, "name": self.name,
            "box": self.box, "running": self.running,
            **{k: self.stats[k] for k in ("readings", "skipped", "errors",
                                          "last_at", "last_prop", "last_error")},
        }


def flatten(obj: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    """递归展平嵌套 dict：{"a": {"b": 1}} → {"a.b": 1}。列表原样保留（忽略）。"""
    out: Dict[str, Any] = {}
    for k, v in obj.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(flatten(v, key))
        else:
            out[key] = v
    return out
