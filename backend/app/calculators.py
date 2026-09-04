"""工序碳排放计算层（领域逻辑）：各工序 calc_* 函数 + RULES 注册表 + 公式展开辅助。

本模块是碳引擎的「领域计算器」集合，与编排层 carbon_engine.py（simulate 调度）解耦：
- carbon_engine 只负责常量/原语/仿真编排；
- 本模块只负责「给定参数与因子 -> 单工序排放」的确定性计算；
- 通过 RULES 注册表（策略/注册表模式）供 simulate 按工序类型分发，新增工序=新增一个 calc_* 并登记。
"""
from __future__ import annotations

from typing import Dict

from .factors import (
    CO2_PER_C,            # 碳转 CO2 系数（44/12）
    DEFAULT_FACTORS,      # 默认排放因子表（燃料 NCV/CC、电网因子、碳酸盐/电极）
    fuel_carbon,          # NCV×CC×44/12 燃料碳排
    _led,                 # 台账条目构造
    _base,                # 单工序结果基底
    METAL_C,              # 铁水/钢水溶解碳系数
    _clamp,               # 取值钳制（鼓风炉有效燃料比等边界处理）
    BF_COAL_REF,          # 名义基准煤比 kg/tFe（喷煤置换零点）
    BF_OXY_COAL_PER_PCT,  # 富氧派生煤比：每 1% 富氧允许多喷煤粉 kg/tFe
    replacement_ratio,    # 喷煤置换比（Geerdes 公式）
)

# 喷煤置换比（与前端 bfFuel.js RR 一致，当前 ≈ 0.71）
RR = replacement_ratio()


def _fuel_formula(fuel: str, amount: float, co2: float, cfg: Dict) -> str:
    f = cfg["fuels"][fuel]
    ncv, cc = f["ncv"], f["cc"]
    if f["unit"] == "m3":
        return f"{amount:.0f} m³ ÷1e4 × {ncv} GJ/万Nm³ × {cc} tC/GJ × 3.667 = {co2:.0f} tCO₂/h"
    return f"{amount:.0f} t × {ncv} GJ/t × {cc} tC/GJ × 3.667 = {co2:.0f} tCO₂/h"


def _elec_formula(elec: float, co2: float, cfg: Dict) -> str:
    return f"{elec:.1f} MWh × {cfg['grid_ef']} tCO₂/MWh = {co2:.0f} tCO₂/h"


def _carbonate_formula(flux_t: float, co2: float, cfg: Dict, key: str = "limestone") -> str:
    return f"{flux_t:.0f} t × {cfg['carbonate'][key]} tCO₂/t = {co2:.0f} tCO₂/h"


def _electrode_formula(electrode: float, co2: float, cfg: Dict) -> str:
    return f"{electrode:.2f} t × {cfg['electrode_ef']} tCO₂/t = {co2:.0f} tCO₂/h"


def _purchases(r: Dict, **kw: float) -> None:
    """登记本工序外购原燃料消耗（固体按 t/h 计），供全厂成本核算（用量 × 单价）。

    物料 id 与前端 flowLibrary.MATERIALS 对齐（iron_ore/coke/coal/limestone/scrap/
    electrode/biomass…）；外购电力(MWh/h)与天然气(m³/h)由 simulate 统一自动汇总，无需在此登记。
    """
    buy = {k: round(float(v), 3) for k, v in kw.items() if v and float(v) > 1e-9}
    if buy:
        r["purchases"] = buy


def calc_sinter(p, cfg=DEFAULT_FACTORS):
    ore = p.get("ore_rate", 0.0)
    fuel_t = p.get("fuel_rate", 0.0) * ore / 1000.0          # t/h 固体燃料
    direct = fuel_carbon(fuel_t, "coal", cfg)
    elec = p.get("electricity", ore * 0.04)                  # 40 kWh/t（主抽风机+环冷+除尘）
    indirect = elec * cfg["grid_ef"]
    r = _base()
    r.update(co2_direct=direct, co2_indirect=indirect, carbon_in=direct / CO2_PER_C,
             carbon_to_co2=direct / CO2_PER_C, steel_output=ore,
             carbon_by_fuel={"coal": direct / CO2_PER_C})
    r["ledger"] = [
        _led("固体燃料(焦粉/煤粉)", fuel_t, "t/h", "NCV×CC×44/12", direct, "direct",
             formula=_fuel_formula("coal", fuel_t, direct, cfg)),
        _led("外购电力", elec, "MWh/h", f"电网因子 {cfg['grid_ef']} tCO₂/MWh", indirect, "indirect",
             formula=_elec_formula(elec, indirect, cfg)),
    ]
    r["notes"] = ["烧结碳排主要来自燃料燃烧(范围一)与电耗(范围二)"]
    _purchases(r, coal=fuel_t, iron_ore=ore)   # 外购：铁矿石(处理矿量) + 固体燃料
    return r


def calc_pellet(p, cfg=DEFAULT_FACTORS):
    ore = p.get("ore_rate", 0.0)
    fuel_t = p.get("fuel_rate", 0.0) * ore / 1000.0
    direct = fuel_carbon(fuel_t, "coal", cfg)
    elec = p.get("electricity", ore * 0.045)                 # 45 kWh/t（焙烧鼓风+环冷）
    indirect = elec * cfg["grid_ef"]
    r = _base()
    r.update(co2_direct=direct, co2_indirect=indirect, carbon_in=direct / CO2_PER_C,
             carbon_to_co2=direct / CO2_PER_C, steel_output=ore,
             carbon_by_fuel={"coal": direct / CO2_PER_C})
    r["ledger"] = [
        _led("固体燃料(返矿/煤粉)", fuel_t, "t/h", "NCV×CC×44/12", direct, "direct",
             formula=_fuel_formula("coal", fuel_t, direct, cfg)),
        _led("外购电力", elec, "MWh/h", f"电网因子 {cfg['grid_ef']} tCO₂/MWh", indirect, "indirect",
             formula=_elec_formula(elec, indirect, cfg)),
    ]
    r["notes"] = ["球团工序碳排低于烧结，是更清洁的炉料准备方式"]
    _purchases(r, coal=fuel_t, iron_ore=ore)   # 外购：铁矿石(处理矿量) + 固体燃料
    return r


