"""碳素流仿真引擎。

核心思想：把"工序类型 -> 碳排算法"做成注册表（RULES，见 calculators.py）。
新增一种工序 = 注册一个函数，框架完全不用改。前端/自然语言改出来的
任意流程，引擎读图按类型自动计算——这就是"自适应"。

核算方法：
- 对标 GB/T 32151.5《钢铁行业碳排放核算与报告要求》，采用物料平衡法思想：
  企业/工序碳排放 = Σ输入碳（化石燃料、碳酸盐、电极、含碳原料） − Σ输出含碳产品带入的碳。
- 化石燃料排放采用国家标准推荐计算式：E = AD × EF = (燃料量 × NCV × CC) × 44/12。
  其中 NCV 为低位发热量，CC 为单位热值含碳量，固体/液体按 t、气体按 m³ 输入。
- 碳酸盐分解排放采用标准因子（石灰石 0.4395、白云石 0.4761 tCO₂/t）。
- 电极消耗排放采用标准因子 3.663 tCO₂/t 电极。
- 外购电力间接排放按电网排放因子（grid_ef）计入范围二。

所有排放因子集中在 factors.DEFAULT_FACTORS（含单位与说明），可通过 simulate(factors=...)
运行时覆盖，便于按企业实测数据替换——这就是"可配置项"，前端提供编辑入口。

说明：本引擎在公式形式上对齐国家标准，默认参数为典型参考值，用于教学与
平台演示、体现碳素流向与策略对比的相对关系；绝对值非企业精确台账，不可直接
作为合规报送依据。
"""
from __future__ import annotations

import json
from collections import OrderedDict
from typing import Dict, List

from .models import ProcessModel, SimResult, SimTotals, UnitResult, SankeyNode, SankeyLink, LedgerItem
from .devices import compute_device_readings
from .calculators import RULES
from .specs import spec_defaults
from .factors import (
    CO2_PER_C, _clamp, CC_FUEL, GJ_PER_MWH, KGCE_PER_GJ,
    METAL_C, DEFAULT_FACTORS, FUEL_LABEL, default_factors, _merge_factors,
    fuel_carbon, _energy_of, _led, _base,
)


# ------------------------- 每种工序的默认参数（被用户/自然语言覆盖） -------------------------
DEFAULT_PARAMS: Dict[str, Dict[str, float]] = {
    # —— 原料准备 ——
    # 电耗显式值 = 产量 × 实际强度（kWh/t）/1000，与 calculators 中 fallback 一致
    # 默认规模：铁水 1000 t/h（约 2 座 3200m³ 高炉的演示规模），强度参数均按实际工业值标定
    "sinter_plant":      {"ore_rate": 1100, "fuel_rate": 45, "electricity": 44.0},    # 40 kWh/t
    "pelletizing":       {"ore_rate": 500,  "fuel_rate": 18, "electricity": 22.5},    # 45 kWh/t
    "coke_oven":         {"coal_rate": 475, "electricity": 9.5},                      # 20 kWh/t 煤
    "reheating_furnace": {"steel_in": 1000, "ng_rate": 45, "electricity": 8.0},       # 8 kWh/t
    # —— 炼铁（焦比/煤比标定到真实高炉区间，使吨钢强度进入 1800–2200 kg/t）——
    "blast_furnace":     {"hot_metal": 1000, "coke_rate": 470, "coal_inj": 150, "flux": 120, "slag_rate": 300},
    # 氢冶金：电耗 = h2_rate(kg/t)×产量×55 kWh/kgH₂ /1000（电解制氢）
    "hydrogen_bf":       {"hot_metal": 1000, "h2_rate": 90, "electricity": 4950.0},
    "h2_dri":            {"dri_out": 750, "h2_rate": 90, "electricity": 3712.5},
    "dri_midrex":        {"pellet_rate": 750, "ng_rate": 300, "electricity": 112.5},  # 150 kWh/t-DRI
    "smelting_reduction":{"ore_rate": 750, "coal_rate": 900, "electricity": 30.0},    # 40 kWh/t
    "biochar_injection": {"biomass_rate": 25, "electricity": 2.5},                    # 100 kWh/t
    # —— 炼钢 ——
    "bof":               {"hot_metal_in": 1000, "scrap": 100, "flux": 60, "slag_rate": 120},
    "eaf":               {"scrap": 900, "dri": 0, "electricity": 360.0, "electrode": 1.8},  # 400 kWh/t·2 kg/t
    # —— 精炼 ——
    "ladle_furnace":     {"steel_in": 1000, "electricity": 25.0},                     # 25 kWh/t
    "rh_vacuum":         {"steel_in": 1000, "electricity": 5.0},                      # 5 kWh/t
    "vd_vacuum":         {"steel_in": 1000, "electricity": 4.0},                      # 4 kWh/t
    "aod":               {"steel_in": 1000, "electricity": 12.0},                     # 12 kWh/t
    # —— 连铸 ——
    "caster":            {"steel_in": 1000, "electricity": 15.0},                     # 15 kWh/t
    "ingot_casting":     {"steel_in": 1000, "ng_rate": 20, "electricity": 8.0},       # 8 kWh/t
    # —— 轧制 ——
    "rolling_mill":      {"steel_in": 1000, "ng_rate": 32, "electricity": 80.0},      # 80 kWh/t
    "cold_rolling":      {"steel_in": 1000, "ng_rate": 25, "electricity": 100.0},     # 100 kWh/t
}

