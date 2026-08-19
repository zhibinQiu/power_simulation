"""工序参数分级元数据（单一事实来源）。

把每个工序的「可编辑参数」标注为两类：
  - kind="config" 因变量/给定约束：由工厂既定条件决定（产量规模、焦比、喷煤比、
    熔剂比、燃料比、电耗基线等）。提供「参考范围」，但不在自动策略优化范围内——
    即它们是需要如实填入的已知条件，而不是用来"求解"的杠杆。
  - kind="optim"  自变量/节能减排决策变量：会直接影响能耗与碳排的操作/配比杠杆
    （废钢比、氢比、天然气/能源配比、生物质替代比等）。这是策略优化与 LLM 拆解时
    优先建议调整的旋钮。

本文件同时供：
  - 前端 /api/param-schema 拉取，渲染「流程编排」参数编辑器（分组 + 参考范围）；
  - 后端 LLM 提示词构建，让大模型知道有哪些可调参数及其单位/范围。
"""
from __future__ import annotations

from typing import Dict, List

from .carbon_engine import UNIT_META

# 减排技术 id -> 中文标签（供 LLM 提示词 & 前端）
TECHS_INFO = [
    {"tech": "ccs", "label": "碳捕集(CCS)"},
    {"tech": "waste_heat", "label": "余热回收"},
    {"tech": "h2_inj", "label": "富氢喷吹"},
]

# 工序类型 id -> 中文标签（供 LLM 提示词）
UNIT_TYPES_INFO = [
    {"type": tid, "label": meta.get("label", tid), "cat": meta.get("cat", "")}
    for tid, meta in UNIT_META.items()
]

