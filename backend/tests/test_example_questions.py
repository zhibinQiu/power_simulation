"""「本析智擎」示例问题数据链路测试（backend）。

覆盖四个典型问询所需的技能链路：
1. 「当前的设备都运转正常吗」→ query_realtime_devices 设备健康状态
2. 「今年以来工厂一共排放了多少碳，消耗了多少能源」→ summarize_plant_emissions 累计统计
3. 「给出各个工艺碳排放的实时占比」→ run_simulation 工序级 CO2 与占比
4. 「高炉节能减碳的措施有哪些」→ query_knowledge 知识库检索（含拆词回退）

运行：
  cd backend && python -m pytest tests/test_example_questions.py -v
"""
import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.skills.registry import get_registry  # noqa: E402

REGISTRY = None


def _registry():
    global REGISTRY
    if REGISTRY is None:
        REGISTRY = get_registry()
    return REGISTRY


def _exec(name: str, args: dict) -> dict:
    return json.loads(asyncio.run(_registry().execute(name, args)))


def _skill_ok(name: str) -> bool:
    s = _registry().get(name)
    return s is not None and s.enabled


def _agent_skills(aid: str) -> list:
    """直接读 data/agents.json 获取智能体白名单（避免触发 langgraph 依赖）。"""
    p = Path(__file__).resolve().parent.parent / "data" / "agents.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    for a in data.get("agents", data if isinstance(data, list) else []):
        if a.get("id") == aid:
            return a.get("available_skills")
    return None


# ---------------------------------------------------------------------------
# 问题 1：当前的设备都运转正常吗
# ---------------------------------------------------------------------------
def test_q1_device_health_status_fields():
    """设备查询返回每台设备健康状态与汇总统计。"""
    out = _exec("query_realtime_devices", {})
    assert "summary" in out and "devices" in out
    summary = out["summary"]
    st = summary["device_status"]
    assert st["total"] > 0
    assert st["total"] == st["ok"] + st["abnormal"] + st["no_data"]
    assert st["ok"] == 0                       # 测试环境 MQTT 未关联 → 全部无数据
    assert st["no_data"] == st["total"]
    for d in out["devices"]:
        assert d["status"] in ("ok", "abnormal", "no_data")


def test_q1_device_health_status_classification(monkeypatch):
    """健康判定：无数据 / 超量程 / 正常 三类正确区分。"""
    import app.mqtt_source as mqtt_source

    calls = {"n": 0}

    def fake_reading(did: str):
        calls["n"] += 1
        if "::belt_scale_0" in did:            # 皮带秤 6000 t/h 量程 → 超量程
            return 99999.0
        if "::power_meter_0" in did:           # 电表正常
            return 50.0
        return None                            # 其余无数据

    monkeypatch.setattr(mqtt_source, "resolve_reading", fake_reading)
    out = _exec("query_realtime_devices", {})
    st = out["summary"]["device_status"]
    assert st["abnormal"] >= 1
    assert st["ok"] >= 1
    assert st["no_data"] >= 1
    statuses = {d["id"]: d["status"] for d in out["devices"]}
    abnormal = [k for k, v in statuses.items() if v == "abnormal"]
    assert any("belt_scale" in k for k in abnormal)


def test_q1_skill_available_to_agents():
    """设备技能对通用助手与设备专家可用。"""
    for aid in ("general", "device_expert", "data_analyst"):
        allow = _agent_skills(aid)
        if allow is not None:
            assert "query_realtime_devices" in allow
    assert _skill_ok("query_realtime_devices")


# ---------------------------------------------------------------------------
# 问题 2：今年以来工厂一共排放了多少碳，消耗了多少能源
# ---------------------------------------------------------------------------
def test_q2_ytd_emissions_math():
    """累计排放/能耗 = 仿真瞬时速率 × 运行时长，且含估算口径说明。"""
    out = _exec("summarize_plant_emissions", {"hours": 100})
    assert out["ok"] is True
    assert out["hours"] == 100
    assert out["hours_note"] == "入参运行时长（小时）"
    rates = out["rates_per_hour"]
    ytd = out["ytd"]
    assert ytd["co2_total_t"] == round(rates["co2_t"] * 100, 0)
    assert ytd["energy_total_gj"] == round(rates["energy_gj"] * 100, 0)
    assert ytd["energy_total_tce"] == round(ytd["energy_total_gj"] * 34.12 / 1000.0, 0)
    assert ytd["steel_total_t"] == round(rates["steel_t"] * 100, 0)
    note = out["calculation_note"]
    assert note["summary"] and note["steps"] and note["assumptions"]
    assert any("估算" in a for a in note["assumptions"])