# 工序展示元数据：中文名 / 几何形状 / 工艺分类（用于工序库分组与3D建模）
UNIT_META: Dict[str, Dict[str, str]] = {
    # 原料准备
    "sinter_plant":      {"label": "烧结机",     "shape": "box",      "cat": "原料准备"},
    "pelletizing":       {"label": "球团",       "shape": "box",      "cat": "原料准备"},
    "coke_oven":         {"label": "焦炉",       "shape": "box",      "cat": "原料准备"},
    "reheating_furnace": {"label": "加热炉",     "shape": "furnace",  "cat": "原料准备"},
    # 炼铁
    "blast_furnace":     {"label": "高炉",       "shape": "furnace",  "cat": "炼铁"},
    "hydrogen_bf":       {"label": "氢冶金高炉", "shape": "furnace",  "cat": "炼铁"},
    "h2_dri":            {"label": "氢基竖炉",   "shape": "furnace",  "cat": "炼铁"},
    "dri_midrex":        {"label": "直接还原炉", "shape": "furnace",  "cat": "炼铁"},
    "smelting_reduction":{"label": "熔融还原",   "shape": "furnace",  "cat": "炼铁"},
    "biochar_injection": {"label": "生物质喷吹", "shape": "cylinder", "cat": "炼铁"},
    # 炼钢
    "bof":               {"label": "转炉",       "shape": "converter","cat": "炼钢"},
    "eaf":               {"label": "电炉",       "shape": "furnace",  "cat": "炼钢"},
    # 精炼
    "ladle_furnace":     {"label": "精炼炉",     "shape": "cylinder", "cat": "精炼"},
    "rh_vacuum":         {"label": "RH精炼",     "shape": "cylinder", "cat": "精炼"},
    "vd_vacuum":         {"label": "VD脱气",     "shape": "cylinder", "cat": "精炼"},
    "aod":               {"label": "AOD精炼",    "shape": "converter","cat": "精炼"},
    # 连铸
    "caster":            {"label": "连铸机",     "shape": "slab",     "cat": "连铸"},
    "ingot_casting":     {"label": "模铸",       "shape": "box",      "cat": "连铸"},
    # 轧制
    "rolling_mill":      {"label": "热轧机",     "shape": "rollers",  "cat": "轧制"},
    "cold_rolling":      {"label": "冷轧机",     "shape": "rollers",  "cat": "轧制"},
}



# ------------------------- 技术修正（领域逻辑） -------------------------