def calc_coke(p, cfg=DEFAULT_FACTORS):
    coal = p.get("coal_rate", 0.0)
    # 干馏：入炉煤碳 − 焦炭固碳 = 以 CO2 排出；焦炭固碳作为中间产品碳离开本工序（供高炉）
    c_in = fuel_carbon(coal, "coal", cfg) / CO2_PER_C     # tC/h 入炉煤
    coke_out = coal * 0.75
    cf = cfg["fuels"]["coke"]
    c_to_coke = coke_out * cf["cc"] * cf["ncv"]   # 焦炭含碳(tC/h) —— 中间产品碳
    c_to_co2 = c_in - c_to_coke
    direct = c_to_co2 * CO2_PER_C
    elec = p.get("electricity", coal * 0.02)                 # 20 kWh/t 煤（除尘+机械，吨焦约 27 kWh）
    indirect = elec * cfg["grid_ef"]
    r = _base()
    r.update(co2_direct=direct, co2_indirect=indirect, carbon_in=c_in,
             carbon_to_co2=c_to_co2, carbon_to_product=c_to_coke,
             steel_output=coke_out, carbon_by_fuel={"coal": c_in})
    r["ledger"] = [
        _led("入炉煤(干馏排放碳)", c_to_co2, "tC/h", "煤碳 − 焦炭固碳", direct, "direct",
             formula=f"{c_to_co2:.1f} tC（入炉煤碳 {c_in:.1f} − 焦炭固碳 {c_to_coke:.1f}）× 3.667 = {direct:.0f} tCO₂/h"),
        _led("焦炭产品碳(入高炉)", c_to_coke, "tC/h", "约 75% 入炉煤碳固结于焦炭，作为中间产品离开本工序", 0.0, "direct",
             formula=f"{coke_out:.1f} t 焦炭 × 含碳率 {cf['cc']*100:.1f}% × 低位热值 {cf['ncv']:.2f} GJ/t = {c_to_coke:.1f} tC/h（不排放）"),
        _led("外购电力", elec, "MWh/h", f"电网因子 {cfg['grid_ef']} tCO₂/MWh", indirect, "indirect",
             formula=_elec_formula(elec, indirect, cfg)),
    ]
    r["notes"] = ["焦炉约 75% 的碳进入焦炭(后续入高炉)，作为中间产品碳离开本工序",
                  "焦炭产品碳已按物料连线流入高炉（焦炭碳节点 → 高炉），构成 煤→焦炉→高炉 碳素流闭环；高炉焦炭外源仅含自产不足部分"]
    _purchases(r, coal=coal)                 # 外购：入炉炼焦煤（自产焦炭成本随煤计入）
    return r


def calc_reheat(p, cfg=DEFAULT_FACTORS):
    steel = p.get("steel_in", 0.0)
    ng_m3 = p.get("ng_rate", 0.0) * steel                    # m³/h（气体按体积，ng_rate 单位 m³/t）
    direct = fuel_carbon(ng_m3, "ng", cfg)
    elec = p.get("electricity", steel * 0.008)               # 8 kWh/t（风机/助燃/传动）
    indirect = elec * cfg["grid_ef"]
    r = _base()
    r.update(co2_direct=direct, co2_indirect=indirect, carbon_in=direct / CO2_PER_C,
             carbon_to_co2=direct / CO2_PER_C, steel_output=steel,
             carbon_by_fuel={"ng": direct / CO2_PER_C})
    r["ledger"] = [
        _led("天然气(加热燃料)", ng_m3, "m³/h", "NCV×CC×44/12", direct, "direct",
             formula=_fuel_formula("ng", ng_m3, direct, cfg)),
        _led("外购电力", elec, "MWh/h", f"电网因子 {cfg['grid_ef']} tCO₂/MWh", indirect, "indirect",
             formula=_elec_formula(elec, indirect, cfg)),
    ]
    r["notes"] = ["加热炉以天然气加热钢坯，直接碳排来自燃气燃烧"]
    return r


def _flux_co2(flux_t: float, cfg: Dict, dolomite_ratio: float = 0.0) -> Dict:
    """碳酸盐分解排放：石灰石 + 白云石，按各自标准因子。"""
    limestone = flux_t * (1 - dolomite_ratio)
    dolomite = flux_t * dolomite_ratio
    co2 = limestone * cfg["carbonate"]["limestone"] + dolomite * cfg["carbonate"]["dolomite"]
    return {"co2": co2, "limestone": limestone, "dolomite": dolomite}


def _bf_effective_fuel(p):
    """高炉「操作参数 + 富氧派生煤比 + 喷煤置换 → 工艺状态(焦比/煤比)」的耦合推导。

    返回 (coke_rate, coal_inj, op_mode, info)。
    - 喷煤置换（无条件，节点定义了煤比即生效）：有效煤比偏离名义基准(175 kg/tFe)时，
      焦比按 Δ焦比 = −RR × Δ煤比 反向联动（RR = 喷煤置换比，Geerdes 公式，
      成分见 factors.PULVERIZED_COAL_COMP，当前 ≈ 0.71）。
    - 富氧为「派生煤比」通道（不再直接节焦）：每 +1% 富氧允许多喷 15 kg/tFe 煤粉
      （BF_OXY_COAL_PER_PCT，实测出处见 factors.py），有效煤比 = 设定煤比 + 15×富氧率，
      再经喷煤置换联动降低焦比。
    - op_mode=True：节点带操作参数(风量/风温/富氧/抽力)，按相对「名义工况」
      (风温 1250℃ / 抽力 1.0) 的偏离叠加扰动推算（风温/抽力直接节焦）；否则只应用
      喷煤置换项。
    - 风量是产量通道：提高铁水产量但单位焦比不变，不参与焦比/煤比推算。
    - 设定煤比原样读取（输入值即基准），不再做总燃料比守恒补偿。
    """
    ref_coke = p.get("coke_rate")
    ref_coal = p.get("coal_inj")
    wind = p.get("wind_rate")
    t_blast = p.get("hot_blast_temp")
    # 纯氧流量 o2_flow(Nm³/h) 优先：按物理混合反算富氧率%（与前端 tft.enrichFromFlow 口径一致）；
    # 缺省时回退原 oxygen_enrich 参数（兼容存量工况）。
    o2 = p.get("oxygen_enrich")
    o2_flow = p.get("o2_flow")
    hm = p.get("hot_metal") or 0
    if o2_flow is not None and wind and hm:
        b_air = wind * 1000.0 / hm
        b_o2 = o2_flow / hm if hm else 0.0  # o2_flow 单位 Nm³/h，已是绝对流量，无需 ×1000
        o2_frac = (b_air * 0.21 + b_o2) / (b_air + b_o2) if (b_air + b_o2) else 0.21
        o2 = max(0.0, (o2_frac - 0.21) * 100)
    draft = p.get("draft")
    has_op = any(v is not None for v in (wind, t_blast, o2, draft))
    base_coke = ref_coke if ref_coke is not None else 470
    # 富氧派生煤比：设定煤比为基准，富氧每 +1% 允许多喷 15 kg/tFe；无煤比参数时不派生
    coal_base = _clamp(ref_coal, 0, 260) if ref_coal is not None else None
    coal_oxy = (BF_OXY_COAL_PER_PCT * o2) if o2 is not None else 0.0
    coal = _clamp(coal_base + coal_oxy, 0, 260) if coal_base is not None else 150
    # 喷煤置换：Δ焦比 = −RR × (有效煤比 − 名义基准煤比 175)；无煤比参数时不耦合
    d_coke = -RR * (coal - BF_COAL_REF) if coal_base is not None else 0.0
    if has_op:
        temp_f = (t_blast / 1250.0) if t_blast is not None else 1.0
        draft_f = draft if draft is not None else 1.0
        # 风温↑/抽力↑ → 焦比下降（敏感性系数经验取值，与前端 dCoke 完全一致）；
        # 富氧不直接节焦，其作用经「派生煤比 → 喷煤置换 → 焦比联动」体现
        d_coke += -250 * (temp_f - 1) - 30 * (draft_f - 1)
    coke = _clamp(base_coke + d_coke, 300, 560)
    info = {
        "wind_rate": wind, "hot_blast_temp": t_blast, "oxygen_enrich": o2, "draft": draft,
        "coke_rate_base": round(base_coke, 1),
        "coke_rate_derived": round(coke, 1),
        "coal_inj_base": round(coal_base if coal_base is not None else 150, 1),
        "coal_inj_derived": round(coal, 1),
        "coal_oxy_inc": round(coal_oxy, 1),
        "replacement_ratio": round(RR, 3),
    }
    return coke, coal, has_op, info


