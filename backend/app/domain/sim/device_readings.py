"""钢铁流程监测设备库与读数生成。

设计原则（对齐 GB/T 32151.5 / GHG Protocol）：
- 碳排放是「因变量」，由「活动数据（自变量）× 排放因子（系数）」算出；
- 活动数据来自现场监测设备：皮带秤（固体质量）、气体流量计（煤气/天然气体积）、
  智能电表（电耗）、料斗秤/失重秤（熔剂/喷吹）、钢水秤（产量）等；
- 去重原则：若检测设备监测的物理量恰为同工序「可调设备（设定值 SP→测定值 PV）」的
  测定值，则该检测设备不再内置，避免双源数据冲突（如烧结/球团/焦化的皮带秤对皮带机/给料机、
  高炉失重秤对喷吹系统、电炉/精炼炉电表对电极调节器）；核算统一以可调设备测定值为准。
- 本模块把每台设备建模为内置实体；compute_device_readings 依据工序的「活动数据」
  计算**仿真默认读数**（用于流程编排/仿真计算展示）。
- 实时遥测数据源已对接 MQTT（mqtt_source.py + 前端配置的云端 Broker，参照参考项目 yunduan1
  数据链路）：realtime.py 推送的设备读数一律来自 MQTT 真实数据，不再生成模拟读数。
"""

from __future__ import annotations

from typing import Any, Dict, List

from .specs import PROCESS_SPECS

# ----------------------- 设备类型元数据（内置库） -----------------------
# color 用于在 3D 图与 UI 中区分设备种类。
DEVICE_LIBRARY: Dict[str, Dict[str, Any]] = {
    "belt_scale": {
        "label": "皮带秤", "icon": "⚖️", "color": "#6f9e74",
        "measures": "固体质量流量", "unit": "t/h",
        "accuracy": "±0.5%", "range": "0–6000 t/h",
        "desc": "安装在输送皮带上的连续称重装置，计量矿、焦、煤、烧结矿、球团等固体物料的质量流量，是碳核算「活动数据」的主源头。",
    },
    "loss_in_weight": {
        "label": "失重秤", "icon": "🪨", "color": "#8a9a5b",
        "measures": "粉料/喷吹质量流量", "unit": "t/h",
        "accuracy": "±1.0%", "range": "0–500 t/h",
        "desc": "用于高炉喷吹煤粉、熔剂添加等精确给料计量的失重式喂料秤。",
    },
    "hopper_scale": {
        "label": "料斗秤", "icon": "🪣", "color": "#5f7d52",
        "measures": "批料质量", "unit": "t/批",
        "accuracy": "±0.5%", "range": "0–300 t/批",
        "desc": "配料仓/喷吹罐的批重计量，对应焦比、喷煤比、熔剂比等单耗的实测来源。",
    },
    "weigher": {
        "label": "钢水/铸坯秤", "icon": "🏋️", "color": "#5b83a8",
        "measures": "产品/半产品质量", "unit": "t/h",
        "accuracy": "±0.3%", "range": "0–400 t/h",
        "desc": "铁水罐秤、钢包秤、连铸坯秤等，计量产出侧质量，用于「钢中固碳」扣减与钢产量统计。",
    },
    "gas_flowmeter": {
        "label": "气体流量计", "icon": "💨", "color": "#c0903e",
        "measures": "气体体积流量（标态）", "unit": "m³/h",
        "accuracy": "±1.5%", "range": "0–5e6 m³/h",
        "desc": "配温度/压力补偿，计量高炉煤气(BFG)、转炉煤气(LDG)、天然气、氧气等气体体积流量，对应燃料类直接排放的「活动数据」。",
    },
    "power_meter": {
        "label": "智能电表", "icon": "⚡", "color": "#8a7bb0",
        "measures": "电功率/电量", "unit": "MWh/h",
        "accuracy": "±0.5%", "range": "0–2000 MWh/h",
        "desc": "总降/工序变压器/单台大电机的分项计量，对应范围二（外购电）间接排放的活动数据。",
    },
    "composition_analyzer": {
        "label": "成分分析仪", "icon": "🔬", "color": "#4f97a0",
        "measures": "物料成分/品位", "unit": "—",
        "accuracy": "±0.1%", "range": "—",
        "desc": "XRF/碳硫分析仪/LIBS 等，测定矿石品位、燃料实际含碳率，用以精化排放因子（替代默认 CC 假设）。",
    },
    "cems": {
        "label": "CEMS 烟气监测", "icon": "📡", "color": "#c4774a",
        "measures": "CO₂ 浓度×流量（直接排放）", "unit": "tCO₂/h",
        "accuracy": "±2.0%", "range": "—",
        "desc": "烟气排放连续监测系统，直接用 CO₂ 浓度×标态流量测得排放，作为因子法的交叉校验（点源直接监测法）。",
    },
}