def _apply_techs(unit, res: Dict) -> Dict:
    """应用技术对结果的修正，并向台账追加减排项（保证台账求和=总量）。"""
    ledger = res.setdefault("ledger", [])
    for tech in unit.techs:
        if tech == "ccs":                      # 碳捕集：捕集直接碳排的一部分
            rate = unit.params.get("capture_rate", 0.9)
            captured = res["co2_direct"] * rate
            captured_c = captured / CO2_PER_C
            res["co2_direct"] -= captured
            res["carbon_captured"] = captured_c
            res["carbon_to_co2"] = max(res["carbon_to_co2"] - captured_c, 0.0)
            ledger.append(_led("碳捕集(CCS)减排", captured, "tCO₂/h", f"捕集率 {int(rate*100)}%", -captured, "direct",
                               formula=f"捕集 {captured:.0f} tCO₂/h（直接排放 × {int(rate*100)}%）"))
        elif tech == "waste_heat":             # 余热回收：降低间接电耗
            before = res["co2_indirect"]
            after = before * 0.85
            red = before - after
            res["co2_indirect"] = after
            ledger.append(_led("余热回收(节电)", red, "tCO₂/h", "间接排放降低 15%", -red, "indirect",
                               formula=f"间接排放 {before:.0f} − {after:.0f} = 减排 {red:.0f} tCO₂/h"))
        elif tech == "h2_inj":                 # 富氢喷吹：降低焦比等效碳
            before = res["co2_direct"]
            after = before * 0.9
            red = before - after
            res["co2_direct"] = after
            res["carbon_to_co2"] = max(res["carbon_to_co2"] - red / CO2_PER_C, 0.0)
            ledger.append(_led("富氢喷吹(降焦)", red, "tCO₂/h", "直接排放降低 10%", -red, "direct",
                               formula=f"直接排放 {before:.0f} − {after:.0f} = 减排 {red:.0f} tCO₂/h"))
    return res


# ------------------------- 仿真结果缓存（LRU） -------------------------
# 角色：以「规范化后的模型 + 因子」为键缓存 SimResult，对完全相同的重复仿真
# （前端防抖后的连续高频请求、KPI 轮询、策略对比重算）直接命中缓存，避免重复计算。
# 设计：备忘录/缓存模式（Memoization）+ 最近最少使用淘汰；结果对象只读、下游仅序列化，
# 不存在被外部改写的风险，故缓存同一对象引用而非深拷贝，开销最低。
_SIM_CACHE: "OrderedDict[str, SimResult]" = OrderedDict()
_SIM_CACHE_MAX = 64                          # 缓存容量，超出淘汰最久未用
_SIM_CACHE_HITS = 0
_SIM_CACHE_MISSES = 0


def _sim_cache_key(model: ProcessModel, factors) -> str:
    """对模型与因子做确定性序列化，作为缓存键（忽略字段顺序/空格）。"""
    try:
        model_json = model.model_dump_json()
    except Exception:
        model_json = json.dumps(getattr(model, "model_dump", lambda: {})() or {},
                                 sort_keys=True, ensure_ascii=False, default=str)
    fac_json = json.dumps(factors or {}, sort_keys=True, ensure_ascii=False, default=str)
    return model_json + "||" + fac_json


def cached_simulate(model: ProcessModel, factors: Dict = None) -> SimResult:
    global _SIM_CACHE_HITS, _SIM_CACHE_MISSES
    key = _sim_cache_key(model, factors)
    hit = _SIM_CACHE.get(key)
    if hit is not None:
        _SIM_CACHE.move_to_end(key)
        _SIM_CACHE_HITS += 1
        return hit
    _SIM_CACHE_MISSES += 1
    res = simulate(model, factors)
    _SIM_CACHE[key] = res
    if len(_SIM_CACHE) > _SIM_CACHE_MAX:
        _SIM_CACHE.popitem(last=False)
    return res


def sim_cache_stats() -> Dict[str, int]:
    return {"size": len(_SIM_CACHE), "hits": _SIM_CACHE_HITS, "misses": _SIM_CACHE_MISSES}