# 高炉排放核算口径开关：
#   "gb"      —— 国标企业核算式：入碳按 E = AD × NCV(收到基低位发热量) × CC × 44/12
#                （AD 为燃料消耗量），排放 CO₂ = 入碳 − 产品带出碳（铁水溶碳 4.5%、
#                渣带碳 3%，以未氧化形态随产品/副产品离开工序，予以扣除）；
#   "balance" —— 碳平衡法演示口径：数学上与国标式一致，但保留完整碳素流字段
#                （carbon_to_steel / carbon_to_slag / carbon_to_co2），用于碳流可视化。
BF_EMISSION_METHOD = "gb"


def calc_bf(p, cfg=DEFAULT_FACTORS):
    hm = p.get("hot_metal", 0.0)
    coke_rate, coal_inj, op_mode, op_info = _bf_effective_fuel(p)
    coke_t = hm * coke_rate / 1000.0                       # t/h 焦炭
    coal_t = hm * coal_inj / 1000.0                        # t/h 喷吹煤
    direct_coke = fuel_carbon(coke_t, "coke", cfg)
    direct_coal = fuel_carbon(coal_t, "coal", cfg)
    c_coke = direct_coke / CO2_PER_C
    c_coal = direct_coal / CO2_PER_C
    c_in = c_coke + c_coal
    c_steel = hm * METAL_C["hot_metal"]                    # 铁水溶解碳（碳平衡法扣减项）
    slag_rate = p.get("slag_rate", 300.0)                  # 渣比 kg/t 铁（默认 300）
    slag_t = hm * slag_rate / 1000.0                       # t/h 高炉渣
    c_slag = slag_t * METAL_C["bf_slag"]                   # 炉渣带走碳
    flux = _flux_co2(hm * p.get("flux", 0.0) / 1000.0, cfg)
    flux_co2 = flux["co2"]
    elec = p.get("electricity", hm * 0.03)
    indirect = elec * cfg["grid_ef"]
    r = _base()

    if BF_EMISSION_METHOD == "balance":
        # —— 碳平衡法（原实现）——
        c_to_co2 = (c_in - c_steel - c_slag) + flux_co2 / CO2_PER_C
        direct = (c_in - c_steel - c_slag) * CO2_PER_C + flux_co2
        r.update(co2_direct=direct, co2_indirect=indirect,
                 carbon_in=c_in + flux_co2 / CO2_PER_C,
                 carbon_to_steel=c_steel, carbon_to_slag=c_slag, carbon_to_co2=c_to_co2,
                 steel_output=hm, carbon_by_fuel={"coke": c_coke, "coal": c_coal})
        r["ledger"] = [
            _led("焦炭", coke_t, "t/h", "NCV×CC×44/12", direct_coke, "direct",
                 formula=_fuel_formula("coke", coke_t, direct_coke, cfg)),
            _led("喷吹煤粉", coal_t, "t/h", "NCV×CC×44/12", direct_coal, "direct",
                 formula=_fuel_formula("coal", coal_t, direct_coal, cfg)),
            _led("熔剂(石灰石分解)", flux["limestone"], "t/h", f"分解因子 {cfg['carbonate']['limestone']} tCO₂/t", flux_co2, "direct",
                 formula=_carbonate_formula(flux["limestone"], flux_co2, cfg)),
            _led("铁水溶解碳(未排放)", c_steel, "tC/h", f"铁水含碳 {METAL_C['hot_metal']*100:.1f}% 进入钢水", 0.0, "direct",
                 formula=f"{c_steel:.1f} tC 进入钢水（不排放）"),
            _led("炉渣带走碳(未排放)", c_slag, "tC/h", f"渣比 {slag_rate:.0f} kg/t · 渣含碳 {METAL_C['bf_slag']*100:.1f}% 进入高炉渣", 0.0, "direct",
                 formula=f"{slag_t:.1f} t 渣 × {METAL_C['bf_slag']*100:.1f}% = {c_slag:.1f} tC 进入渣（不排放）"),
            _led("外购电力", elec, "MWh/h", f"电网因子 {cfg['grid_ef']} tCO₂/MWh", indirect, "indirect",
                 formula=_elec_formula(elec, indirect, cfg)),
        ]
        notes = ["铁水约 4.5% 的碳以溶解碳进入钢水，不计入 CO₂ 排放",
                 "炉渣带走碳（渣含碳约 3%）随水淬渣排出，不计入 CO₂ 排放，物料平衡须单独扣减",
                 "高炉是长流程钢厂最大的直接碳排源"]
    else:
        # —— 国标企业核算式：燃料入碳 AD×NCV×CC×44/12，扣除产品带出碳 ——
        deduct_steel = c_steel * CO2_PER_C
        deduct_slag = c_slag * CO2_PER_C
        direct = direct_coke + direct_coal + flux_co2 - deduct_steel - deduct_slag
        c_to_co2 = (c_in - c_steel - c_slag) + flux_co2 / CO2_PER_C
        r.update(co2_direct=direct, co2_indirect=indirect,
                 carbon_in=c_in + flux_co2 / CO2_PER_C,
                 carbon_to_steel=c_steel, carbon_to_slag=c_slag, carbon_to_co2=c_to_co2,
                 steel_output=hm, carbon_by_fuel={"coke": c_coke, "coal": c_coal})
        r["ledger"] = [
            _led("焦炭(国标式入碳)", coke_t, "t/h", "AD×NCV×CC×44/12", direct_coke, "direct",
                 formula=_fuel_formula("coke", coke_t, direct_coke, cfg)),
            _led("喷吹煤粉(国标式入碳)", coal_t, "t/h", "AD×NCV×CC×44/12", direct_coal, "direct",
                 formula=_fuel_formula("coal", coal_t, direct_coal, cfg)),
            _led("熔剂(石灰石分解)", flux["limestone"], "t/h", f"分解因子 {cfg['carbonate']['limestone']} tCO₂/t", flux_co2, "direct",
                 formula=_carbonate_formula(flux["limestone"], flux_co2, cfg)),
            _led("产品带出碳扣减(铁水)", c_steel, "tC/h",
                 f"铁水含碳 {METAL_C['hot_metal']*100:.1f}% 随产品带出（未氧化），按国标企业核算扣除",
                 -deduct_steel, "direct",
                 formula=f"-{c_steel:.1f} tC/h × 44/12 = -{deduct_steel:.1f} tCO₂/h"),
            _led("副产品带出碳扣减(炉渣)", c_slag, "tC/h",
                 f"渣比 {slag_rate:.0f} kg/t · 渣含碳 {METAL_C['bf_slag']*100:.1f}% 随渣带出（未氧化），予以扣除",
                 -deduct_slag, "direct",
                 formula=f"-{c_slag:.1f} tC/h × 44/12 = -{deduct_slag:.1f} tCO₂/h"),
            _led("外购电力", elec, "MWh/h", f"电网因子 {cfg['grid_ef']} tCO₂/MWh", indirect, "indirect",
                 formula=_elec_formula(elec, indirect, cfg)),
        ]
        notes = ["直接排放按国标企业核算式：入碳 = AD×NCV×CC×44/12（消耗量×收到基低位发热量×单位热值含碳量）",
                 "扣除产品带出碳：铁水溶碳 "
                 f"{METAL_C['hot_metal']*100:.1f}%（−{deduct_steel:.0f} tCO₂/h）与渣带碳 "
                 f"{METAL_C['bf_slag']*100:.1f}%（−{deduct_slag:.0f} tCO₂/h），未氧化碳不计入排放",
                 "高炉是长流程钢厂最大的直接碳排源"]
    if op_mode:
        parts = []
        if op_info.get("wind_rate") is not None:
            parts.append(f"风量{op_info['wind_rate']} kNm³/h(鼓风机供给)")
        if op_info.get("hot_blast_temp") is not None:
            parts.append(f"风温{op_info['hot_blast_temp']}℃(热风炉供给)")
        if op_info.get("oxygen_enrich") is not None:
            parts.append(f"富氧{op_info['oxygen_enrich']}%")
        if op_info.get("draft") is not None:
            parts.append(f"炉顶抽力×{op_info['draft']}(引风机供给)")
        r["ledger"].append(_led(
            "操作参数推算(焦比/煤比)", 0.0, "",
            "风量/风温/抽力/富氧 → 焦比↓·煤比↑（由独立工辅经物料连线供给）", 0.0, "direct",
            formula=f"{' + '.join(parts)} → 推算焦比 {op_info['coke_rate_derived']} kg/t、煤比 {op_info['coal_inj_derived']} kg/t（基准 {op_info['coke_rate_base']}/{op_info['coal_inj_base']}）"))
        notes.insert(0, "操作驱动模式（数据由独立工辅经物料连线耦合）：" + "、".join(parts) +
            f" → 推算焦比 {op_info['coke_rate_derived']} kg/t、煤比 {op_info['coal_inj_derived']} kg/t"
            f"（基准 {op_info['coke_rate_base']}/{op_info['coal_inj_base']} kg/t）")
    r["notes"] = notes
    _purchases(r, coke=coke_t, coal=coal_t,           # 外购：焦炭(需求−焦炉自产差额于 simulate 补正)/喷吹煤
               limestone=flux["limestone"] + flux["dolomite"])  # 外购：熔剂（石灰石+白云石）
    return r


