"""默认流程模型与工序工厂。

提供一个典型"长流程"钢厂作为基线（烧结->高炉->转炉->精炼->连铸->轧机），
并提供 default_unit() 供自然语言"新增工序"时生成带合理默认参数的单元。
"""
from __future__ import annotations

from typing import Optional

from .carbon_engine import UNIT_META
from .models import ProcessModel, Unit, Flow


def _u(uid: str, utype: str, name: str, x: float, z: float = 0.0, rot: float = 0.0, params: Optional[dict] = None, techs=None) -> Unit:
    return Unit(id=uid, type=utype, name=name, x=x, z=z, rot=rot, params=params or {}, techs=techs or [])


def default_model() -> ProcessModel:
    units = [
        _u("s1", "sinter_plant", "烧结机", -34),
        _u("bf1", "blast_furnace", "高炉", -20),
        _u("bof1", "bof", "转炉", -4),
        _u("lf1", "ladle_furnace", "精炼炉", 10),
        _u("cc1", "caster", "连铸机", 22),
        _u("rm1", "rolling_mill", "热轧机", 34),
    ]
    flows = [
        Flow(id="f0", from_unit="s1", to_unit="bf1", material="sinter", rate=1100),
        Flow(id="f1", from_unit="bf1", to_unit="bof1", material="hot_metal", rate=1000),
        Flow(id="f2", from_unit="bof1", to_unit="lf1", material="steel", rate=1000),
        Flow(id="f3", from_unit="lf1", to_unit="cc1", material="steel", rate=1000),
        Flow(id="f4", from_unit="cc1", to_unit="rm1", material="steel", rate=1000),
    ]
    return ProcessModel(units=units, flows=flows)


# 新增工序时的布局：按序号在 x 轴排布；命名规则：单台直接用工艺名（如 高炉），
# 同类型出现多台时按 高炉、高炉2、高炉3 … 顺序命名
def default_unit(utype: str, index: int, same_count: int = 0) -> Unit:
    label = UNIT_META.get(utype, {}).get("label", utype)
    x = -40 + index * 8.0
    seq = same_count + 1
    name = label if same_count == 0 else f"{label}{seq}"
    return Unit(id=f"{utype[:3]}{seq}", type=utype, name=name, x=x, z=0.0)


def preset_strategies() -> list:
    """内置几条示例策略，方便用户一键体验。"""
    return [
        {"name": "氢冶金替代高炉", "text": "将 高炉 改为 氢冶金，并应用 碳捕集"},
        {"name": "绿氢竖炉替代", "text": "新增 一座 氢基直接还原，并 删除 高炉"},
        {"name": "电炉短流程", "text": "新增 一座 电炉，并 删除 高炉"},
        {"name": "焦比优化", "text": "高炉 的 焦比 降到 360，喷煤 提高 15%"},
        {"name": "余热+碳捕集", "text": "应用 余热回收，应用 碳捕集"},
        {"name": "熔融还原路线", "text": "新增 一座 熔融还原，并 删除 高炉"},
    ]