def _raw_units(model: ProcessModel, cfg: Dict) -> List[tuple]:
    """计算内核：返回 [(unit, res, params)]，与 simulate 共用，供扫描/审计复用。"""
    out = []
    for u in model.units:
        if not u.enabled:
            continue
        params = dict(DEFAULT_PARAMS.get(u.type, {}))
        # 设备规格：用规格档位的默认参数覆盖该类型默认值（不同规格同类设备各按额定运行点仿真）
        if getattr(u, "spec", ""):
            params.update(spec_defaults(u.type, u.spec))
        params.update(u.params or {})
        fn = RULES.get(u.type)
        if fn is None:
            continue
        res = fn(params, cfg)
        res = _apply_techs(u, res)
        res.update(_energy_of(res))   # 计算能耗（节能减碳：先能后碳）
        res["co2_total"] = res["co2_direct"] + res["co2_indirect"]
        out.append((u, res, params))
    return out


# 金属/成品类工序（其 steel_output 可参与全厂"钢产量"口径的汇总）
_OUTPUT_METAL_TYPES = {
    "blast_furnace", "hydrogen_bf", "h2_dri", "dri_midrex", "smelting_reduction",
    "bof", "eaf", "ladle_furnace", "rh_vacuum", "vd_vacuum", "aod",
    "caster", "ingot_casting", "reheating_furnace", "rolling_mill", "cold_rolling",
}


def simulate(model: ProcessModel, factors: Dict = None) -> SimResult:
    cfg = _merge_factors(factors)
    units_out: List[UnitResult] = []
    totals = _base()
    totals["co2_direct"] = totals["co2_indirect"] = 0.0
    totals["carbon_in"] = totals["carbon_to_co2"] = totals["carbon_to_steel"] = totals["carbon_captured"] = 0.0
    totals["steel_output"] = 0.0
    totals["energy_total"] = 0.0
    totals["elec"] = 0.0
    totals["fuel_energy"] = 0.0

    raw = _raw_units(model, cfg)
    max_co2 = 1.0
    for u, res, params in raw:
        max_co2 = max(max_co2, res["co2_total"])
        # 汇总
        totals["co2_direct"] += res["co2_direct"]
        totals["co2_indirect"] += res["co2_indirect"]
        totals["co2_total"] += res["co2_total"]
        totals["carbon_in"] += res["carbon_in"]
        totals["carbon_to_co2"] += res["carbon_to_co2"]
        totals["carbon_to_steel"] += res["carbon_to_steel"]
        totals["carbon_to_slag"] += res["carbon_to_slag"]
        totals["carbon_captured"] += res["carbon_captured"]
        totals["energy_total"] += res["energy_total"]
        totals["elec"] += res["elec"]
        totals["fuel_energy"] += res["fuel_energy"]
        # 钢产量：仅统计"金属/成品"类工序（铁水、钢水、DRI、成品材），
        # 排除原料类工序（烧结/球团/焦炭/生物质），避免其产品量被误认为钢产量
        if u.type in _OUTPUT_METAL_TYPES and res["steel_output"] > totals["steel_output"]:
            totals["steel_output"] = res["steel_output"]

    # 热力图归一化 + 组装 UnitResult
    for u, res, params in raw:
        heat = min(res["co2_total"] / max_co2, 1.0)
        cbf = res.get("carbon_by_fuel", {}) or {}
        units_out.append(UnitResult(
            id=u.id, type=u.type, name=u.name,
            co2_direct=round(res["co2_direct"], 2),
            co2_indirect=round(res["co2_indirect"], 2),
            co2_total=round(res["co2_total"], 2),
            carbon_in=round(res["carbon_in"], 3),
            carbon_to_co2=round(res["carbon_to_co2"], 3),
            carbon_to_steel=round(res["carbon_to_steel"], 3),
            carbon_to_slag=round(res["carbon_to_slag"], 3),
            carbon_captured=round(res["carbon_captured"], 3),
            heat=round(heat, 3),
            steel_output=round(res.get("steel_output", 0.0), 1),
            elec=round(res["elec"], 2),
            fuel_energy=round(res["fuel_energy"], 2),
            energy_total=round(res["energy_total"], 2),
            energy_intensity=round(res["energy_intensity"], 1),
            carbon_by_fuel={k: round(v, 3) for k, v in cbf.items()},
            breakdown=[LedgerItem(**it) for it in res.get("ledger", [])],
            notes=res.get("notes", []),
            devices=compute_device_readings(u, params),
        ))

    steel = totals["steel_output"] or 1.0
    intensity = totals["co2_total"] / steel * 1000.0
    util = ((totals["carbon_to_steel"] + totals["carbon_to_slag"] + totals["carbon_captured"]) / totals["carbon_in"]) if totals["carbon_in"] else 0.0
    energy_intensity = (totals["energy_total"] * KGCE_PER_GJ) / steel if steel > 0 else 0.0
    t = SimTotals(
        co2_direct=round(totals["co2_direct"], 2),
        co2_indirect=round(totals["co2_indirect"], 2),
        co2_total=round(totals["co2_total"], 2),
        carbon_in=round(totals["carbon_in"], 3),
        carbon_to_co2=round(totals["carbon_to_co2"], 3),
        carbon_to_steel=round(totals["carbon_to_steel"], 3),
        carbon_to_slag=round(totals["carbon_to_slag"], 3),
        carbon_captured=round(totals["carbon_captured"], 3),
        carbon_utilization=round(util, 4),
        steel_output=round(steel, 1),
        intensity=round(intensity, 1),
        energy_total=round(totals["energy_total"], 1),
        energy_intensity=round(energy_intensity, 1),
        elec=round(totals["elec"], 1),
        fuel_energy=round(totals["fuel_energy"], 1),
    )
    sankey = build_sankey(raw)
    sankey_energy = build_energy_sankey(raw, cfg)
    return SimResult(totals=t, units=units_out, sankey=sankey, sankey_energy=sankey_energy)


