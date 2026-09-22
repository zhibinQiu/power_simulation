"""工序设备规格档位库。

为「不同规格的同类设备」提供仿真适配：同一工序类型（如高炉）可定义多个
规格档位（小型/中型/大型），每个档位携带：
  - defaults      ：默认参数覆盖（决定该规格设备的额定运行点，引擎仿真基准）
  - ranges        ：参数运行空间覆盖（min/max/step，编辑器可调范围）
  - device_ranges ：设备量程覆盖（该规格设备配套量程，可空）

前端在流程编排中为工序节点选择规格（Unit.spec 携带规格 key）；
引擎 simulate() 按规格默认参数覆盖 DEFAULT_PARAMS（用户显式参数仍最后覆盖），
实现同类型不同规格设备各自的仿真结果。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# 工序 -> 规格档位列表（key 稳定，供前端选择器与引擎查询）
PROCESS_SPECS: Dict[str, List[Dict[str, Any]]] = {
    # —— 炼铁 · 高炉（按有效容积分档）——
    "blast_furnace": [
        {
            "key": "bf_1000",
            "label": "小型高炉（1000m³级）",
            "desc": "适合 300 万吨/年以下产线，铁水产量偏低、焦比偏高",
            "defaults": {"hot_metal": 500, "coke_rate": 510, "coal_inj": 140, "flux": 130, "slag_rate": 300},
            "ranges": {"hot_metal": {"min": 250, "max": 900, "step": 50}},
            "device_ranges": {"belt_scale": {"min": 0, "max": 600}},
        },
        {
            "key": "bf_2000",
            "label": "中型高炉（2000m³级）",
            "desc": "主流配置，铁水产量与焦比均衡",
            "defaults": {"hot_metal": 800, "coke_rate": 485, "coal_inj": 150, "flux": 120, "slag_rate": 300},
            "ranges": {"hot_metal": {"min": 500, "max": 1400, "step": 50}},
            "device_ranges": {"belt_scale": {"min": 0, "max": 900}},
        },
        {
            "key": "bf_3200",
            "label": "大型高炉（3200m³级）",
            "desc": "大型产线主力炉，产量高、焦比低",
            "defaults": {"hot_metal": 1200, "coke_rate": 465, "coal_inj": 155, "flux": 110, "slag_rate": 300},
            "ranges": {"hot_metal": {"min": 800, "max": 1800, "step": 50}},
            "device_ranges": {"belt_scale": {"min": 0, "max": 1400}},
        },
    ],
    # —— 原料准备 ——
    "sinter_plant": [
        {
            "key": "sp_90",
            "label": "烧结机 90m²",
            "desc": "小型烧结机，矿量低",
            "defaults": {"ore_rate": 550, "fuel_rate": 52, "electricity": 22.0},
            "ranges": {"ore_rate": {"min": 300, "max": 900, "step": 50}},
        },
        {
            "key": "sp_180",
            "label": "烧结机 180m²",
            "desc": "主流中型烧结机",
            "defaults": {"ore_rate": 1100, "fuel_rate": 47, "electricity": 44.0},
            "ranges": {"ore_rate": {"min": 700, "max": 1700, "step": 50}},
        },
        {
            "key": "sp_360",
            "label": "烧结机 360m²",
            "desc": "大型烧结机，矿量大、燃耗低",
            "defaults": {"ore_rate": 1750, "fuel_rate": 44, "electricity": 70.0},
            "ranges": {"ore_rate": {"min": 1300, "max": 2300, "step": 50}},
        },
    ],
    "coke_oven": [
        {
            "key": "co_60",
            "label": "焦炉 60 孔",
            "desc": "小型焦炉组",
            "defaults": {"coal_rate": 300, "electricity": 6.0},
            "ranges": {"coal_rate": {"min": 200, "max": 500, "step": 50}},
        },
        {
            "key": "co_120",
            "label": "焦炉 120 孔",
            "desc": "主流焦炉组",
            "defaults": {"coal_rate": 500, "electricity": 10.0},
            "ranges": {"coal_rate": {"min": 350, "max": 750, "step": 50}},
        },
    ],
    # —— 炼钢 ——
    "bof": [
        {
            "key": "bof_120",
            "label": "转炉 120t",
            "desc": "小型转炉",
            "defaults": {"hot_metal_in": 500, "scrap": 60, "flux": 65, "slag_rate": 120},
            "ranges": {"hot_metal_in": {"min": 300, "max": 900, "step": 50}},
        },
        {
            "key": "bof_250",
            "label": "转炉 250t",
            "desc": "主流大型转炉",
            "defaults": {"hot_metal_in": 1000, "scrap": 110, "flux": 58, "slag_rate": 120},
            "ranges": {"hot_metal_in": {"min": 700, "max": 1500, "step": 50}},
        },
    ],
    "eaf": [
        {
            "key": "eaf_70",
            "label": "电炉 70t",
            "desc": "小型电弧炉（短流程）",
            "defaults": {"scrap": 450, "dri": 0, "electricity": 180.0, "electrode": 0.9},
            "ranges": {"scrap": {"min": 250, "max": 650, "step": 50}},
        },
        {
            "key": "eaf_150",
            "label": "电炉 150t",
            "desc": "主流电弧炉（短流程）",
            "defaults": {"scrap": 900, "dri": 0, "electricity": 360.0, "electrode": 1.8},
            "ranges": {"scrap": {"min": 600, "max": 1200, "step": 50}},
        },
    ],
    # —— 连铸 ——
    "caster": [
        {
            "key": "cc_1",
            "label": "连铸机 1 机 1 流",
            "desc": "小型连铸",
            "defaults": {"steel_in": 500, "electricity": 7.5},
            "ranges": {"steel_in": {"min": 300, "max": 800, "step": 50}},
        },
        {
            "key": "cc_2",
            "label": "连铸机 2 机 2 流",
            "desc": "主流连铸配置",
            "defaults": {"steel_in": 1000, "electricity": 15.0},
            "ranges": {"steel_in": {"min": 700, "max": 1500, "step": 50}},
        },
    ],
    # —— 轧制 ——
    "rolling_mill": [
        {
            "key": "rm_1780",
            "label": "热轧 1780 线",
            "desc": "主流热轧产线",
            "defaults": {"steel_in": 1000, "ng_rate": 32, "electricity": 80.0},
            "ranges": {"steel_in": {"min": 700, "max": 1500, "step": 50}},
        },
        {
            "key": "rm_2250",
            "label": "热轧 2250 线",
            "desc": "大型热轧产线",
            "defaults": {"steel_in": 1400, "ng_rate": 30, "electricity": 112.0},
            "ranges": {"steel_in": {"min": 1000, "max": 1900, "step": 50}},
        },
    ],
}


def spec_by_key(ut: str, key: str) -> Optional[Dict[str, Any]]:
    """按规格 key 查找档位；找不到返回 None。"""
    if not key:
        return None
    for s in PROCESS_SPECS.get(ut, []):
        if s["key"] == key:
            return s
    return None


def spec_defaults(ut: str, key: str) -> Dict[str, Any]:
    """返回规格档位的默认参数覆盖；无规格/未命中时返回空字典。"""
    s = spec_by_key(ut, key)
    return dict(s.get("defaults", {})) if s else {}
