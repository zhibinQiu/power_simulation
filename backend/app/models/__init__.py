"""数据模型定义：工序、物流、流程模型、策略、仿真结果。

所有前后端交互的数据契约都集中在这里，保证类型一致。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Unit(BaseModel):
    id: str
    type: str
    name: str
    x: float = 0.0
    z: float = 0.0
    rot: float = 0.0           # Y轴旋转角度（弧度），让进出口朝向更合理的方位
    enabled: bool = True
    params: Dict[str, float] = Field(default_factory=dict)
    techs: List[str] = Field(default_factory=list)  # 已应用的技术，如 ccs / waste_heat
    spec: str = ""                   # 设备规格 key（如 bf_1000 / bf_3200），空=平台默认规格


class Flow(BaseModel):
    id: str
    from_unit: str
    to_unit: str
    material: str = "hot_metal"      # hot_metal / scrap / steel / dri
    rate: float = 0.0                # t/h


class ProcessModel(BaseModel):
    units: List[Unit] = Field(default_factory=list)
    flows: List[Flow] = Field(default_factory=list)


# ---------------------- 自然语言策略解析结果 ----------------------

class ParsedOp(BaseModel):
    action: str                      # replace_type / set_param / add_unit / remove_unit / apply_tech
    target: Optional[str] = None     # 命中的工序名或类型
    to_type: Optional[str] = None
    param: Optional[str] = None
    value: Optional[float] = None
    mode: str = "absolute"           # absolute / relative(百分比)
    tech: Optional[str] = None
    count: int = 1
    note: str = ""                   # 给人看的自然语言描述


class ParseResult(BaseModel):
    raw_text: str
    understood: List[str] = Field(default_factory=list)   # 人可理解的要点
    ops: List[ParsedOp] = Field(default_factory=list)
    confidence: float = 0.0
    warnings: List[str] = Field(default_factory=list)
    engine: str = "heuristic"            # 解析引擎：llm / heuristic


# ---------------------- 仿真结果 ----------------------

class LedgerItem(BaseModel):
    """碳排放核算台账的一项：把"用了什么、因子多少、贡献多少CO2"讲清楚。"""
    item: str = ""                   # 项目名，如 焦炭 / 外购电力 / 碳捕集减排
    qty: float = 0.0                 # 用量
    qty_unit: str = ""               # 单位，如 t/h、MWh/h、kg/t
    basis: str = ""                  # 计算依据 / 排放因子说明
    formula: str = ""                # 完整计算展开式，如 "3360 t × 28.435 × 0.0295 × 3.667 = 10331 tCO₂/h"
    co2: float = 0.0                 # 该项 CO2 贡献，tCO2/h（减排项为负）
    scope: str = "direct"            # direct=范围一(直接) / indirect=范围二(间接)


class UnitResult(BaseModel):
    id: str
    type: str
    name: str
    co2_direct: float = 0.0          # tCO2/h (范围一)
    co2_indirect: float = 0.0        # tCO2/h (范围二，外购电)
    co2_total: float = 0.0
    carbon_in: float = 0.0           # tC/h 输入
    carbon_to_co2: float = 0.0       # tC/h 以 CO2 排出
    carbon_to_steel: float = 0.0     # tC/h 固结于钢
    carbon_to_slag: float = 0.0      # tC/h 进入高炉渣
    carbon_captured: float = 0.0     # tC/h 被捕集
    heat: float = 0.0                # 0~1，用于热力图着色
    # —— 能耗（节能减碳主题：先能后碳）——
    steel_output: float = 0.0        # t/h 该工序主产物产量（用于单位产品能耗）
    elec: float = 0.0                # MWh/h 电耗（外购电）
    fuel_energy: float = 0.0         # GJ/h 燃料能耗（燃料燃烧低位热值之和）
    energy_total: float = 0.0        # GJ/h 综合能耗（燃料+电折标，1 MWh=3.6 GJ）
    energy_intensity: float = 0.0    # kgce/t 单位产品综合能耗（综合能耗×34.12 / 主产物产量）
    carbon_by_fuel: Dict[str, float] = Field(default_factory=dict)
    breakdown: List[LedgerItem] = Field(default_factory=list)   # 核算明细台账
    notes: List[str] = Field(default_factory=list)              # 工艺/算法说明
    devices: List[Dict[str, Any]] = Field(default_factory=list) # 该工序内置监测设备及模拟读数（活动数据/自变量）


class SankeyNode(BaseModel):
    id: str
    label: str
    col: float                       # 列 0=外部源 1..=工序(按链深) 小数=中间产品 末列=去向
    kind: str                        # fuel / process / mid / sink


class SankeyLink(BaseModel):
    source: str
    target: str
    value: float                     # tC/h


class SimTotals(BaseModel):
    co2_direct: float
    co2_indirect: float
    co2_total: float
    carbon_in: float
    carbon_to_co2: float
    carbon_to_steel: float
    carbon_to_slag: float
    carbon_captured: float
    carbon_utilization: float       # 固碳/输入碳
    steel_output: float             # t/h
    intensity: float                 # kgCO2/t
    energy_total: float = 0.0       # GJ/h 全厂综合能耗
    energy_intensity: float = 0.0   # kgce/t 单位产品综合能耗
    elec: float = 0.0               # MWh/h 全厂外购电耗
    fuel_energy: float = 0.0        # GJ/h 全厂燃料能耗
    # 外购原燃料/动力量汇总（成本核算 = 用量 × 单价）：
    #   iron_ore/coke/coal/limestone/scrap/electrode/biomass 单位 t/h；electricity MWh/h；ngas m³/h
    #   coke 为「焦炭需求 − 焦炉自产」后的外购差额
    purchases: Dict[str, float] = Field(default_factory=dict)


class SimResult(BaseModel):
    totals: SimTotals
    units: List[UnitResult]
    sankey: Dict[str, Any] = Field(default_factory=dict)
    sankey_energy: Dict[str, Any] = Field(default_factory=dict)


# ---------------------- 策略 ----------------------

class Strategy(BaseModel):
    id: str
    name: str
    description: str = ""
    raw_text: str = ""
    ops: List[ParsedOp] = Field(default_factory=list)
    applied: bool = False
    created_at: str = ""


class ParseRequest(BaseModel):
    text: str
    model: Optional[ProcessModel] = None


class SimulateRequest(BaseModel):
    model: ProcessModel
    ops: List[ParsedOp] = Field(default_factory=list)   # 可选，应用策略后再仿真
    factors: Optional[Dict[str, Any]] = None            # 可选，覆盖默认排放因子（燃料 NCV/CC、电网因子、碳酸盐/电极因子）


class SimulateResponse(BaseModel):
    baseline: SimResult
    strategy: Optional[SimResult] = None
    delta: Optional[Dict[str, float]] = None            # 策略相对基线的变化