def build_sankey(raw) -> Dict[str, object]:
    """生成碳素流桑基图：燃料源 -> 工序 -> 去向(CO2/固碳/捕集)。单位 tC/h。"""
    nodes: List[SankeyNode] = []
    links: List[SankeyLink] = []
    node_ids = set()

    sink_ids = {"co2": "CO₂排放碳", "steel": "钢中固碳", "captured": "捕集碳", "product": "碳产品/固定碳"}
    for sid, slab in sink_ids.items():
        nodes.append(SankeyNode(id=sid, label=slab, col=2, kind="sink"))
        node_ids.add(sid)

    for u, res, _params in raw:
        cbf = res.get("carbon_by_fuel", {}) or {}
        fuel_carbon = 0.0
        fuel_links: List[tuple] = []
        for fk, fv in cbf.items():
            if fk == "elec":
                continue  # 外购电为间接碳，不计入碳素流(直接碳)桑基图，交由能流图展示
            if fv <= 1e-6:
                continue
            fuel_links.append((fk, fv))
            fuel_carbon += fv
        # 炉料/熔剂带入碳：钢铁料(铁水/废钢/海绵铁)与熔剂本身携带的碳，
        # 最终进入「钢中固碳」或氧化为 CO₂，但未计入燃料源，故补为统一源节点，保证碳流守恒。
        charge_carbon = (res.get("carbon_in", 0.0) or 0.0) - fuel_carbon
        carbon_out = res["carbon_to_co2"] + res["carbon_to_steel"] + res["carbon_captured"]
        carried = (res.get("carbon_in", 0.0) or 0.0) - carbon_out
        # 无任何碳流入/流出的工序（如引风机、鼓风机等不涉碳工辅）不在碳素流中体现
        if fuel_carbon <= 1e-9 and charge_carbon <= 1e-9 and carbon_out <= 1e-6 and carried <= 1e-6:
            continue
        pid = f"u:{u.id}"
        if pid not in node_ids:
            nodes.append(SankeyNode(id=pid, label=u.name, col=1, kind="process"))
            node_ids.add(pid)
        for fk, fv in fuel_links:
            fid = f"f:{fk}"
            if fid not in node_ids:
                nodes.append(SankeyNode(id=fid, label=FUEL_LABEL.get(fk, fk), col=0, kind="fuel"))
                node_ids.add(fid)
            links.append(SankeyLink(source=fid, target=pid, value=round(fv, 3)))
        if charge_carbon > 1e-9:
            fid = "f:charge"
            if fid not in node_ids:
                nodes.append(SankeyNode(id=fid, label="炉料/熔剂碳", col=0, kind="fuel"))
                node_ids.add(fid)
            links.append(SankeyLink(source=fid, target=pid, value=round(charge_carbon, 3)))
        # 工序 -> 去向
        if res["carbon_to_co2"] > 1e-6:
            links.append(SankeyLink(source=pid, target="co2", value=round(res["carbon_to_co2"], 3)))
        if res["carbon_to_steel"] > 1e-6:
            links.append(SankeyLink(source=pid, target="steel", value=round(res["carbon_to_steel"], 3)))
        if res["carbon_captured"] > 1e-6:
            links.append(SankeyLink(source=pid, target="captured", value=round(res["carbon_captured"], 3)))
        # 碳产品/固定碳：未排放也未固结于钢水的碳（如焦化工序焦炭本身携带的碳），
        # 以守恒方式吸收差额，保证桑基图左右流量平衡。
        if carried > 1e-6:
            links.append(SankeyLink(source=pid, target="product", value=round(carried, 3)))
    return {"nodes": [n.model_dump() for n in nodes], "links": [l.model_dump() for l in links]}