def calc_h2bf(p, cfg=DEFAULT_FACTORS):
    """氢冶金高炉：以 H2 部分/全部替代焦炭还原，直接碳排极低；间接碳来自制氢电耗。"""
    hm = p.get("hot_metal", 0.0)
    h2_rate = p.get("h2_rate") or 90.0                       # kg/t 铁（氢耗，默认 90）
    coal_t = hm * p.get("coal_inj", 10) / 1000.0             # 仅少量补偿煤
    direct_coal = fuel_carbon(coal_t, "coal", cfg)
    c_in = direct_coal / CO2_PER_C
    # 氢冶金以 H₂ 还原，铁水几乎不渗碳，含碳取接近成品钢的低值（远低于常规高炉 4.5%）
    c_steel = hm * METAL_C["steel"]
    c_to_co2 = max(c_in - c_steel, 0.0)
    direct = c_to_co2 * CO2_PER_C
    # 电解制氢电耗：h2_rate(kg/t) × hm × 55 kWh/kgH₂ / 1000 = MWh/h
    elec = p.get("electricity", h2_rate * hm / 1000.0 * 55)
    indirect = elec * cfg["grid_ef"]
    r = _base()
    r.update(co2_direct=direct, co2_indirect=indirect, carbon_in=c_in,
             carbon_to_steel=c_steel, carbon_to_co2=c_to_co2, steel_output=hm,
             carbon_by_fuel={"elec": indirect / CO2_PER_C})
    r["ledger"] = [
        _led("补偿燃料(煤)", coal_t, "t/h", "NCV×CC×44/12", direct, "direct",
             formula=_fuel_formula("coal", coal_t, direct, cfg)),
        _led("铁水溶解碳(未排放)", c_steel, "tC/h", f"氢冶金铁水含碳约 {METAL_C['steel']*100:.1f}%（H₂ 不渗碳），进入钢水", 0.0, "direct",
             formula=f"{c_steel:.1f} tC 进入钢水（不排放）"),
        _led("电解制氢电耗", elec, "MWh/h", f"电网因子 {cfg['grid_ef']} tCO₂/MWh（绿电可近零）", indirect, "indirect",
             formula=_elec_formula(elec, indirect, cfg)),
    ]
    r["notes"] = ["以 H₂ 替代焦炭作还原剂，直接碳排极低；碳排主要来自制氢电耗",
                  "氢冶金铁水几乎不渗碳，溶解碳远低于常规高炉",
                  "若制氢采用绿电，则该环节近零碳"]
    _purchases(r, coal=coal_t)               # 外购：少量补偿煤
    return r


