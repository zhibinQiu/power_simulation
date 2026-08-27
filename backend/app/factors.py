"""排放因子与计算原语层（共享常量 + 基础算法）。

作为独立的「基础层」，被 carbon_engine（仿真编排）与 calculators（工序领域计算器）
共同依赖，自身不依赖任何 app 内部模块——从而打破 carbon_engine↔calculators 的循环依赖。

本层只回答三件事：
1. 常量：碳转 CO₂ 系数、排放因子默认值、能耗换算系数、金属料含碳率、燃料中文标签。
2. 因子合并：把用户传入的 factors 合并进默认表（_merge_factors）。
3. 计算原语：单燃料燃烧碳（fuel_carbon）、台账条目构造（_led）、单工序结果基底（_base）、
   能耗反推（_energy_of）、取值钳制（_clamp）。
"""
from __future__ import annotations

import copy
from typing import Dict

# ------------------------- 常数 -------------------------
CO2_PER_C = 44.0 / 12.0          # 碳转 CO2 系数（与国标一致）


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


# 能耗换算常数（节能减碳主题：先能后碳）
# 燃料单位热值含碳量（tC/GJ），用于由燃烧碳反推燃料低位热值 GJ
CC_FUEL = {"coke": 0.0295, "coal": 0.0262, "ng": 0.0153, "biomass": 0.0275}
GJ_PER_MWH = 3.6                # 1 MWh = 3.6 GJ
KGCE_PER_GJ = 34.12             # 1 GJ = 34.12 kgce（标准煤）

# 金属料含碳率（用于物料平衡：输入含碳 − 产品含碳）
METAL_C = {
    "hot_metal": 0.045,           # 铁水含碳 ~4.5%
    "scrap":     0.002,           # 废钢含碳 ~0.2%
    "dri":       0.0018,          # 直接还原铁含碳 ~0.18%
    "steel":     0.002,           # 最终钢水含碳 ~0.2%（行业典型中间值，碳素流去向演示）
    "bf_slag":   0.030,           # 高炉渣含碳率 ~3%（企业可配，反映渣中溶解碳/未燃煤粉）
    "steel_slag": 0.015,          # 转炉钢渣含碳率 ~1.5%（企业可配，渣中溶解碳）
}

# 喷吹煤粉元素/工业分析（喷煤置换比 Geerdes 公式输入；与前端 tft.js
# DEFAULT_TFT_CONFIG.fuels.pulverized_coal 一致——前端改配置后需同步此处）
PULVERIZED_COAL_COMP = {"Celem": 0.83, "H": 0.04, "H2O": 0.05, "Ash": 0.10}

# 基准煤比 kg/tFe（喷煤置换的零点，「模板=基准」：= 前端 flowLibrary 高炉模板 coal_inj def。
# 前端 bfFuel.js 已动态读取模板 def 自动跟随；后端为手动同步，改模板后需同步此处）
BF_COAL_REF = 130

# 富氧派生煤比系数：每 1% 富氧允许多喷煤粉 kg/tFe。
# 富氧升温 → 燃烧带容纳更多煤粉 → 置换焦炭（富氧不再直接节焦，作用经喷煤通道体现）。
# 实测数据出处：北大先锋·山西某钢厂 0→4% 富氧，煤比 120→170 kg/t（原 ≈12.5 kg/t per 1%）；
# 当前配置按 15 kg/t per 1% 设定（用户调整）。
BF_OXY_COAL_PER_PCT = 15


def replacement_ratio(comp=None):
    """喷煤置换比（Geerdes 公式，The Coal Handbook [17.11]）：
    RR% = 2·C% + 2.5·H% − 2·H₂O% + 0.9·Ash% − 86，返回小数（当前配置 ≈ 0.89）。
    C/H 取元素分析（Celem/H），H₂O/Ash 取收到基工业分析。"""
    c = comp if comp is not None else PULVERIZED_COAL_COMP
    rr = (2 * c["Celem"] + 2.5 * c["H"] - 2 * c["H2O"] + 0.9 * c["Ash"]) * 100 - 86
    return rr / 100.0

# 排放因子表（可配置项的默认值）。前端可在「因子配置」面板覆盖。
# fuels[fuel] = {ncv, cc, unit, label, desc}
#   ncv: 低位发热量 GJ/t(固体/液体) 或 GJ/1e4Nm³(气体)
#   cc : 单位热值含碳量 tC/GJ
#   unit: "t" 或 "m3"（气体按体积，AD 输入单位统一为 m³）
DEFAULT_FACTORS: Dict[str, object] = {
    "fuels": {
        "coke":    {"ncv": 28.435, "cc": 0.0295, "unit": "t",  "label": "焦炭",
                    "desc": "低位发热量 28.435 GJ/t · 单位热值含碳量 0.0295 tC/GJ（典型参考值）"},
        "coal":    {"ncv": 26.700, "cc": 0.0262, "unit": "t",  "label": "煤/煤粉",
                    "desc": "低位发热量 26.700 GJ/t · 单位热值含碳量 0.0262 tC/GJ（典型参考值）"},
        "biomass": {"ncv": 15.000, "cc": 0.0275, "unit": "t",  "label": "生物质碳",
                    "desc": "低位发热量 15.000 GJ/t · 单位热值含碳量 0.0275 tC/GJ（碳中性）"},
        "ng":      {"ncv": 389.310, "cc": 0.0153, "unit": "m3", "label": "天然气",
                    "desc": "低位发热量 389.310 GJ/万Nm³ · 单位热值含碳量 0.0153 tC/GJ（典型参考值）"},
    },
    "grid_ef": 0.5703,                        # tCO2/MWh，电网排放因子（2022 年全国电力平均 CO₂ 排放因子，可替换）
    "grid_desc": "电网排放因子 0.5703 tCO₂/MWh（2022 年全国电力平均 CO₂ 排放因子，可替换）",
    "carbonate": {"limestone": 0.4395, "dolomite": 0.4761},   # 碳酸盐分解因子 tCO2/t
    "electrode_ef": 3.663,                    # 电极消耗因子 tCO2/t 电极
}