def test_q2_ytd_default_hours():
    """缺省运行时长按今年已过天数 × 24h × 负荷率估算。"""
    from datetime import datetime

    out = _exec("summarize_plant_emissions", {})
    days = datetime.now().timetuple().tm_yday
    expect = days * 24.0 * 0.85
    assert out["hours"] == round(expect, 1)
    assert "今年已过天数" in out["hours_note"]


def test_q2_skill_registered():
    assert _skill_ok("summarize_plant_emissions")
    s = _registry().get("summarize_plant_emissions")
    assert "统计" in s.description


# ---------------------------------------------------------------------------
# 问题 3：给出各个工艺碳排放的实时占比
# ---------------------------------------------------------------------------
def test_q3_process_carbon_shares():
    """仿真结果按工序给出 CO2 与占比，占比合计约 100%。"""
    out = _exec("run_simulation", {})
    assert "summary" in out and "units" in out
    shares = out["summary"]["process_shares"]
    assert len(shares) >= 3
    total_pct = round(sum(s["share_pct"] for s in shares), 1)
    assert 99.0 <= total_pct <= 101.0
    total_t = sum(s["co2_total_t"] for s in shares)
    assert abs(total_t - out["summary"]["total_co2_t"]) < 1.0
    # 长流程中高炉通常是最大排放源
    bf = max(shares, key=lambda s: s["share_pct"])
    assert bf["share_pct"] > 50.0
    # units 中也带同名字段
    units = {u["name"]: u for u in out["units"]}
    assert "co2_total_t" in units[bf["name"]]


def test_q3_skill_available_to_agents():
    for aid in ("general", "carbon_advisor", "data_analyst"):
        allow = _agent_skills(aid)
        if allow is not None:
            assert "run_simulation" in allow


# ---------------------------------------------------------------------------
# 问题 4：高炉节能减碳的措施有哪些
# ---------------------------------------------------------------------------
def test_q4_blast_furnace_abatement_knowledge_doc_exists():
    """知识库已存在「高炉节能减碳措施」文档。"""
    from app.services import knowledge_service as kb

    tree = kb.list_tree()
    found = False

    def walk(node):
        nonlocal found
        if found:
            return
        for doc in node.get("docs", []):
            if doc.get("title") == "高炉节能减碳措施":
                found = True
                return
        for child in node.get("children", []):
            walk(child)

    walk(tree.get("tree", {}))
    assert found, "知识库缺少「高炉节能减碳措施」文档"


def test_q4_blast_furnace_abatement_search():
    """用整句提问也能命中（拆词回退检索）。"""
    out = _exec("query_knowledge", {"query": "高炉节能减碳的措施有哪些"})
    assert out["ok"] is True
    assert out["count"] >= 1
    titles = [r["title"] for r in out["results"]]
    assert "高炉节能减碳措施" in titles


def test_q4_knowledge_skill_available_to_agents():
    """知识库技能进入减排/合规顾问白名单。"""
    for aid in ("carbon_advisor", "compliance_advisor"):
        allow = _agent_skills(aid) or []
        assert "query_knowledge" in allow, f"{aid} 白名单缺 query_knowledge"
        assert "summarize_plant_emissions" in allow, f"{aid} 白名单缺 summarize_plant_emissions"
    assert _skill_ok("query_knowledge")


def test_q4_knowledge_fallback_split_terms():
    """拆词回退：仅命中单个词时也能返回结果。"""
    out = _exec("query_knowledge", {"query": "富氧鼓风 提高 热风温度 措施"})
    assert out["count"] >= 1
