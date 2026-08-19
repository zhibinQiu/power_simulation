"""平台可配置项（工艺规模档位、设备量程、参数运行空间）。

为不同钢厂/产线提供通用性：管理员可通过「平台配置」面板调整
  - process_scales（工艺规模档位）：各工序规模参数（产量/入炉量）的 min/max/step + 档位预设
  - device_ranges（设备量程）：各设备类型的量程 min/max/unit
  - param_ranges（参数运行空间）：各工序参数的 min/max/step

配置持久化到 backend/platform_config.json（仅存用户覆盖项），
GET /api/param-schema 与 /api/devices 返回时叠加用户配置，
前端编辑器 / 设备面板 / 3D 标注自动使用配置后的范围。
"""
from __future__ import annotations

import copy
import json
import os
import re
from typing import Any, Dict, Optional

from .param_schema import PARAM_SCHEMA
from .devices import DEVICE_LIBRARY, library_payload
from .specs import PROCESS_SPECS

_DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "platform_config.json")

# 每个工序的「规模参数」key（产量/入炉量，决定产线规模档位）
PROCESS_SCALE_KEYS: Dict[str, str] = {
    "sinter_plant": "ore_rate",
    "pelletizing": "ore_rate",
    "coke_oven": "coal_rate",
    "reheating_furnace": "steel_in",
    "blast_furnace": "hot_metal",
    "hydrogen_bf": "hot_metal",
    "h2_dri": "dri_out",
    "dri_midrex": "pellet_rate",
    "smelting_reduction": "ore_rate",
    "biochar_injection": "biomass_rate",
    "bof": "hot_metal_in",
    "eaf": "scrap",
    "ladle_furnace": "steel_in",
    "rh_vacuum": "steel_in",
    "vd_vacuum": "steel_in",
    "aod": "steel_in",
    "caster": "steel_in",
    "ingot_casting": "steel_in",
    "rolling_mill": "steel_in",
    "cold_rolling": "steel_in",
}

# 量程字符串解析：如 "0–6000 t/h"、"0–5e6 m³/h"、"—"
_RANGE_RE = re.compile(r"^([\d.eE+\-]+)\s*[–—-]\s*([\d.eE+\-]+)\s*(.*)$")


def _parse_range(s: str):
    """把设备库量程字符串解析为 (min, max, unit)；无法解析时返回 (None, None, "")。"""
    if not s or str(s).strip() in ("—", "-"):
        return None, None, ""
    m = _RANGE_RE.match(str(s).strip())
    if not m:
        return None, None, ""
    try:
        return float(m.group(1)), float(m.group(2)), m.group(3).strip()
    except ValueError:
        return None, None, ""


def _fmt_num(v) -> str:
    if v is None:
        return "—"
    f = float(v)
    if abs(f - round(f)) < 1e-9:
        return str(int(round(f)))
    return f"{f:g}"


def _fmt_range(mn, mx, unit: str = "") -> str:
    if mn is None or mx is None:
        return "—"
    s = f"{_fmt_num(mn)}–{_fmt_num(mx)}"
    if unit:
        s += " " + unit
    return s


def _default_process_scales() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for ut, key in PROCESS_SCALE_KEYS.items():
        for p in PARAM_SCHEMA.get(ut, []):
            if p["key"] == key:
                out[ut] = {
                    "key": key,
                    "label": p.get("label", key),
                    "unit": p.get("unit", ""),
                    "min": p.get("min", 0),
                    "max": p.get("max", 100),
                    "step": p.get("step", 1),
                }
                break
    return out


def _default_device_ranges() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for dev, meta in DEVICE_LIBRARY.items():
        mn, mx, unit = _parse_range(meta.get("range", ""))
        out[dev] = {
            "label": meta.get("label", dev),
            "unit": meta.get("unit", "") or unit,
            "min": mn,
            "max": mx,
        }
    return out


def _default_param_ranges() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for ut, params in PARAM_SCHEMA.items():
        out[ut] = {}
        for p in params:
            out[ut][p["key"]] = {
                "min": p.get("min", 0),
                "max": p.get("max", 100),
                "step": p.get("step", 1),
            }
    return out