# ----------------------- 各工序内置设备规格 -----------------------
# 每项：dev=设备类型, mount=在 3D 图上的挂载方位, label=设备实例名,
#       measured=实测量中文, feeds=喂给引擎的输入/公式说明。
# 读数由 compute_device_readings 依据工序活动数据计算。
_UNIT_DEVICE_SPECS: Dict[str, List[Dict[str, Any]]] = {
    "sinter_plant": [
        # 注：皮带秤·原料/燃料 已去除——本工序可调设备 皮带机/给料机 的测定值即该物理量，避免数据冲突。
        {"dev": "power_meter", "mount": "power", "label": "智能电表·烧结主抽", "measured": "烧结机电耗", "feeds": "引擎输入 electricity（范围二，自变量）"},
        {"dev": "composition_analyzer", "mount": "control", "label": "成分分析仪·烧结矿", "measured": "烧结矿品位/TFe", "feeds": "精化熔剂需求与排放因子"},
    ],
    "pelletizing": [
        # 注：皮带秤·精矿/燃料 已去除——本工序可调设备 皮带机/给料机 的测定值即该物理量，避免数据冲突。
        {"dev": "power_meter", "mount": "power", "label": "智能电表·造球辊", "measured": "造球/焙烧电耗", "feeds": "引擎输入 electricity"},
        {"dev": "composition_analyzer", "mount": "control", "label": "成分分析仪·球团", "measured": "球团品位", "feeds": "精化排放因子"},
    ],
    "coke_oven": [
        # 注：皮带秤·洗煤 已去除——本工序可调设备 皮带机 的测定值即该物理量，避免数据冲突。
        {"dev": "gas_flowmeter", "mount": "gas", "label": "气体流量计·焦炉煤气", "measured": "焦炉煤气(COG)产量", "feeds": "副产煤气利用量（能源平衡）"},
        {"dev": "power_meter", "mount": "power", "label": "智能电表·炼焦", "measured": "炼焦电耗", "feeds": "引擎输入 electricity"},
    ],
    "blast_furnace": [
        {"dev": "belt_scale", "mount": "feed", "label": "皮带秤·炉料", "measured": "烧结矿/球团/矿石入炉量", "feeds": "炉料总质量（矿量，自变量）"},
        {"dev": "belt_scale", "mount": "fuel", "label": "皮带秤·焦炭", "measured": "焦炭入炉量", "feeds": "引擎输入 coke_rate→焦碳质量"},
        # 注：失重秤·喷吹煤 已去除——本工序可调设备 喷吹系统 的测定值（喷吹速率）即该物理量，避免数据冲突。
        {"dev": "hopper_scale", "mount": "flux", "label": "料斗秤·熔剂", "measured": "石灰石/白云石添加量", "feeds": "引擎输入 flux（碳酸盐分解源）"},
        {"dev": "weigher", "mount": "product", "label": "铁水秤", "measured": "出铁量（铁水）", "feeds": "引擎输入 hot_metal / 钢中固碳扣减"},
        {"dev": "gas_flowmeter", "mount": "gas", "label": "气体流量计·高炉煤气", "measured": "高炉煤气(BFG)产量", "feeds": "煤气利用量（能源平衡）"},
        {"dev": "power_meter", "mount": "power", "label": "智能电表·鼓风/除尘", "measured": "鼓风/除尘电耗", "feeds": "引擎输入 electricity（范围二）"},
        {"dev": "composition_analyzer", "mount": "control", "label": "成分分析仪·焦炭", "measured": "焦炭固定碳含量", "feeds": "精化 CC 排放因子"},
        {"dev": "cems", "mount": "gas", "label": "CEMS·高炉烟囱", "measured": "烟囱 CO₂ 直接排放", "feeds": "因子法交叉校验（直接监测）"},
    ],
    "bof": [
        {"dev": "weigher", "mount": "feed", "label": "钢水秤·铁水/废钢", "measured": "铁水+废钢装入量", "feeds": "引擎输入 steel_in（金属料，自变量）"},
        {"dev": "hopper_scale", "mount": "flux", "label": "料斗秤·造渣熔剂", "measured": "石灰/白云石添加量", "feeds": "引擎输入 flux（碳酸盐分解源）"},
        {"dev": "gas_flowmeter", "mount": "gas", "label": "气体流量计·转炉煤气", "measured": "转炉煤气(LDG)回收量", "feeds": "煤气回收（能源平衡）"},
        {"dev": "power_meter", "mount": "power", "label": "智能电表·吹炼", "measured": "吹炼/除尘电耗", "feeds": "引擎输入 electricity"},
        {"dev": "composition_analyzer", "mount": "control", "label": "副枪·终点碳", "measured": "终点碳含量/炉气 CO/CO₂", "feeds": "交叉校验脱碳碳排"},
    ],
    "eaf": [
        {"dev": "weigher", "mount": "feed", "label": "钢水秤·废钢/DRI", "measured": "废钢+直接还原铁装入量", "feeds": "引擎输入 scrap/dri（金属料）"},
        {"dev": "loss_in_weight", "mount": "fuel", "label": "失重秤·电极", "measured": "电极消耗量", "feeds": "引擎输入 electrode（电极碳排源）"},
        # 注：智能电表·电弧炉 已去除——本工序可调设备 电极调节器 的测定值（电弧功率）即该物理量，避免数据冲突。
        {"dev": "gas_flowmeter", "mount": "gas", "label": "气体流量计·氧气/天然气", "measured": "吹氧/烧嘴燃气量", "feeds": "燃料类直接排放活动数据"},
        {"dev": "composition_analyzer", "mount": "control", "label": "成分分析仪·钢水", "measured": "钢水碳含量", "feeds": "精化固碳量与排放因子"},
    ],
    "hydrogen_bf": [
        {"dev": "belt_scale", "mount": "feed", "label": "皮带秤·炉料", "measured": "矿/球团入炉量", "feeds": "炉料总质量（矿量）"},
        {"dev": "loss_in_weight", "mount": "fuel", "label": "失重秤·补偿煤", "measured": "少量补偿煤粉量", "feeds": "引擎输入 coal_inj"},
        {"dev": "power_meter", "mount": "power", "label": "智能电表·电解制氢", "measured": "电解制氢电耗（大）", "feeds": "引擎输入 electricity（氢冶金主排放源）"},
        {"dev": "composition_analyzer", "mount": "control", "label": "成分分析仪·铁水", "measured": "铁水碳含量", "feeds": "精化固碳量"},
    ],
    "ladle_furnace": [
        {"dev": "weigher", "mount": "feed", "label": "钢水秤·钢水", "measured": "钢水周转量", "feeds": "引擎输入 steel_in"},
        # 注：智能电表·精炼 已去除——本工序可调设备 电极调节器 的测定值（电弧功率）即该物理量，避免数据冲突。
        {"dev": "composition_analyzer", "mount": "control", "label": "成分分析仪·合金", "measured": "合金化成分", "feeds": "精化排放因子"},
    ],
    "caster": [
        {"dev": "weigher", "mount": "product", "label": "铸坯秤", "measured": "连铸坯产量", "feeds": "引擎输入 steel_in / 钢产量"},
        {"dev": "power_meter", "mount": "power", "label": "智能电表·结晶/拉矫", "measured": "结晶/拉矫电耗", "feeds": "引擎输入 electricity"},
    ],
    "rolling_mill": [
        {"dev": "weigher", "mount": "feed", "label": "钢材秤·钢坯", "measured": "入轧钢坯量", "feeds": "引擎输入 steel_in（钢材产量）"},
        {"dev": "gas_flowmeter", "mount": "gas", "label": "气体流量计·加热炉煤气", "measured": "加热/退火炉燃气量", "feeds": "引擎输入 ng_rate（天然气直接排放）"},
        {"dev": "power_meter", "mount": "power", "label": "智能电表·轧制", "measured": "轧制主电机电耗", "feeds": "引擎输入 electricity（间接排放）"},
    ],
    "h2_dri": [
        {"dev": "belt_scale", "mount": "feed", "label": "皮带秤·球团/块矿", "measured": "入炉球团/块矿量", "feeds": "引擎输入 dri_out（竖炉处理量）"},
        {"dev": "gas_flowmeter", "mount": "gas", "label": "气体流量计·氢气", "measured": "还原气(H₂)量", "feeds": "引擎输入 h2_rate（氢耗，直接排放近零）"},
        {"dev": "power_meter", "mount": "power", "label": "智能电表·电解制氢", "measured": "电解制氢电耗", "feeds": "引擎输入 electricity（氢冶金主排放源）"},
    ],
    "dri_midrex": [
        {"dev": "belt_scale", "mount": "feed", "label": "皮带秤·球团/块矿", "measured": "入炉球团/块矿量", "feeds": "引擎输入 pellet_rate"},
        {"dev": "gas_flowmeter", "mount": "gas", "label": "气体流量计·天然气", "measured": "还原气(天然气)量", "feeds": "引擎输入 ng_rate（直接排放）"},
        {"dev": "power_meter", "mount": "power", "label": "智能电表·压球/压缩", "measured": "压球/压缩电耗", "feeds": "引擎输入 electricity"},
    ],
}


