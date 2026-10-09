"""火电（thermal-power）场景的碳排核算回归测试。

核算口径：GB/T 32151.1《温室气体排放核算与报告要求 第 1 部分：发电企业》
  ① 范围一（燃料燃烧）= 入炉煤量 × 低位发热量 × 单位热值含碳量 × 碳氧化率 × 44/12
  ② 范围一（工业过程）= 脱硫剂耗量 × CaCO₃ 含量 × 碳酸盐分解因子
  ③ 范围二（间接）    = 各系统厂用电(MWh/h) × 电网排放因子

本组用例锁住三件事：
  1. 火电 14 类工序（12 个既有 + 除灰渣/石膏脱水 2 个固废副产品节点）全部注册计算器；
  2. 碳氧化率与脱硫剂纯度这两个"场景扩展因子"真正生效（否则排放会系统性偏高）；
  3. 全厂守恒闭合（未燃尽碳作为固废碳离开系统，不重复计入排放）。
"""
import json
import os

import pytest

from app.models import ProcessModel
from app.domain.sim.calculators import RULES
from app.domain.sim.carbon_engine import simulate, conservation_audit

BASE = os.path.join(os.path.dirname(__file__), "..", "app", "..", "data", "scenes", "thermal-power")

# 火电资源包的全部工序类型（与 dictionary.json / templates.json 一致）
TP_TYPES = [
    "coal_handling", "boiler", "steam_turbine", "generator",
    "condenser", "cooling_tower", "feedwater",
    "denitration", "dedust", "desulfurization", "stack",
    "ash_handling", "gypsum_handling", "heat_net",
]


def _load():
    with open(os.path.join(BASE, "model.json"), encoding="utf-8") as f:
        m = ProcessModel(**json.load(f))
    with open(os.path.join(BASE, "factors.json"), encoding="utf-8") as f:
        fac = json.load(f)
    return m, fac


def test_all_thermal_power_types_registered():
    """火电 14 类工序必须全部注册计算器，否则 simulate 会静默跳过（排放恒为 0）。"""
    missing = [t for t in TP_TYPES if t not in RULES]
    assert missing == []


def test_model_units_all_covered():
    """场景默认模型里的每个工序都要能算（含新增的除灰渣、石膏脱水节点）。"""
    m, _fac = _load()
    missing = [u.type for u in m.units if u.type not in RULES]
    assert missing == []


def test_boiler_applies_carbon_oxidation_factor():
    """锅炉必须乘碳氧化率(OF=0.98)：255 × 20.9 × 0.0262 × 0.98 × 3.667 ≈ 501.7 tCO₂/h。"""
    m, fac = _load()
    res = simulate(m, fac)
    boiler = next(u for u in res.units if u.type == "boiler")
    coal, ncv, cc, ox = 255.0, 20.9, 0.0262, 0.98
    expect = coal * ncv * cc * ox * 44.0 / 12.0
    assert boiler.co2_direct == pytest.approx(expect, abs=0.05)
    # 未乘氧化率时约 512 tCO₂/h，必须明显低于该值，证明 OF 已生效
    assert boiler.co2_direct < coal * ncv * cc * 44.0 / 12.0 - 5.0


def test_desulfurization_applies_scene_carbonate_purity():
    """脱硫过程排放按场景 carbonate_purity(=0.9)：8 × 0.9 × 0.4395 ≈ 3.17 tCO₂/h。"""
    m, fac = _load()
    res = simulate(m, fac)
    ds = next(u for u in res.units if u.type == "desulfurization")
    purity = float(fac.get("carbonate_purity", 0.9))
    expect = 8.0 * purity * fac["carbonate"]["limestone"]
    assert ds.co2_direct == pytest.approx(expect, abs=0.05)


def test_intensity_is_per_kwh_basis():
    """火电的产量口径是发电量(MW)，故强度 = 直接排放 ÷ 发电量 × 1000 即度电碳排 g/kWh。"""
    m, fac = _load()
    res = simulate(m, fac)
    t = res.totals
    assert t.steel_output == pytest.approx(660.0)
    assert t.intensity == pytest.approx(t.co2_direct / 660.0 * 1000.0, abs=0.1)
    assert 700.0 < t.intensity < 850.0      # 当前煤电度电碳排的典型区间


def test_conservation_closed_and_unburned_carbon_to_solid_waste():
    """未燃尽碳随灰渣排出（carbon_to_product），碳守恒闭合误差应为 0。"""
    m, fac = _load()
    res = simulate(m, fac)
    boiler = next(u for u in res.units if u.type == "boiler")
    ox = 0.98
    assert boiler.carbon_to_product == pytest.approx(boiler.carbon_in * (1 - ox), abs=0.01)
    a = conservation_audit(m, fac)
    assert abs(a["totals"]["closure_error"]) < 1e-6


def test_aux_only_units_emit_indirect_only():
    """除灰渣/石膏脱水/汽轮机等无燃烧工序：直接排放为 0，只有厂用电对应的范围二。"""
    m, fac = _load()
    res = simulate(m, fac)
    for t in ("ash_handling", "gypsum_handling", "steam_turbine", "condenser", "dedust", "stack"):
        u = next(x for x in res.units if x.type == t)
        assert u.co2_direct == 0.0
        assert u.co2_indirect > 0.0