def default_config() -> Dict[str, Any]:
    """内置默认配置（与平台出厂值一致）。"""
    return {
        "process_scales": _default_process_scales(),
        "device_ranges": _default_device_ranges(),
        "param_ranges": _default_param_ranges(),
    }


def _merge(defaults, overrides):
    if not isinstance(overrides, dict):
        return defaults
    out = copy.deepcopy(defaults)
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class PlatformConfigStore:
    """平台可配置项存储：仅持久化用户覆盖项，读取时与默认值合并。"""

    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self):
        try:
            if os.path.exists(_DATA_FILE):
                with open(_DATA_FILE, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
        except Exception:
            self._data = {}

    def _save(self):
        try:
            with open(_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def effective(self) -> Dict[str, Any]:
        return _merge(default_config(), self._data)

    def save(self, cfg: Optional[Dict[str, Any]] = None):
        """保存用户配置（缺省为空 → 恢复默认）。"""
        self._data = cfg or {}
        self._save()

    def reset(self):
        self._data = {}
        self._save()


config = PlatformConfigStore()


def _with_tiers(scales: Dict[str, Any]) -> Dict[str, Any]:
    """为每个工艺规模附加「小型/中型/大型」档位预设（按默认范围三等分）。"""
    out = copy.deepcopy(scales)
    for ut, s in out.items():
        mn, mx = float(s.get("min", 0)), float(s.get("max", 100))
        span = (mx - mn) / 3.0
        s["tiers"] = [
            {"id": "small", "label": "小型", "min": round(mn, 2), "max": round(mn + span, 2)},
            {"id": "mid", "label": "中型", "min": round(mn + span, 2), "max": round(mn + 2 * span, 2)},
            {"id": "large", "label": "大型", "min": round(mn + 2 * span, 2), "max": round(mx, 2)},
        ]
    return out


def config_payload() -> Dict[str, Any]:
    """供 /api/platform-config 使用的完整负载（含档位预设，可直接渲染面板）。"""
    cfg = config.effective()
    cfg = copy.deepcopy(cfg)
    cfg["process_scales"] = _with_tiers(cfg["process_scales"])
    # 工序设备规格档位库（内置，供前端规格选择器与范围/量程联动）
    cfg["process_specs"] = PROCESS_SPECS
    return cfg


def save_config(cfg: Optional[Dict[str, Any]] = None):
    config.save(cfg)


def reset_config():
    config.reset()


def apply_to_schema() -> Dict[str, Any]:
    """返回叠加用户配置后的 PARAM_SCHEMA（副本），min/max/step 被覆盖。

    覆盖来源：param_ranges（参数运行空间）+ process_scales（工艺规模档位，
    会同步到对应规模参数，保证高炉规模等档位生效）。
    """
    cfg = config.effective()
    pr = copy.deepcopy(cfg.get("param_ranges", {}))
    # 工艺规模档位 → 同步覆盖到对应规模参数的运行空间
    for ut, s in cfg.get("process_scales", {}).items():
        key = s.get("key")
        if not key:
            continue
        pr.setdefault(ut, {})[key] = {
            "min": s.get("min"),
            "max": s.get("max"),
            "step": s.get("step"),
        }
    schema = copy.deepcopy(PARAM_SCHEMA)
    for ut, params in schema.items():
        overrides = pr.get(ut, {})
        for p in params:
            o = overrides.get(p["key"])
            if not o:
                continue
            if o.get("min") is not None:
                p["min"] = o["min"]
            if o.get("max") is not None:
                p["max"] = o["max"]
            if o.get("step") is not None:
                p["step"] = o["step"]
    return schema


def apply_to_devices() -> Dict[str, Any]:
    """返回叠加用户配置后的设备库负载（副本），量程/单位被覆盖。"""
    payload = copy.deepcopy(library_payload())
    lib = payload.get("library", {})
    cfg = config.effective()
    dr = cfg.get("device_ranges", {})
    for dev, o in dr.items():
        meta = lib.get(dev)
        if not meta:
            continue
        mn, mx = o.get("min"), o.get("max")
        unit = o.get("unit")
        if mn is not None and mx is not None:
            meta["range"] = _fmt_range(mn, mx, unit or meta.get("unit", ""))
        if unit:
            meta["unit"] = unit
    return payload