def _pv(params: Dict[str, float], key: str, default: float) -> float:
    v = params.get(key)
    return float(v) if v is not None else default


def compute_device_readings(unit: Any, params: Dict[str, float] = None) -> List[Dict[str, Any]]:
    """依据工序活动数据（params）生成该工序各内置设备的模拟读数。

    返回的每一项含：id, type, mount, label, measured, reading, unit, accuracy, feeds。
    reading 即为「设备采集到的活动数据」，是碳核算引擎的输入（自变量）。
    params 为已与 DEFAULT_PARAMS 合并后的完整参数（由引擎传入）；为空时回退到 unit.params。
    """
    t = unit.type if isinstance(unit, dict) else getattr(unit, "type", "")
    base = unit.params if isinstance(unit, dict) else getattr(unit, "params", {}) or {}
    params = dict(params) if params else {}
    params.update(base)  # unit.params 覆盖默认值（与碳引擎一致）
    specs = _UNIT_DEVICE_SPECS.get(t, [])
    out: List[Dict[str, Any]] = []

    for i, s in enumerate(specs):
        dev = s["dev"]
        meta = DEVICE_LIBRARY.get(dev, {})
        reading = 0.0
        unit_str = meta.get("unit", "")

        # 依据工序类型与设备挂载，由活动数据计算读数（与碳引擎保持一致）
        if t == "sinter_plant":
            ore = _pv(params, "ore_rate", 0.0)
            if s["mount"] == "feed":
                reading = ore
            elif s["mount"] == "fuel":
                reading = ore * _pv(params, "fuel_rate", 0.0) / 1000.0
            elif s["mount"] == "power":
                reading = _pv(params, "electricity", ore * 0.04)      # 40 kWh/t
        elif t == "pelletizing":
            ore = _pv(params, "ore_rate", 0.0)
            if s["mount"] == "feed":
                reading = ore
            elif s["mount"] == "fuel":
                reading = ore * _pv(params, "fuel_rate", 0.0) / 1000.0
            elif s["mount"] == "power":
                reading = _pv(params, "electricity", ore * 0.045)     # 45 kWh/t
        elif t == "coke_oven":
            coal = _pv(params, "coal_rate", 0.0)
            if s["mount"] == "feed":
                reading = coal
            elif s["mount"] == "gas":
                reading = coal * 340.0          # COG 约 340 m³/t 煤
            elif s["mount"] == "power":
                reading = _pv(params, "electricity", coal * 0.02)      # 20 kWh/t 煤
        elif t == "blast_furnace":
            hm = _pv(params, "hot_metal", 0.0)
            burden = hm * 1.6                   # 矿+焦+熔剂近似总炉料
            if s["mount"] == "feed":
                reading = burden
            elif s["mount"] == "fuel" and "焦炭" in s["label"]:
                reading = hm * _pv(params, "coke_rate", 0.0) / 1000.0
            elif s["mount"] == "fuel":
                reading = hm * _pv(params, "coal_inj", 0.0) / 1000.0
            elif s["mount"] == "flux":
                reading = hm * _pv(params, "flux", 0.0) / 1000.0
            elif s["mount"] == "product":
                reading = hm
            elif s["mount"] == "gas" and "高炉煤气" in s["label"]:
                reading = hm * 1600.0           # BFG 约 1600 m³/tHM
            elif s["mount"] == "power":
                reading = _pv(params, "electricity", hm * 0.03)
        elif t == "bof":
            steel = _pv(params, "steel_in", 0.0)
            if s["mount"] == "feed":
                reading = steel
            elif s["mount"] == "flux":
                reading = steel * _pv(params, "flux", 0.0) / 1000.0
            elif s["mount"] == "gas":
                reading = steel * 100.0         # LDG 约 100 m³/t 钢
            elif s["mount"] == "power":
                reading = _pv(params, "electricity", steel * 0.03)     # 30 kWh/t
        elif t == "eaf":
            scrap = _pv(params, "scrap", 0.0)
            dri = _pv(params, "dri", 0.0)
            steel = scrap + dri
            if s["mount"] == "feed":
                reading = steel
            elif s["mount"] == "fuel":
                reading = _pv(params, "electrode", steel * 0.002)      # 2 kg/t
            elif s["mount"] == "power":
                reading = _pv(params, "electricity", steel * 0.4)      # 400 kWh/t
            elif s["mount"] == "gas":
                reading = steel * 30.0          # 氧气/燃气近似
        elif t == "hydrogen_bf":
            hm = _pv(params, "hot_metal", 0.0)
            if s["mount"] == "feed":
                reading = hm * 1.6
            elif s["mount"] == "fuel":
                reading = hm * _pv(params, "coal_inj", 10.0) / 1000.0
            elif s["mount"] == "power":
                reading = _pv(params, "electricity", (_pv(params, "h2_rate", 90.0) * hm / 1000.0 * 55))  # 电解制氢
        elif t == "ladle_furnace":
            steel = _pv(params, "steel_in", 0.0)
            if s["mount"] == "feed":
                reading = steel
            elif s["mount"] == "power":
                reading = _pv(params, "electricity", steel * 0.03)
        elif t == "caster":
            steel = _pv(params, "steel_in", 0.0)
            if s["mount"] == "product":
                reading = steel
            elif s["mount"] == "power":
                reading = _pv(params, "electricity", steel * 0.015)    # 15 kWh/t
        elif t == "rolling_mill":
            steel = _pv(params, "steel_in", 0.0)
            if s["mount"] == "feed":
                reading = steel
            elif s["mount"] == "gas":
                reading = steel * _pv(params, "ng_rate", 0.0)          # m³/t → m³/h
            elif s["mount"] == "power":
                reading = _pv(params, "electricity", steel * 0.08)     # 80 kWh/t
        elif t == "h2_dri":
            dri = _pv(params, "dri_out", 0.0)
            if s["mount"] == "feed":
                reading = dri
            elif s["mount"] == "gas":
                reading = dri * _pv(params, "h2_rate", 0.0) / 1000.0
            elif s["mount"] == "power":
                reading = _pv(params, "electricity", _pv(params, "h2_rate", 90.0) * dri / 1000.0 * 55)  # 电解制氢
        elif t == "dri_midrex":
            pellet = _pv(params, "pellet_rate", 0.0)
            dri = _pv(params, "dri_out", pellet * 0.65)
            if s["mount"] == "feed":
                reading = pellet
            elif s["mount"] == "gas":
                reading = dri * _pv(params, "ng_rate", 0.0)          # m³/t-DRI → m³/h
            elif s["mount"] == "power":
                reading = _pv(params, "electricity", dri * 0.15)     # 150 kWh/t-DRI

        out.append({
            "id": f"{unit.id if isinstance(unit, dict) else getattr(unit, 'id', 'u')}::{dev}_{i}",
            "type": dev,
            "mount": s["mount"],
            "label": s["label"],
            "measured": s["measured"],
            "reading": round(reading, 2),
            "unit": unit_str,
            "accuracy": meta.get("accuracy", ""),
            "range": meta.get("range", ""),
            "feeds": s["feeds"],
            "color": meta.get("color", "#888888"),
            "icon": meta.get("icon", "🔧"),
        })
    return out


def library_payload() -> Dict[str, Any]:
    """供前端 /api/devices 使用的负载：设备库 + 各工序设备规格摘要 + 工序设备规格档位库。"""
    specs_summary = {
        ut: [
            {"dev": s["dev"], "mount": s["mount"], "label": s["label"],
             "measured": s["measured"], "feeds": s["feeds"]}
            for s in specs
        ]
        for ut, specs in _UNIT_DEVICE_SPECS.items()
    }
    return {"library": DEVICE_LIBRARY, "unit_specs": specs_summary, "process_specs": PROCESS_SPECS}
