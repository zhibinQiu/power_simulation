"""火电（thermal-power）场景资源包结构测试。

覆盖「包文件形态」资源包的完整性 —— 平台对非钢场景没有任何代码分支，
全部由 backend/data/scenes/thermal-power/*.json 驱动，因此包内容本身必须自洽：
  场景注册且就绪（/api/scenes 可见、openScene 可打开）
  资源齐备：model / templates / dictionary / factors / methods / param-schema / devices / strategies
  工序排放声明（emissions）与工序参数、排放因子三者键名一致（否则范围一恒为 0，静默出错）
  模板连线端口与节点端口一一对应（端口悬空会导致编排连线丢线）
  附加传感 / 可变设备类型必须是前端 attachLibrary 已注册类型（未注册类型详情面板无量程/单位）

运行：
  cd backend && python -m pytest tests/test_scene_thermal_power.py -v
"""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.scene import scene_loader, scene_registry  # noqa: E402

# backend/tests/test_scene_thermal_power.py → parents[1]=backend、parents[2]=仓库根
ROOT = Path(__file__).resolve().parents[2]
SCENE_DIR = ROOT / "backend" / "data" / "scenes" / "thermal-power"
ATTACH_LIB = ROOT / "frontend" / "src" / "data" / "attachLibrary.js"