def calc_h2dri(p, cfg=DEFAULT_FACTORS):
    """氢基直接还原竖炉：纯 H₂ 还原铁氧化物，产物为水，直接碳排近零。"""
    dri = p.get("dri_out", 0.0)
    h2_rate = p.get("h2_rate") or 90.0                       # kg/t DRI（氢耗，默认 90）
    h2 = h2_rate * dri / 1000.0
    # 电解制氢电耗：h2_rate(kg/t) × dri × 55 kWh/kgH₂ / 1000 = MWh/h
    elec = p.get("electricity", h2_rate * dri / 1000.0 * 55)
    indirect = elec * cfg["grid_ef"]
    r = _base()
    r.update(co2_direct=0.0, co2_indirect=indirect, carbon_in=0.0,
             carbon_to_co2=0.0, carbon_to_steel=0.0, steel_output=dri,
             carbon_by_fuel={"elec": indirect / CO2_PER_C})
    r["ledger"] = [
        _led("氢气(绿氢)", h2, "t/h", "还原产物为 H₂O，直接碳排近零", 0.0, "direct",
             formula="H₂ 还原产物为 H₂O，直接碳排≈0"),
        _led("电解制氢电耗", elec, "MWh/h", f"电网因子 {cfg['grid_ef']} tCO₂/MWh（绿电可近零）", indirect, "indirect",
             formula=_elec_formula(elec, indirect, cfg)),
    ]
    r["notes"] = ["绿氢直接还原：还原产物为水，直接碳排近零；碳排取决于制氢电力结构",
                  "是长流程高炉最具潜力的深度脱碳替代路线之一"]
    return r


def calc_dri(p, cfg=DEFAULT_FACTORS):
    """Midrex 竖炉直接还原：以天然气重整气还原铁氧化物。"""
    pellets = p.get("pellet_rate", 0.0)
    dri = p.get("dri_out") or pellets * 0.65
    ng_m3 = p.get("ng_rate", 0.0) * dri                       # m³/h（ng_rate 单位 m³/t-DRI，≈260–320）
    direct = fuel_carbon(ng_m3, "ng", cfg)
    elec = p.get("electricity", dri * 0.15)                  # 150 kWh/t-DRI（压缩/换热/传动）
    indirect = elec * cfg["grid_ef"]
    # DRI 产品固碳：天然气重整气中约 0.18% 碳固结于 DRI 金属（中间产品碳，随物料链流入电炉），
    # 其余碳以 CO₂ 排出。固碳部分不再计入本工序排放，避免碳素流中「产品碳无来源」的失衡。
    dri_c = dri * METAL_C["dri"]
    c_ng = direct / CO2_PER_C
    c_to_co2 = max(c_ng - dri_c, 0.0)
    co2_direct = c_to_co2 * CO2_PER_C
    r = _base()
    r.update(co2_direct=co2_direct, co2_indirect=indirect, carbon_in=c_ng,
             carbon_to_co2=c_to_co2, carbon_to_product=dri_c, steel_output=dri,
             carbon_by_fuel={"ng": c_ng})
    r["ledger"] = [
        _led("天然气(重整还原气)", ng_m3, "m³/h", "NCV×CC×44/12", direct, "direct",
             formula=_fuel_formula("ng", ng_m3, direct, cfg)),
        _led("DRI固碳(中间产品)", dri, "t/h", f"含碳 {METAL_C['dri']*100:.1f}%，自天然气碳中扣减", -dri_c * CO2_PER_C,
             "direct", formula=f"{dri:.0f} × {METAL_C['dri']} × 44/12 = {dri_c * CO2_PER_C:.1f}"),
        _led("外购电力(压缩/换热)", elec, "MWh/h", f"电网因子 {cfg['grid_ef']} tCO₂/MWh", indirect, "indirect",
             formula=_elec_formula(elec, indirect, cfg)),
    ]
    r["notes"] = ["DRI 以天然气重整气还原铁氧化物；若改用绿氢则直接碳排近零",
                  "所得 DRI 通常供电炉炼钢，构成短流程低碳路线",
                  f"DRI 产品固碳 {dri_c:.1f} tC/h 作为中间产品碳随物料连线流入电炉，不重复计入本工序排放"]
    return r


def calc_smelt(p, cfg=DEFAULT_FACTORS):
    """熔融还原(Corex/Finex)：以非炼焦煤粉为还原剂与燃料，直接碳排较高。"""
    ore = p.get("ore_rate", 0.0)
    coal_t = p.get("coal_rate", 0.0)
    direct = fuel_carbon(coal_t, "coal", cfg)
    elec = p.get("electricity", ore * 0.04)                  # 40 kWh/t（制氧+气化炉驱动）
    indirect = elec * cfg["grid_ef"]
    r = _base()
    r.update(co2_direct=direct, co2_indirect=indirect, carbon_in=direct / CO2_PER_C,
             carbon_to_co2=direct / CO2_PER_C, steel_output=ore * 0.95,
             carbon_by_fuel={"coal": direct / CO2_PER_C})
    r["ledger"] = [
        _led("非炼焦煤粉", coal_t, "t/h", "NCV×CC×44/12", direct, "direct",
             formula=_fuel_formula("coal", coal_t, direct, cfg)),
        _led("外购电力", elec, "MWh/h", f"电网因子 {cfg['grid_ef']} tCO₂/MWh", indirect, "indirect",
             formula=_elec_formula(elec, indirect, cfg)),
    ]
    r["notes"] = ["熔融还原以非炼焦煤粉为还原剂与燃料，省去焦炉，但直接碳排仍较高",
                  "可与 CCS/绿电耦合进一步降碳"]
    _purchases(r, coal=coal_t, iron_ore=ore) # 外购：非炼焦煤粉 + 铁矿石
    return r