# 产品有效能系数：产品(钢)带走有效能占综合能耗的比例（钢铁行业典型参考值，演示口径）
STEEL_EFF_EFFICIENCY = 0.30

# 能源视角的源标签（区别于碳素流 FUEL_LABEL）
_ENERGY_SOURCE_LABEL = {"coke": "焦炭", "coal": "煤/煤粉", "ng": "天然气", "biomass": "生物质", "elec": "外购电"}


def build_energy_sankey(raw, cfg: Dict) -> Dict[str, object]:
    """生成能流桑基图：能源源 -> 工序 -> 去向(产品有效能/余热回收/损失)。单位 GJ/h。

    设计说明（节能减碳并重）：
    - 能源源按「外购电 + 各燃料」拆分：外购电 = elec×3.6 GJ/h；燃料能量由燃烧碳反推（碳量/单位热值含碳量）。
    - 去向侧单独展示「余热回收利用」（由台账余热回收节电的减排量反推回收能量），突出节能流向；
      其余按行业典型有效能效率拆分「产品有效能」与「烟气/散热损失」。
    """
    nodes: List[SankeyNode] = []
    links: List[SankeyLink] = []
    node_ids = set()

    # 去向节点
    for sid, slab in (("es:product", "产品有效能"), ("es:recovery", "余热回收利用"), ("es:loss", "烟气/散热损失")):
        nodes.append(SankeyNode(id=sid, label=slab, col=2, kind="sink"))
        node_ids.add(sid)

    # 外购电能源源
    nodes.append(SankeyNode(id="ef:elec", label=_ENERGY_SOURCE_LABEL["elec"], col=0, kind="source"))
    node_ids.add("ef:elec")

    grid_ef = float(cfg.get("grid_ef") or 0.5)   # tCO2/MWh
    fuels_cfg = cfg.get("fuels", {}) or {}

    per_unit: Dict[str, Dict[str, float]] = {}
    for u, res, _params in raw:
        pid = f"eu:{u.id}"
        # 外购电 -> 工序
        elec_gj = res.get("elec", 0.0) * GJ_PER_MWH
        # 燃料 -> 工序（碳量反推低位发热量）
        cbf = res.get("carbon_by_fuel", {}) or {}
        fuel_gj = 0.0
        fuel_links: List[tuple] = []
        for fk, fv in cbf.items():
            if fk == "elec":
                continue  # 外购电能量由 ef:elec 统一按 elec×3.6 GJ/h 处理
            if fv <= 1e-6:
                continue
            cc = CC_FUEL.get(fk) or (fuels_cfg.get(fk) or {}).get("cc") or 0.0
            if not cc:
                continue
            gj = fv / cc
            if gj <= 1e-6:
                continue
            fuel_links.append((fk, gj))
            fuel_gj += gj
        energy_total = res.get("energy_total", 0.0) or 0.0
        # 既无能量流入也无综合能耗的工序（孤立节点，无实际能流）不在能流中体现
        if elec_gj <= 1e-6 and fuel_gj <= 1e-6 and energy_total <= 1e-6:
            continue
        if pid not in node_ids:
            nodes.append(SankeyNode(id=pid, label=u.name, col=1, kind="process"))
            node_ids.add(pid)
        if elec_gj > 1e-6:
            links.append(SankeyLink(source="ef:elec", target=pid, value=round(elec_gj, 2)))
        for fk, gj in fuel_links:
            fid = f"ef:{fk}"
            if fid not in node_ids:
                nodes.append(SankeyNode(id=fid, label=_ENERGY_SOURCE_LABEL.get(fk, fk), col=0, kind="source"))
                node_ids.add(fid)
            links.append(SankeyLink(source=fid, target=pid, value=round(gj, 2)))
        per_unit[pid] = {"energy_total": energy_total, "recovery_gj": 0.0}

    # 余热回收能量：由台账「余热回收(节电)」减排量(tCO2/h)反推节电量 -> GJ/h
    for u, res, _params in raw:
        pid = f"eu:{u.id}"
        if pid not in per_unit:
            continue
        for it in res.get("ledger", []) or []:
            if it.get("item") == "余热回收(节电)":
                red_gj = (it.get("qty", 0.0) / grid_ef) * GJ_PER_MWH if grid_ef else 0.0
                per_unit[pid]["recovery_gj"] = max(red_gj, 0.0)
                break

    # 工序 -> 去向
    for pid, info in per_unit.items():
        e = info["energy_total"]
        if e <= 1e-6:
            continue
        r = min(info["recovery_gj"], e)
        p = e * STEEL_EFF_EFFICIENCY
        loss = max(e - p - r, 0.0)
        links.append(SankeyLink(source=pid, target="es:product", value=round(p, 2)))
        if r > 1e-6:
            links.append(SankeyLink(source=pid, target="es:recovery", value=round(r, 2)))
        if loss > 1e-6:
            links.append(SankeyLink(source=pid, target="es:loss", value=round(loss, 2)))

    return {"nodes": [n.model_dump() for n in nodes], "links": [l.model_dump() for l in links]}