def _read(name):
    return json.loads((SCENE_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def pack():
    return scene_loader.load_scene_package("thermal-power")


def _attach_types():
    """前端注册的附加设备类型：kind -> type 集合（包内只能用这些类型）。"""
    txt = ATTACH_LIB.read_text(encoding="utf-8")
    head, _, tail = txt.partition("export const ADJUSTABLE_TEMPLATES")
    sensor = set(re.findall(r"type:\s*'([a-z_0-9]+)'", head))
    adjustable = set(re.findall(r"type:\s*'([a-z_0-9]+)'", tail))
    return {"sensor": sensor, "adjustable": adjustable}


def test_scene_registered_and_ready(pack):
    """火电场景应出现在注册表且就绪（前端场景列表可打开）。"""
    ids = [s["id"] for s in scene_registry.list_scenes()]
    assert "thermal-power" in ids
    meta = scene_registry.get_scene("thermal-power")
    assert meta["ready"] is True
    assert meta["defaultRoute"] == "coal"
    assert meta["routes"] == ["coal", "chp"]
    assert pack and pack["ready"] is True and pack["note"] is None


def test_package_resources_complete(pack):
    """资源齐备：模型 / 模板 / 字典 / 因子 / 方法学 / 参数 / 设备 / 策略。"""
    res = pack["resources"] or {}
    for key in ("model", "templates", "dictionary", "factors", "methods",
                "paramSchema", "devices", "strategies"):
        assert key in res, f"资源缺失：{key}"
    assert len(res["templates"]) == 2
    assert {t["id"] for t in res["templates"]} == {"coal", "chp"}
    assert res["model"]["units"] and res["model"]["flows"]


def test_emissions_declared_match_params_and_factors(pack):
    """工序 emissions 声明的 param 必须是本工序参数、fuel/carbonate 必须在 factors 中有定义。"""
    dictionary = pack["resources"]["dictionary"]
    factors = pack["resources"]["factors"]
    procs = {p["type"]: p for p in dictionary["processes"]}
    declared = [(t, e) for t, p in procs.items() for e in (p.get("emissions") or [])]
    assert declared, "火电包至少要有一个直接排放源（锅炉燃煤）"
    for ptype, e in declared:
        p = procs[ptype]
        keys = {x["key"] for x in (p.get("params") or [])}
        assert e["param"] in keys, f"{ptype}: 排放参数 {e['param']} 不在工序参数内"
        if e["kind"] == "fuel":
            assert e["fuel"] in (factors.get("fuels") or {}), f"{ptype}: 燃料 {e['fuel']} 无排放因子"
        elif e["kind"] == "carbonate":
            assert e["carbonate"] in (factors.get("carbonate") or {}), f"{ptype}: 碳酸盐 {e['carbonate']} 无排放因子"
        else:
            pytest.fail(f"未知排放类型：{e['kind']}")
    # 锅炉燃煤是范围一主源、脱硫是过程排放源
    assert any(e["kind"] == "fuel" and t == "boiler" for t, e in declared)
    assert any(e["kind"] == "carbonate" and t == "desulfurization" for t, e in declared)


def test_fuel_factor_shape(pack):
    """燃料因子字段齐备（ncv/cc/ox），缺 ox 时按 1 计算会低估排放。"""
    fuels = pack["resources"]["factors"]["fuels"]
    for key, f in fuels.items():
        assert f.get("ncv") and f.get("cc"), f"燃料 {key} 缺低位发热量/含碳量"
        assert 0 < float(f.get("ox", 1)) <= 1, f"燃料 {key} 碳氧化率非法"
    coal = fuels["coal"]
    # 发电用原煤典型值：NCV≈20.9 GJ/t、CC≈0.0262 tC/GJ → 约 2.0 tCO₂/t
    ef = float(coal["ncv"]) * float(coal["cc"]) * float(coal["ox"]) * 44 / 12
    assert 1.5 < ef < 2.5, f"原煤排放因子量级异常：{ef}"


def test_template_ports_and_connections_consistent(pack):
    """模板连线必须挂在真实端口上，且介质与端口物料一致。"""
    for tpl in pack["resources"]["templates"]:
        scheme = tpl["scheme"]
        nodes = {n["id"]: n for n in scheme["nodes"]}
        for c in scheme["connections"]:
            src = nodes.get(c["from"])
            dst = nodes.get(c["to"])
            assert src and dst, f"{tpl['id']}: 连线端点不存在 {c['id']}"
            out_port = next((p for p in src["ports"]["out"] if p["id"] == c["fromPort"]), None)
            in_port = next((p for p in dst["ports"]["in"] if p["id"] == c["toPort"]), None)
            assert out_port, f"{tpl['id']}: 源端口缺失 {c['fromPort']}"
            assert in_port, f"{tpl['id']}: 目标端口缺失 {c['toPort']}"
            assert c["material"] == out_port["material"] == in_port["material"], \
                f"{tpl['id']}: 连线介质与端口物料不一致 {c['id']}"
        # 每个工序参数都能在字典里找到定义（属性面板靠字典渲染）
        types = {p["type"] for p in pack["resources"]["dictionary"]["processes"]}
        for n in scheme["nodes"]:
            assert n["type"] in types, f"{tpl['id']}: 工序 {n['type']} 未在字典声明"


def test_attached_types_registered_in_frontend(pack):
    """包内附加设备类型必须是前端 attachLibrary 已注册类型（否则无单位/量程/默认读数）。"""
    if not ATTACH_LIB.exists():
        pytest.skip("前端附加设备库缺失")
    reg = _attach_types()
    seen = 0
    for tpl in pack["resources"]["templates"]:
        for n in tpl["scheme"]["nodes"]:
            for a in (n.get("attached") or []):
                assert a["kind"] in reg, f"未注册的附加设备类别：{a['kind']}"
                assert a["type"] in reg[a["kind"]], f"未注册的附加设备类型：{a['type']}"
                if a.get("src") == "attach":
                    # 联动型传感器必须指向同工序的可调设备，且给出量程锚点
                    refs = {x["uid"] for x in (n.get("attached") or []) if x["kind"] == "adjustable"}
                    assert a.get("devRef") in refs, f"{a['uid']}: 联动源 devRef 无效"
                    assert a.get("scale") and a["scale"].get("from"), f"{a['uid']}: 联动锚点缺失"
                seen += 1
    assert seen >= 10, "附加设备数量过少，模板未体现监测/可调能力"


def test_direct_emission_magnitude(pack):
    """按包内因子核算 660MW 机组：锅炉燃煤排放应落在 400~520 tCO₂/h（约 0.7 tCO₂/MWh）。"""
    dictionary = pack["resources"]["dictionary"]
    factors = pack["resources"]["factors"]
    tpl = next(t for t in pack["resources"]["templates"] if t["id"] == "coal")
    boiler = next(n for n in tpl["scheme"]["nodes"] if n["type"] == "boiler")
    proc = next(p for p in dictionary["processes"] if p["type"] == "boiler")
    e = next(x for x in proc["emissions"] if x["kind"] == "fuel")
    f = factors["fuels"][e["fuel"]]
    ef = float(f["ncv"]) * float(f["cc"]) * float(f["ox"]) * 44 / 12
    co2 = float(boiler["params"][e["param"]]) * ef
    assert 400 < co2 < 520, f"锅炉燃煤排放数量级异常：{co2} tCO₂/h"
    # 发电侧单位排放强度（发电煤耗口径）应在 0.6~0.85 tCO₂/MWh
    gen = next(n for n in tpl["scheme"]["nodes"] if n["type"] == "generator")
    out = float(gen["params"]["output"])
    assert 0.6 < co2 / out < 0.85, f"单位发电排放强度异常：{co2 / out} tCO₂/MWh"