def calc_biochar(p, cfg=DEFAULT_FACTORS):
    """生物质碳喷吹：以生物质碳替代部分化石碳，生命周期视为碳中性。"""
    biomass = p.get("biomass_rate", 0.0)
    elec = p.get("electricity", biomass * 0.1)               # 100 kWh/t（破碎/输送/喷吹）
    indirect = elec * cfg["grid_ef"]
    # 生物质碳（tC/h）：按 NCV×CC 计，源自大气 CO₂ 光合固碳，生命周期净零（不计入直接排放）
    bf = cfg["fuels"]["biomass"]
    bio_c = biomass * bf["ncv"] * bf["cc"]
    r = _base()
    r.update(co2_direct=0.0, co2_indirect=indirect, carbon_in=bio_c,
             carbon_to_co2=0.0, carbon_to_product=bio_c, steel_output=biomass,
             carbon_by_fuel={"biomass": bio_c, "elec": indirect / CO2_PER_C})
    r["ledger"] = [
        _led("生物质碳(碳中性)", biomass, "t/h", "源自大气 CO₂ 光合固碳，生命周期净零", 0.0, "direct",
             formula=f"{biomass:.1f} t × {bf['ncv']:.2f} GJ/t × {bf['cc']:.4f} tC/GJ = {bio_c:.1f} tC/h（不排放）"),
        _led("外购电力", elec, "MWh/h", f"电网因子 {cfg['grid_ef']} tCO₂/MWh", indirect, "indirect",
             formula=_elec_formula(elec, indirect, cfg)),
    ]
    r["notes"] = ["生物质碳来自大气 CO₂ 光合固碳，生命周期视为净零，可抵消等量化石碳排",
                  "属未来减排工艺（BECCS 思路）",
                  "生物质碳/能量已计入碳素流与能流桑基图（源：生物质碳/生物质），碳排放按 0 计"]
    _purchases(r, biomass=biomass)           # 外购：生物质碳（破碎/输送/喷吹用电已按电力自动汇总）
    return r


def calc_bof(p, cfg=DEFAULT_FACTORS):
    hm = p.get("hot_metal_in", 0.0)
    scrap = p.get("scrap", 0.0)
    c_in = hm * METAL_C["hot_metal"] + scrap * METAL_C["scrap"]
    steel = hm + scrap
    c_steel = steel * METAL_C["steel"]
    slag_rate = p.get("slag_rate", 120.0)                  # 转炉渣比 kg/t 钢（默认 120）
    slag_t = steel * slag_rate / 1000.0                    # t/h 钢渣
    c_slag = slag_t * METAL_C["steel_slag"]                # 钢渣带走碳（未排放）
    c_to_co2 = max(c_in - c_steel - c_slag, 0.0)
    flux = _flux_co2(hm * p.get("flux", 0.0) / 1000.0, cfg)
    flux_co2 = flux["co2"]
    direct = c_to_co2 * CO2_PER_C + flux_co2
    elec = p.get("electricity", steel * 0.03)                # 30 kWh/t（一次除尘风机+倾动+上料）
    indirect = elec * cfg["grid_ef"]
    r = _base()
    r.update(co2_direct=direct, co2_indirect=indirect, carbon_in=c_in + flux_co2 / CO2_PER_C,
             carbon_to_steel=c_steel, carbon_to_slag=c_slag,
             carbon_to_co2=c_to_co2 + flux_co2 / CO2_PER_C,
             steel_output=steel, carbon_by_fuel={"steel_c": c_in})
    r["ledger"] = [
        _led("金属料脱碳(铁水+废钢)", c_to_co2, "tC/h", "铁水/废钢含碳，氧化为 CO₂", c_to_co2 * CO2_PER_C, "direct",
             formula=f"{c_to_co2:.1f} tC × 3.667 = {c_to_co2 * CO2_PER_C:.0f} tCO₂/h"),
        _led("熔剂(石灰石分解)", flux["limestone"], "t/h", f"分解因子 {cfg['carbonate']['limestone']} tCO₂/t", flux_co2, "direct",
             formula=_carbonate_formula(flux["limestone"], flux_co2, cfg)),
        _led("炉渣带走碳(未排放)", c_slag, "tC/h", f"渣比 {slag_rate:.0f} kg/t · 渣含碳 {METAL_C['steel_slag']*100:.1f}% 进入钢渣", 0.0, "direct",
             formula=f"{slag_t:.1f} t 渣 × {METAL_C['steel_slag']*100:.1f}% = {c_slag:.1f} tC 进入渣（不排放）"),
        _led("外购电力", elec, "MWh/h", f"电网因子 {cfg['grid_ef']} tCO₂/MWh", indirect, "indirect",
             formula=_elec_formula(elec, indirect, cfg)),
    ]
    r["notes"] = ["脱碳反应将金属料中的碳氧化为 CO₂，是转炉主要直接排放源",
                  "炉渣带走碳（渣含碳约 1.5%）随钢渣排出，不计入 CO₂ 排放，物料平衡须单独扣减",
                  "提高废钢比可降低单位碳排"]
    _purchases(r, scrap=scrap,               # 外购：废钢（铁水为中间产品不购）
               limestone=flux["limestone"] + flux["dolomite"])  # 外购：熔剂（石灰石+白云石）
    return r


def calc_eaf(p, cfg=DEFAULT_FACTORS):
    scrap = p.get("scrap", 0.0)
    dri = p.get("dri", 0.0)
    c_metal = scrap * METAL_C["scrap"] + dri * METAL_C["dri"]   # 金属料带入碳
    steel = scrap + dri
    c_steel = steel * METAL_C["steel"]                          # 终点钢水含碳
    c_carb = max(c_steel - c_metal, 0.0)                        # 渗碳/造渣追加碳（电极溶解+喂碳），进入钢水不排放
    c_to_co2_metal = max(c_metal - c_steel, 0.0)               # 金属料残碳氧化为 CO₂
    # 电极消耗（过程直接排放）：约 2 kg/t 钢，7000 t/h → 14 t/h
    electrode = p.get("electrode", steel * 0.002)       # t/h
    elec_co2 = electrode * cfg["electrode_ef"]
    elec_c = elec_co2 / CO2_PER_C
    # 外购电力（间接排放）：电弧炉吨钢电耗约 400 kWh/t（冶炼+公辅）
    elec = p.get("electricity", steel * 0.4)
    indirect = elec * cfg["grid_ef"]
    direct = c_to_co2_metal * CO2_PER_C + elec_co2
    r = _base()
    r.update(co2_direct=direct, co2_indirect=indirect,
             carbon_in=c_metal + elec_c + c_carb, carbon_to_steel=c_steel,
             carbon_to_co2=c_to_co2_metal + elec_c, steel_output=steel,
             carbon_by_fuel={"elec": indirect / CO2_PER_C, "electrode": elec_c, "carburizer": c_carb})
    r["ledger"] = [
        _led("金属料残碳氧化", c_to_co2_metal, "tC/h", "废钢/DRI 残碳氧化为 CO₂", c_to_co2_metal * CO2_PER_C, "direct",
             formula=f"{c_to_co2_metal:.1f} tC × 3.667 = {c_to_co2_metal * CO2_PER_C:.0f} tCO₂/h"),
        _led("渗碳/造渣追加碳(入钢水)", c_carb, "tC/h", "为达终点钢水含碳，追加电极溶解与喂碳碳量", 0.0, "direct",
             formula=f"终点钢水碳 {c_steel:.1f} − 金属料碳 {c_metal:.1f} = {c_carb:.1f} tC（进入钢水，不排放）"),
        _led("电极消耗", electrode, "t/h", f"电极排放因子 {cfg['electrode_ef']} tCO₂/t", elec_co2, "direct",
             formula=_electrode_formula(electrode, elec_co2, cfg)),
        _led("外购电力(电弧加热)", elec, "MWh/h", f"电网因子 {cfg['grid_ef']} tCO₂/MWh", indirect, "indirect",
             formula=_elec_formula(elec, indirect, cfg)),
    ]
    r["notes"] = ["以废钢/DRI 为原料，直接碳排很低，碳排主要来自电耗与电极消耗",
                  "使用绿电+高废钢比可实现近零碳电炉钢",
                  "钢水含碳高于金属料时，差额由电极溶解/喂碳补足（已计入 carbon_in，不额外排放）"]
    _purchases(r, scrap=scrap,               # 外购：废钢（DRI 视中间产品，随物料连线已由前道计入）
               electrode=electrode)          # 外购：石墨电极
    return r


