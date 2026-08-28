"""参数优化「优化目标」扩展测试：全流程指标 + 每工艺实时指标。

覆盖：
  - _objective_options：全流程五项 + 每个工艺的实时碳排放/能耗/电耗
  - _objective_unit：逐工艺目标键的单位解析
  - GA 优化器 state() 暴露动态 objectives
  - set_settings 接受/拒绝逐工艺目标键

运行：
  cd backend && python -m pytest tests/test_objectives.py -v
（纯算法单测：不依赖真实网络 / Broker）
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import ProcessModel, Unit  # noqa: E402
from app.optimizers import (  # noqa: E402
    UNIT_METRIC_OPTIONS,
    _objective_options,
    _objective_unit,
    get_optimizer,
)

# 含两个工艺的最小流程模型
_MODEL = ProcessModel(
    units=[
        Unit(id="bf1", type="blast_furnace", name="高炉",
             params={"wind_rate": 500.0, "hot_blast_temp": 1100.0, "oxygen_enrich": 3.0}),
        Unit(id="bof1", type="bof", name="转炉",
             params={"scrap_ratio": 0.12}),
    ],
    flows=[],
)


def test_objective_options_include_whole_and_per_unit():
    opts = _objective_options(_MODEL)
    keys = [o["key"] for o in opts]
    # 全流程五项：碳强度 / 吨钢能耗 / 碳排总量 / 综合能耗 / 电耗
    for k in ("intensity", "energy_intensity", "co2_total", "energy_total", "elec"):
        assert k in keys
    # 每个工艺三项：实时碳排放 / 实时能耗 / 实时电耗
    for uid in ("bf1", "bof1"):
        for m in UNIT_METRIC_OPTIONS:
            assert f"unit:{uid}:{m['key']}" in keys
    by_key = {o["key"]: o for o in opts}
    assert by_key["unit:bf1:co2_total"]["label"] == "高炉·实时碳排放"
    assert by_key["unit:bf1:co2_total"]["unit"] == "t/h"
    assert by_key["unit:bf1:co2_total"]["group"] == "工艺实时指标"
    assert by_key["unit:bof1:elec"]["unit"] == "MWh/h"
    # 禁用工艺不参与
    from app.models import ProcessModel as _PM, Unit as _U
    m2 = _PM(units=[_U(id="off1", type="eaf", name="关停电炉", enabled=False)], flows=[])
    keys2 = [o["key"] for o in _objective_options(m2)]
    assert "unit:off1:co2_total" not in keys2


def test_objective_unit_for_unit_keys():
    assert _objective_unit("unit:bf1:co2_total") == "t/h"
    assert _objective_unit("unit:bf1:energy_total") == "GJ/h"
    assert _objective_unit("unit:bf1:elec") == "MWh/h"
    assert _objective_unit("unit:x:weird") == "kgCO₂/t"
    assert _objective_unit("intensity") == "kgCO₂/t"
    assert _objective_unit("energy_total") == "GJ/h"


def test_optimizer_state_exposes_objectives():
    o = get_optimizer("ai::ga")
    o.setup(_MODEL, {})
    st = o.state()
    keys = [x["key"] for x in st["objectives"]]
    assert "unit:bf1:co2_total" in keys
    assert "unit:bof1:energy_total" in keys
    assert "energy_total" in keys
    assert "elec" in keys


def test_set_settings_accepts_unit_objective():
    o = get_optimizer("ai::ga")
    o.setup(_MODEL, {})
    o.set_settings({"objective": "unit:bof1:energy_total"})
    assert o.objective == "unit:bof1:energy_total"
    # 非法 key 忽略，保持当前目标
    o.set_settings({"objective": "nope"})
    assert o.objective == "unit:bof1:energy_total"
    # 切回全流程指标
    o.set_settings({"objective": "elec"})
    assert o.objective == "elec"