# 参数分级表。字段：key/label/unit/min/max/step/kind/ref
#   kind: "config" | "optim"
#   ref : 参考范围说明（人类可读）
PARAM_SCHEMA: Dict[str, List[Dict]] = {
    # —— 原料准备 ——
    "sinter_plant": [
        {"key": "ore_rate", "label": "矿量", "unit": "t/h", "min": 1000, "max": 15000, "step": 200, "kind": "config", "ref": "烧结规模给定"},
        {"key": "fuel_rate", "label": "燃料比", "unit": "kg/t", "min": 20, "max": 80, "step": 1, "kind": "config", "ref": "典型 40–55 kg/t"},
        {"key": "electricity", "label": "电耗", "unit": "MWh/h", "min": 1, "max": 20, "step": 0.5, "kind": "config", "ref": "设备额定（缺省按规模估算）"},
    ],
    "pelletizing": [
        {"key": "ore_rate", "label": "矿量", "unit": "t/h", "min": 500, "max": 8000, "step": 100, "kind": "config", "ref": "球团规模给定"},
        {"key": "fuel_rate", "label": "燃料比", "unit": "kg/t", "min": 5, "max": 40, "step": 1, "kind": "config", "ref": "典型 15–25 kg/t"},
        {"key": "electricity", "label": "电耗", "unit": "MWh/h", "min": 1, "max": 20, "step": 0.5, "kind": "config", "ref": "设备额定（缺省按规模估算）"},
    ],
    "coke_oven": [
        {"key": "coal_rate", "label": "入炉煤", "unit": "t/h", "min": 500, "max": 8000, "step": 100, "kind": "config", "ref": "焦化规模给定"},
        {"key": "electricity", "label": "电耗", "unit": "MWh/h", "min": 1, "max": 20, "step": 0.5, "kind": "config", "ref": "设备额定（缺省按规模估算）"},
    ],
    "reheating_furnace": [
        {"key": "steel_in", "label": "钢水量", "unit": "t/h", "min": 1000, "max": 12000, "step": 100, "kind": "config", "ref": "处理规模给定"},
        {"key": "ng_rate", "label": "天然气", "unit": "m³/t", "min": 0, "max": 120, "step": 2, "kind": "config", "ref": "加热炉设计值"},
        {"key": "electricity", "label": "电耗", "unit": "MWh/h", "min": 1, "max": 20, "step": 0.5, "kind": "config", "ref": "设备额定"},
    ],
    # —— 炼铁 ——
    "blast_furnace": [
        {"key": "hot_metal", "label": "铁水产量", "unit": "t/h", "min": 2000, "max": 12000, "step": 100, "kind": "config", "ref": "高炉规模给定"},
        {"key": "coke_rate", "label": "焦比", "unit": "kg/t", "min": 250, "max": 550, "step": 5, "kind": "config", "ref": "典型 470–530 kg/t（直接调参模式·给定约束）"},
        {"key": "coal_inj", "label": "喷煤比", "unit": "kg/t", "min": 0, "max": 250, "step": 5, "kind": "config", "ref": "典型 120–180 kg/t（直接调参模式·给定约束）"},
        {"key": "flux", "label": "熔剂比", "unit": "kg/t", "min": 0, "max": 250, "step": 5, "kind": "config", "ref": "典型 60–150 kg/t"},
        {"key": "wind_rate", "label": "风量", "unit": "kNm³/h", "min": 100, "max": 900, "step": 10, "kind": "optim", "ref": "实际供风量·提升喷煤能力→焦比↓（设备/操作驱动）"},
        {"key": "hot_blast_temp", "label": "热风温度", "unit": "℃", "min": 950, "max": 1300, "step": 10, "kind": "optim", "ref": "鼓风温度·提升热效率→焦比↓（设备/操作驱动）"},
        {"key": "oxygen_enrich", "label": "富氧率", "unit": "%", "min": 0, "max": 14, "step": 0.5, "kind": "optim", "ref": "鼓风富氧增量(相对空气 21%)·提升喷煤→焦比↓（设备/操作驱动）"},
    ],
    "hydrogen_bf": [
        {"key": "hot_metal", "label": "铁水产量", "unit": "t/h", "min": 2000, "max": 12000, "step": 100, "kind": "config", "ref": "规模给定"},
        {"key": "h2_rate", "label": "氢耗", "unit": "kg/t", "min": 0, "max": 200, "step": 5, "kind": "optim", "ref": "氢替代比例·影响直接碳排（决策变量）"},
        {"key": "electricity", "label": "制氢电耗", "unit": "MWh/h", "min": 100, "max": 1200, "step": 20, "kind": "config", "ref": "由氢耗与电源结构决定"},
    ],
    "h2_dri": [
        {"key": "dri_out", "label": "DRI产量", "unit": "t/h", "min": 1000, "max": 12000, "step": 200, "kind": "config", "ref": "规模给定"},
        {"key": "h2_rate", "label": "氢耗", "unit": "kg/t", "min": 0, "max": 200, "step": 5, "kind": "optim", "ref": "氢替代比例·深度脱碳杠杆（决策变量）"},
        {"key": "electricity", "label": "制氢电耗", "unit": "MWh/h", "min": 100, "max": 1200, "step": 20, "kind": "config", "ref": "由电源结构决定"},
    ],
    "dri_midrex": [
        {"key": "pellet_rate", "label": "球团矿量", "unit": "t/h", "min": 1000, "max": 12000, "step": 200, "kind": "config", "ref": "规模给定"},
        {"key": "ng_rate", "label": "天然气", "unit": "m³/t", "min": 0, "max": 400, "step": 10, "kind": "optim", "ref": "天然气→可切换绿氢的能源配比杠杆（决策变量）"},
        {"key": "electricity", "label": "电耗", "unit": "MWh/h", "min": 1, "max": 30, "step": 0.5, "kind": "config", "ref": "设备额定"},
    ],
    "smelting_reduction": [
        {"key": "ore_rate", "label": "矿量", "unit": "t/h", "min": 1000, "max": 12000, "step": 200, "kind": "config", "ref": "规模给定"},
        {"key": "coal_rate", "label": "非炼焦煤", "unit": "t/h", "min": 100, "max": 2000, "step": 50, "kind": "config", "ref": "燃料设计值"},
        {"key": "electricity", "label": "电耗", "unit": "MWh/h", "min": 1, "max": 30, "step": 0.5, "kind": "config", "ref": "设备额定"},
    ],
    "biochar_injection": [
        {"key": "biomass_rate", "label": "生物质碳", "unit": "t/h", "min": 0, "max": 1000, "step": 20, "kind": "optim", "ref": "碳中性替代比例·抵消化石碳（决策变量）"},
        {"key": "electricity", "label": "电耗", "unit": "MWh/h", "min": 0, "max": 10, "step": 0.5, "kind": "config", "ref": "设备额定"},
    ],
    # —— 炼钢 ——
    "bof": [
        {"key": "hot_metal_in", "label": "铁水入炉", "unit": "t/h", "min": 2000, "max": 12000, "step": 100, "kind": "config", "ref": "上游铁水量给定"},
        {"key": "scrap", "label": "废钢", "unit": "t/h", "min": 0, "max": 3000, "step": 100, "kind": "optim", "ref": "废钢比·提高可降单位碳排（决策变量）"},
        {"key": "flux", "label": "熔剂比", "unit": "kg/t", "min": 0, "max": 150, "step": 5, "kind": "config", "ref": "典型 40–80 kg/t"},
    ],
    "eaf": [
        {"key": "scrap", "label": "废钢", "unit": "t/h", "min": 0, "max": 12000, "step": 100, "kind": "optim", "ref": "废钢比·短流程核心降碳杠杆（决策变量）"},
        {"key": "dri", "label": "DRI", "unit": "t/h", "min": 0, "max": 6000, "step": 100, "kind": "optim", "ref": "原料配比·搭配绿氢 DRI 可近零碳（决策变量）"},
        {"key": "electricity", "label": "电耗", "unit": "MWh/h", "min": 50, "max": 800, "step": 10, "kind": "config", "ref": "由电源结构决定"},
    ],
    # —— 精炼 ——
    "ladle_furnace": [
        {"key": "steel_in", "label": "钢水量", "unit": "t/h", "min": 1000, "max": 12000, "step": 100, "kind": "config", "ref": "处理规模给定"},
        {"key": "electricity", "label": "电耗", "unit": "MWh/h", "min": 1, "max": 20, "step": 0.5, "kind": "config", "ref": "设备额定"},
    ],
    "rh_vacuum": [
        {"key": "steel_in", "label": "钢水量", "unit": "t/h", "min": 1000, "max": 12000, "step": 100, "kind": "config", "ref": "处理规模给定"},
        {"key": "electricity", "label": "电耗", "unit": "MWh/h", "min": 1, "max": 20, "step": 0.5, "kind": "config", "ref": "设备额定"},
    ],
    "vd_vacuum": [
        {"key": "steel_in", "label": "钢水量", "unit": "t/h", "min": 1000, "max": 12000, "step": 100, "kind": "config", "ref": "处理规模给定"},
        {"key": "electricity", "label": "电耗", "unit": "MWh/h", "min": 1, "max": 20, "step": 0.5, "kind": "config", "ref": "设备额定"},
    ],
    "aod": [
        {"key": "steel_in", "label": "钢水量", "unit": "t/h", "min": 1000, "max": 12000, "step": 100, "kind": "config", "ref": "处理规模给定"},
        {"key": "electricity", "label": "电耗", "unit": "MWh/h", "min": 1, "max": 20, "step": 0.5, "kind": "config", "ref": "设备额定"},
    ],
    # —— 连铸 ——
    "caster": [
        {"key": "steel_in", "label": "钢水量", "unit": "t/h", "min": 1000, "max": 12000, "step": 100, "kind": "config", "ref": "处理规模给定"},
        {"key": "electricity", "label": "电耗", "unit": "MWh/h", "min": 1, "max": 20, "step": 0.5, "kind": "config", "ref": "设备额定（缺省按规模估算）"},
    ],
    "ingot_casting": [
        {"key": "steel_in", "label": "钢水量", "unit": "t/h", "min": 1000, "max": 12000, "step": 100, "kind": "config", "ref": "处理规模给定"},
        {"key": "ng_rate", "label": "保温燃气", "unit": "m³/t", "min": 0, "max": 80, "step": 2, "kind": "config", "ref": "均热炉设计值"},
        {"key": "electricity", "label": "电耗", "unit": "MWh/h", "min": 1, "max": 20, "step": 0.5, "kind": "config", "ref": "设备额定"},
    ],
    # —— 轧制 ——
    "rolling_mill": [
        {"key": "steel_in", "label": "钢水量", "unit": "t/h", "min": 1000, "max": 12000, "step": 100, "kind": "config", "ref": "处理规模给定"},
        {"key": "ng_rate", "label": "天然气", "unit": "m³/t", "min": 0, "max": 80, "step": 2, "kind": "config", "ref": "退火炉设计值"},
        {"key": "electricity", "label": "电耗", "unit": "MWh/h", "min": 1, "max": 20, "step": 0.5, "kind": "config", "ref": "设备额定"},
    ],
    "cold_rolling": [
        {"key": "steel_in", "label": "钢水量", "unit": "t/h", "min": 1000, "max": 12000, "step": 100, "kind": "config", "ref": "处理规模给定"},
        {"key": "ng_rate", "label": "退火燃气", "unit": "m³/t", "min": 0, "max": 80, "step": 2, "kind": "config", "ref": "退火炉设计值"},
        {"key": "electricity", "label": "电耗", "unit": "MWh/h", "min": 1, "max": 20, "step": 0.5, "kind": "config", "ref": "设备额定"},
    ],
}