def calc_lf(p, cfg=DEFAULT_FACTORS):
    steel = p.get("steel_in", 0.0)
    elec = p.get("electricity", steel * 0.025)               # 25 kWh/t（LF 电弧加热+搅拌）
    indirect = elec * cfg["grid_ef"]
    r = _base()
    r.update(co2_indirect=indirect, carbon_in=0.0,
             carbon_to_co2=0.0, steel_output=steel,
             carbon_by_fuel={"elec": indirect / CO2_PER_C})
    r["ledger"] = [
        _led("外购电力(电弧加热/搅拌)", elec, "MWh/h", f"电网因子 {cfg['grid_ef']} tCO₂/MWh", indirect, "indirect",
             formula=_elec_formula(elec, indirect, cfg)),
    ]
    r["notes"] = ["精炼炉以电加热与合金化为主，仅间接排放（范围二，不计入物料碳平衡）"]
    return r


def calc_rh(p, cfg=DEFAULT_FACTORS):
    steel = p.get("steel_in", 0.0)
    elec = p.get("electricity", steel * 0.005)               # 5 kWh/t（真空泵）
    indirect = elec * cfg["grid_ef"]
    r = _base()
    r.update(co2_indirect=indirect, carbon_in=0.0,
             carbon_to_co2=0.0, steel_output=steel,
             carbon_by_fuel={"elec": indirect / CO2_PER_C})
    r["ledger"] = [
        _led("外购电力(真空泵)", elec, "MWh/h", f"电网因子 {cfg['grid_ef']} tCO₂/MWh", indirect, "indirect",
             formula=_elec_formula(elec, indirect, cfg)),
    ]
    r["notes"] = ["RH 真空精炼以真空泵电耗为主，间接排放（范围二，不计入物料碳平衡）"]
    return r


def calc_vd(p, cfg=DEFAULT_FACTORS):
    steel = p.get("steel_in", 0.0)
    elec = p.get("electricity", steel * 0.004)               # 4 kWh/t（真空脱气）
    indirect = elec * cfg["grid_ef"]
    r = _base()
    r.update(co2_indirect=indirect, carbon_in=0.0,
             carbon_to_co2=0.0, steel_output=steel,
             carbon_by_fuel={"elec": indirect / CO2_PER_C})
    r["ledger"] = [
        _led("外购电力(真空脱气)", elec, "MWh/h", f"电网因子 {cfg['grid_ef']} tCO₂/MWh", indirect, "indirect",
             formula=_elec_formula(elec, indirect, cfg)),
    ]
    r["notes"] = ["VD 真空脱气以电耗为主，间接排放（范围二，不计入物料碳平衡）"]
    return r


def calc_aod(p, cfg=DEFAULT_FACTORS):
    steel = p.get("steel_in", 0.0)
    # 不锈钢冶炼：含高碳铬铁/返回料，钢水含碳较高（约 1.5%），终点脱碳至约 0.08%
    c_in = steel * 0.015
    c_steel = steel * 0.0008
    c_to_co2 = max(c_in - c_steel, 0.0)
    elec = p.get("electricity", steel * 0.012)               # 12 kWh/t（顶底复吹+除尘）
    direct = c_to_co2 * CO2_PER_C
    indirect = elec * cfg["grid_ef"]
    r = _base()
    r.update(co2_direct=direct, co2_indirect=indirect, carbon_in=c_in,
             carbon_to_steel=c_steel, carbon_to_co2=c_to_co2, steel_output=steel,
             carbon_by_fuel={"steel_c": c_in})
    r["ledger"] = [
        _led("金属料脱碳(不锈钢)", c_to_co2, "tC/h", "铬系钢脱碳氧化为 CO₂", direct, "direct",
             formula=f"{c_to_co2:.1f} tC × 3.667 = {direct:.0f} tCO₂/h"),
        _led("外购电力", elec, "MWh/h", f"电网因子 {cfg['grid_ef']} tCO₂/MWh", indirect, "indirect",
             formula=_elec_formula(elec, indirect, cfg)),
    ]
    r["notes"] = ["AOD 用于不锈钢精炼，吹氧/氩脱碳，有少量直接排放",
                  "可用氢/氩替代部分氧气进一步降碳"]
    return r


def calc_caster(p, cfg=DEFAULT_FACTORS):
    steel = p.get("steel_in", 0.0)
    elec = p.get("electricity", steel * 0.015)               # 15 kWh/t（结晶器振动/拉矫/切割）
    indirect = elec * cfg["grid_ef"]
    r = _base()
    r.update(co2_indirect=indirect, carbon_in=0.0,
             carbon_to_co2=0.0, steel_output=steel,
             carbon_by_fuel={"elec": indirect / CO2_PER_C})
    r["ledger"] = [
        _led("外购电力(结晶/拉矫)", elec, "MWh/h", f"电网因子 {cfg['grid_ef']} tCO₂/MWh", indirect, "indirect",
             formula=_elec_formula(elec, indirect, cfg)),
    ]
    r["notes"] = ["连铸以电耗为主，碳排较低（范围二，不计入物料碳平衡）"]
    return r