# ============================ 求解 / 分析能力（对标 Aspen 参数扫描） ============================
# 说明：现有 simulate 是「松耦合代数求和」，缺少联立求解与敏感性分析。以下两个函数
# 在不改动 simulate 既有行为的前提下，补上「参数扫描（敏感性分析）」与「守恒审计」，
# 直接把平台从「一次性算出一个数」提升到「能看趋势、能量闭合度」的分析工具。

def parameter_scan(model: ProcessModel, factors: Dict, unit_id: str, param: str,
                  low: float, high: float, steps: int = 11) -> Dict:
    """单工序参数扫描（一维敏感性分析）。

    固定其余参数，将目标工序的 `param` 从 low 线性扫到 high（共 steps 点），
    逐点 simulate 并采集全厂总量，返回随参数变化的曲线。用于回答：
    「焦比从 360 扫到 480，吨钢碳强度怎么变？」这类工程问题。

    返回：{ unit_id, unit_name, unit_type, param, low, high, steps, points:[{value, co2_total, ...}] }
    """
    if low >= high:
        raise ValueError("扫描区间下界必须小于上界（low < high）")
    steps = max(2, int(steps))
    # 克隆模型，避免污染入参
    m2 = ProcessModel(**model.model_dump())
    target = next((u for u in m2.units if u.id == unit_id), None)
    if target is None:
        raise ValueError(f"未找到工序 id={unit_id}（请检查流程模型）")
    if param not in (target.params or {}):
        # 允许覆盖引擎默认值：若参数未显式设置，仍以默认值起扫
        base = (DEFAULT_PARAMS.get(target.type, {}) or {}).get(param)
        if base is None:
            raise ValueError(f"工序 {target.name}（{target.type}）不存在参数 {param}（请核对参数名）")
    is_int = isinstance((target.params or {}).get(param, (DEFAULT_PARAMS.get(target.type, {}) or {}).get(param)), int)

    points = []
    for i in range(steps):
        frac = i / (steps - 1)
        val = low + (high - low) * frac
        if is_int:
            val = int(round(val))
        target.params[param] = val
        r = simulate(m2, factors)            # 调用内核，复用全部既有算法
        t = r.totals
        points.append({
            "value": round(val, 3),
            "co2_total": t.co2_total,
            "co2_direct": t.co2_direct,
            "co2_indirect": t.co2_indirect,
            "intensity": t.intensity,
            "steel_output": t.steel_output,
            "energy_total": t.energy_total,
            "energy_intensity": t.energy_intensity,
        })
    return {
        "unit_id": unit_id,
        "unit_name": target.name,
        "unit_type": target.type,
        "param": param,
        "low": low, "high": high, "steps": steps,
        "points": points,
    }