# 燃料中文标签（桑基图节点），固定不随配置变化
FUEL_LABEL = {"coke": "焦炭碳", "coal": "煤碳", "ng": "天然气碳", "biomass": "生物质碳",
              "elec": "外购电碳", "steel_c": "钢铁料碳", "electrode": "电极碳", "carburizer": "增碳剂碳"}


def default_factors() -> Dict[str, object]:
    """返回默认排放因子表的深拷贝，供前端展示默认值与初始化编辑面板。"""
    return copy.deepcopy(DEFAULT_FACTORS)


def _merge_factors(factors: Dict) -> Dict:
    """把用户传入的 factors 合并进默认表，缺失项沿用默认，返回新 dict。"""
    cfg = copy.deepcopy(DEFAULT_FACTORS)
    if not factors:
        return cfg
    if isinstance(factors.get("fuels"), dict):
        for k, v in factors["fuels"].items():
            if k in cfg["fuels"]:
                cfg["fuels"][k].update(v)
            else:
                cfg["fuels"][k] = v
    if factors.get("grid_ef") is not None:
        cfg["grid_ef"] = factors["grid_ef"]
    if isinstance(factors.get("carbonate"), dict):
        cfg["carbonate"].update(factors["carbonate"])
    if factors.get("electrode_ef") is not None:
        cfg["electrode_ef"] = factors["electrode_ef"]
    return cfg


def fuel_carbon(amount: float, fuel: str, cfg: Dict) -> float:
    """按 NCV×CC×44/12 计算某燃料燃烧产生的 CO2 量（tCO2/h）。

    amount: 燃料量，固体/液体为 t/h，气体为 m³/h（与 cfg fuels[fuel]['unit'] 一致）。
    """
    f = (cfg.get("fuels") or {}).get(fuel)
    if f is None:
        return 0.0
    if f["unit"] == "m3":
        gj = amount / 1e4 * f["ncv"]          # 气体：体积(m³) → 1e4Nm³ → GJ
    else:
        gj = amount * f["ncv"]                # 固体/液体：t → GJ
    tC = gj * f["cc"]
    return tC * CO2_PER_C


def _energy_of(res: Dict) -> Dict[str, float]:
    """由单工序核算结果推导能耗（节能减碳主题：先能后碳）。

    - 电耗(MWh/h)：台账中所有用量单位为 MWh/h 的条目求和（外购电/电解制氢电耗等）。
    - 燃料能耗(GJ/h)：由各类燃料燃烧碳（tC/h）÷ 该燃料单位热值含碳量反推低位热值之和。
      coke_oven 以「炼焦煤」碳流反推（按煤 CC 折算），与碳素流一致。
    - 综合能耗(GJ/h) = 燃料能耗 + 电耗×3.6。
    - 单位产品综合能耗(kgce/t) = 综合能耗×34.12 / 主产物产量。
    """
    elec = 0.0
    for it in (res.get("ledger") or []):
        if it.get("qty_unit") == "MWh/h":
            elec += float(it.get("qty", 0.0) or 0.0)
    cbf = res.get("carbon_by_fuel", {}) or {}
    fuel_gj = 0.0
    for k, v in cbf.items():
        cc = CC_FUEL.get(k)
        if cc:
            fuel_gj += float(v) / cc
    total = fuel_gj + elec * GJ_PER_MWH
    steel = res.get("steel_output", 0.0) or 0.0
    intensity = (total * KGCE_PER_GJ) / steel if steel > 0 else 0.0
    return {
        "elec": round(elec, 2),
        "fuel_energy": round(fuel_gj, 2),
        "energy_total": round(total, 2),
        "energy_intensity": round(intensity, 1),
    }


def _led(item: str, qty: float, qty_unit: str, basis: str, co2: float, scope: str, formula: str = "") -> Dict:
    """构造一条碳排放台账项。"""
    q = round(qty, 3) if isinstance(qty, (int, float)) else qty
    return {"item": item, "qty": q, "qty_unit": qty_unit,
            "basis": basis, "formula": formula, "co2": round(co2, 2), "scope": scope}


def _base() -> Dict[str, float]:
    """单工序核算结果的基底结构。"""
    return {
        "co2_direct": 0.0, "co2_indirect": 0.0, "co2_total": 0.0, "carbon_in": 0.0,
        "carbon_to_co2": 0.0, "carbon_to_steel": 0.0, "carbon_to_slag": 0.0,
        "carbon_captured": 0.0,
        "steel_output": 0.0, "carbon_by_fuel": {},
        "elec": 0.0, "fuel_energy": 0.0, "energy_total": 0.0, "energy_intensity": 0.0,
        "ledger": [], "notes": [],
    }