def calc_ingot(p, cfg=DEFAULT_FACTORS):
    steel = p.get("steel_in", 0.0)
    ng_m3 = p.get("ng_rate", 0.0) * steel                    # m³/h（ng_rate 单位 m³/t）
    direct = fuel_carbon(ng_m3, "ng", cfg)
    elec = p.get("electricity", steel * 0.008)               # 8 kWh/t（均热炉风机/行车）
    indirect = elec * cfg["grid_ef"]
    r = _base()
    r.update(co2_direct=direct, co2_indirect=indirect, carbon_in=direct / CO2_PER_C,
             carbon_to_co2=direct / CO2_PER_C, steel_output=steel,
             carbon_by_fuel={"ng": direct / CO2_PER_C})
    r["ledger"] = [
        _led("保温燃气(均热炉)", ng_m3, "m³/h", "NCV×CC×44/12", direct, "direct",
             formula=_fuel_formula("ng", ng_m3, direct, cfg)),
        _led("外购电力", elec, "MWh/h", f"电网因子 {cfg['grid_ef']} tCO₂/MWh", indirect, "indirect",
             formula=_elec_formula(elec, indirect, cfg)),
    ]
    r["notes"] = ["模铸需均热保温，有少量燃气直接排放"]
    return r


def calc_roll(p, cfg=DEFAULT_FACTORS):
    steel = p.get("steel_in", 0.0)
    ng_m3 = p.get("ng_rate", 0.0) * steel                    # m³/h（ng_rate 单位 m³/t）
    direct = fuel_carbon(ng_m3, "ng", cfg)
    elec = p.get("electricity", steel * 0.08)                # 80 kWh/t（主传动+风机+卷取）
    indirect = elec * cfg["grid_ef"]
    r = _base()
    r.update(co2_direct=direct, co2_indirect=indirect, carbon_in=direct / CO2_PER_C,
             carbon_to_co2=direct / CO2_PER_C, steel_output=steel,
             carbon_by_fuel={"ng": direct / CO2_PER_C, "elec": indirect / CO2_PER_C})
    r["ledger"] = [
        _led("天然气(退火炉)", ng_m3, "m³/h", "NCV×CC×44/12", direct, "direct",
             formula=_fuel_formula("ng", ng_m3, direct, cfg)),
        _led("外购电力(轧制)", elec, "MWh/h", f"电网因子 {cfg['grid_ef']} tCO₂/MWh", indirect, "indirect",
             formula=_elec_formula(elec, indirect, cfg)),
    ]
    r["notes"] = ["热轧以轧制电耗为主，加热/退火炉有燃气直接排放（电耗为范围二）"]
    return r


def calc_cold(p, cfg=DEFAULT_FACTORS):
    steel = p.get("steel_in", 0.0)
    ng_m3 = p.get("ng_rate", 0.0) * steel                    # m³/h（ng_rate 单位 m³/t）
    direct = fuel_carbon(ng_m3, "ng", cfg)
    elec = p.get("electricity", steel * 0.1)                 # 100 kWh/t（轧机+退火电炉+酸洗）
    indirect = elec * cfg["grid_ef"]
    r = _base()
    r.update(co2_direct=direct, co2_indirect=indirect, carbon_in=direct / CO2_PER_C,
             carbon_to_co2=direct / CO2_PER_C, steel_output=steel,
             carbon_by_fuel={"ng": direct / CO2_PER_C, "elec": indirect / CO2_PER_C})
    r["ledger"] = [
        _led("退火炉燃气", ng_m3, "m³/h", "NCV×CC×44/12", direct, "direct",
             formula=_fuel_formula("ng", ng_m3, direct, cfg)),
        _led("外购电力(冷轧)", elec, "MWh/h", f"电网因子 {cfg['grid_ef']} tCO₂/MWh", indirect, "indirect",
             formula=_elec_formula(elec, indirect, cfg)),
    ]
    r["notes"] = ["冷轧以轧制电耗为主，退火炉有燃气直接排放"]
    return r


RULES = {
    # 原料准备
    "sinter_plant": calc_sinter,
    "pelletizing": calc_pellet,
    "coke_oven": calc_coke,
    "reheating_furnace": calc_reheat,
    # 炼铁
    "blast_furnace": calc_bf,
    "hydrogen_bf": calc_h2bf,
    "h2_dri": calc_h2dri,
    "dri_midrex": calc_dri,
    "smelting_reduction": calc_smelt,
    "biochar_injection": calc_biochar,
    # 炼钢
    "bof": calc_bof,
    "eaf": calc_eaf,
    # 精炼
    "ladle_furnace": calc_lf,
    "rh_vacuum": calc_rh,
    "vd_vacuum": calc_vd,
    "aod": calc_aod,
    # 连铸
    "caster": calc_caster,
    "ingot_casting": calc_ingot,
    # 轧制
    "rolling_mill": calc_roll,
    "cold_rolling": calc_cold,
}


# 工辅通用计算器：从参数中累加「功率类」字段得到运行电耗（MWh/h，按 1h 计），
# 直接碳恒为 0（其驱动介质对被服务工艺的影响已在对应工艺 calc 中折入）。
def calc_energy_aux(p, cfg=DEFAULT_FACTORS):
    # 工辅电耗由其「电机功率」字段（MW）决定；其余字段（风量/煤气量/产汽等）
    # 是被服务工艺的运行工况，其碳排已在被服务工艺 calc 中计入，本工艺不再计。
    power = float(p.get("power", 0.0)) or 0.0
    # 绿电占比抵扣外购电（仅 drive_supply 等带 green_ratio 者生效）
    green_ratio = p.get("green_ratio")
    if isinstance(green_ratio, (int, float)):
        power = power * (1.0 - float(green_ratio) / 100.0)
    elec = power  # MWh/h
    indirect = elec * cfg["grid_ef"]
    r = _base()
    r.update(co2_direct=0.0, co2_indirect=indirect, carbon_in=0.0,
             carbon_to_co2=0.0, carbon_by_fuel={"elec": indirect / CO2_PER_C})
    r["ledger"] = [
        _led("工辅运行电耗", elec, "MWh/h", f"电网因子 {cfg['grid_ef']} tCO₂/MWh", indirect, "indirect",
             formula=_elec_formula(elec, indirect, cfg)),
    ]
    r["notes"] = ["独立工辅：自身不产生直接碳，仅计范围二电耗；"
                 "其输出(风量/热风/抽力/驱动电)经物料连线驱动被服务工艺参数。"]
    return r


# RULES 注册：工辅类型（鼓风机/热风炉/引风机/喷吹系统/电极调节…独立节点）。
# 自身不产直接碳，仅耗电（范围二）；对被服务工艺的影响经驱动连线折算到其参数，
# 已在被服务工艺的 calc 中计入。
for _aux_type in ("blower", "hot_blast_stove", "id_fan", "injector", "combustion_blower",
                  "drive_supply", "electrode_reg", "belt_conv", "feeder", "cool_pump",
                  "aux_boiler", "oxy_plant", "oxy_supply", "power_supply"):
    RULES[_aux_type] = calc_energy_aux