def conservation_audit(model: ProcessModel, factors: Dict = None) -> Dict:
    """碳元素守恒审计（工程严谨性自检）。

    逐工序核对：碳输入 = 排CO₂ + 固结于钢 + 入渣 + 被捕集 + 产品携出（product 节点）。
    关键发现：各工序的单位碳算术本身是**闭合的**（残差≈0）；真正的「非闭合」来自
    中间产品碳（焦炭/DRI）——它们经桑基图 product 节点兜底吸收，却未通过物料连线
    真正流入下游工序。这正是「经验耦合」与「物料平衡闭环」之间的最大差距所在。

    返回：{ units:[{...}], totals:{...}, note }
    """
    cfg = _merge_factors(factors)
    raw = _raw_units(model, cfg)
    units = []
    t_in = t_co2 = t_steel = t_slag = t_cap = t_prod = t_cprod = t_res = 0.0
    for u, res, _params in raw:
        c_in = res.get("carbon_in", 0.0) or 0.0
        c_co2 = res.get("carbon_to_co2", 0.0) or 0.0
        c_steel = res.get("carbon_to_steel", 0.0) or 0.0
        c_slag = res.get("carbon_to_slag", 0.0) or 0.0
        c_cap = res.get("carbon_captured", 0.0) or 0.0
        c_prod = res.get("carbon_to_product", 0.0) or 0.0   # 中间产品碳（焦炭/DRI/HBI 等，离开本工序供下游）
        # 桑基图「产品/固定碳」节点吸收量（不含入渣碳）
        prod = c_in - (c_co2 + c_steel + c_cap)
        # 真实闭合余量：碳输入 − 全部显式去向（排CO₂+固钢+入渣+捕集+中间产品）；趋近 0 表示单位守恒良好
        residual = c_in - (c_co2 + c_steel + c_slag + c_cap + c_prod)
        units.append({
            "id": u.id, "name": u.name, "type": u.type,
            "carbon_in": round(c_in, 3),
            "carbon_to_co2": round(c_co2, 3),
            "carbon_to_steel": round(c_steel, 3),
            "carbon_to_slag": round(c_slag, 3),
            "carbon_captured": round(c_cap, 3),
            "carbon_to_product": round(c_prod, 3),
            "product_carried": round(prod, 3),
            "residual": round(residual, 3),
        })
        t_in += c_in; t_co2 += c_co2; t_steel += c_steel; t_slag += c_slag; t_cap += c_cap; t_prod += prod; t_cprod += c_prod; t_res += residual
    return {
        "units": units,
        "totals": {
            "carbon_in": round(t_in, 3),
            "carbon_to_co2": round(t_co2, 3),
            "carbon_to_steel": round(t_steel, 3),
            "carbon_to_slag": round(t_slag, 3),
            "carbon_captured": round(t_cap, 3),
            "carbon_to_product": round(t_cprod, 3),
            "product_carried": round(t_prod, 3),
            "residual": round(t_res, 3),
            "closure_error": round((t_res / t_in) if t_in > 1e-9 else 0.0, 4),
        },
        "note": "本平台以物料平衡法核算碳素流；residual（真实闭合余量）趋近 0 表示单位碳算术守恒良好。"
                "中间产品碳（焦炭/DRI 等）现作为 carbon_to_product 显式计入守恒，残差应归零；"
                "product_carried 为桑基图「碳产品/固定碳」节点吸收的碳——它们目前靠 product 节点兜底，"
                "未通过物料连线真正流入下游。把中间产品碳接入 flow 连线，即从「经验耦合」走向「物料平衡闭环」。",
    }