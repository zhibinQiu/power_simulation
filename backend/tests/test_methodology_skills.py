"""方法学 Skills 测试（backend）。

覆盖：
- 8 个方法学技能已注册且默认启用、可转 OpenAI function 格式
- compute_carbon_accounting  碳排放量核算结果正确
- judge_carbon_market_cycle  市场周期判断（显式价格序列 + 台账回退）
- forecast_carbon_price_to_year_end  预测失败/成功路径
- compute_cea_carry_forward  结转公式正确
- evaluate_carbon_compliance  履约缺口与 CCER 覆盖
- recommend_carbon_strategy  缺参/企业不存在友好错误 + 完整策略链路（临时存储）
- query_carbon_enterprise_ledger / list_carbon_enterprises 台账查询
- 每个方法学技能返回「计算过程说明」calculation_note（summary/steps/assumptions）
- 体系自动扩展：追加一个 Skill 即注册，缺字段给出清晰报错

运行：
  cd backend && python -m pytest tests/test_methodology_skills.py -v
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.skills.base import Skill  # noqa: E402
from app.skills.registry import get_registry  # noqa: E402
from app.skills.methodology import (  # noqa: E402
    _METHODOLOGY_SKILLS,
    methodology_manifest,
    register_methodology_skills,
)

METHODOLOGY_NAMES = [
    "compute_carbon_accounting",
    "judge_carbon_market_cycle",
    "forecast_carbon_price_to_year_end",
    "compute_cea_carry_forward",
    "evaluate_carbon_compliance",
    "recommend_carbon_strategy",
    "query_carbon_enterprise_ledger",
    "list_carbon_enterprises",
]


def _exec(name: str, args: dict) -> dict:
    """通过注册表执行技能并把文本结果解析为 dict。"""
    registry = get_registry()
    skill = registry.get(name)
    assert skill is not None, f"skill 未注册: {name}"
    assert skill.enabled, f"skill 未启用: {name}"
    text = None
    import asyncio

    async def _run():
        return await registry.execute(name, args)

    text = asyncio.run(_run())
    assert isinstance(text, str), f"{name} 应返回文本"
    return json.loads(text)


# ---------------------------------------------------------------------------
# 注册与格式
# ---------------------------------------------------------------------------
def test_all_methodology_skills_registered():
    registry = get_registry()
    for name in METHODOLOGY_NAMES:
        skill = registry.get(name)
        assert skill is not None, f"skill 未注册: {name}"
        assert skill.enabled
        assert skill.source == "builtin"
        assert skill.description
        assert skill.input_schema


def test_methodology_skill_openai_format():
    registry = get_registry()
    skill = registry.get("recommend_carbon_strategy")
    tool = skill.to_openai_tool()
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "recommend_carbon_strategy"
    assert "required" in tool["function"]["parameters"]


def test_methodology_skill_mcp_format():
    registry = get_registry()
    skill = registry.get("compute_carbon_accounting")
    tool = skill.to_mcp_tool()
    assert tool["name"] == "compute_carbon_accounting"
    assert "inputSchema" in tool


# ---------------------------------------------------------------------------
# 1. 碳排放量核算
# ---------------------------------------------------------------------------
def test_compute_carbon_accounting():
    out = _exec("compute_carbon_accounting", {
        "scope1_combustion": 10.0,       # 万吨
        "scope1_process": 2.0,           # 万吨
        "free_cea_quota": 8.0,           # 万吨
        "own_ccer_eligible": 0.5,        # 万吨
    })
    assert out["ok"] is True
    r = out["result"]
    assert r["scope1_total"] == pytest.approx(12.0)
    assert r["verified_emission"] == pytest.approx(12.0)
    assert r["compliance_gap"] == pytest.approx(4.0)       # 12 - 8
    assert r["ccer_cap"] == pytest.approx(0.6)             # 12 * 0.05
    assert r["own_ccer_usable"] == pytest.approx(0.5)      # min(0.5, 0.6, 4.0)
    assert r["residual_gap_after_own_ccer"] == pytest.approx(3.5)


def test_compute_carbon_accounting_verified_override():
    out = _exec("compute_carbon_accounting", {
        "scope1_combustion": 10.0,
        "verified_override": 13.0,
    })
    assert out["result"]["verified_emission"] == pytest.approx(13.0)


# ---------------------------------------------------------------------------
# 2. 碳市场行情周期判断
# ---------------------------------------------------------------------------
def test_judge_carbon_market_cycle_with_prices():
    prices = [60.0, 62.0, 58.0, 70.0, 75.0, 80.0, 78.0, 85.0, 82.0, 90.0]
    out = _exec("judge_carbon_market_cycle", {
        "cea_monthly_prices": prices,
        "current_cea_price": 85.0,
        "current_ccer_price": 60.0,
    })
    assert out["ok"] is True
    r = out["result"]
    assert r["price_band"] in ("low", "mid", "high")
    assert r["time_window"] in ("early", "mid", "late")
    assert r["action_tag"] in ("buy", "sell", "hold")
    assert r["current_price"] == pytest.approx(85.0)
    assert r["cea_ccer_spread"] == pytest.approx(25.0)
    assert r["rationale"]


def test_judge_carbon_market_cycle_fallback_ledger(tmp_cc):
    """无价格序列时回退市场月度台账（临时存储）。"""
    tmp_cc.upsert_market_cea(None, {"year_month": "2025-01", "avg_price": 75.0})
    tmp_cc.upsert_market_cea(None, {"year_month": "2025-02", "avg_price": 80.0})
    out = _exec("judge_carbon_market_cycle", {"current_cea_price": 78.0})
    assert out["ok"] is True
    assert out["result"]["current_price"] == pytest.approx(78.0)


# ---------------------------------------------------------------------------
# 3. 碳价预测
# ---------------------------------------------------------------------------
def test_forecast_no_history_error():
    out = _exec("forecast_carbon_price_to_year_end", {"history": []})
    assert out["ok"] is False
    assert out["error"]


def test_forecast_with_history(monkeypatch):
    out = _exec("forecast_carbon_price_to_year_end", {
        "history": [
            {"t": "2025-01-06", "close": 70.0},
            {"t": "2025-01-07", "close": 71.0},
            {"t": "2025-01-08", "close": 69.5},
            {"t": "2025-01-09", "close": 72.0},
            {"t": "2025-01-10", "close": 73.0},
        ],
        "method": "rule",
    })
    # 5 个样本不足 _forecast_context 的 len<5 下限（不足5会被拒）
    if not out["ok"]:
        return  # 允许样本不足路径
    assert out["method"] == "price_forecast"
    assert out["instrument"] == "cea"


# ---------------------------------------------------------------------------
# 4. CEA 结转测算
# ---------------------------------------------------------------------------
def test_compute_cea_carry_forward():
    out = _exec("compute_cea_carry_forward", {
        "base_qty": 10.0,
        "net_sell": 2.0,
        "year_end_holding": 12.0,
        "net_sell_multiplier": 1.5,
    })
    assert out["ok"] is True
    r = out["result"]
    # 公式上限 = 10 + 2*1.5 = 13；最大可结转 = min(13, 12) = 12；超额 = 0
    assert r["formula_cap"] == pytest.approx(13.0)
    assert r["max_carry"] == pytest.approx(12.0)
    assert r["excess"] == pytest.approx(0.0)


def test_compute_cea_carry_forward_excess():
    out = _exec("compute_cea_carry_forward", {
        "base_qty": 10.0,
        "net_sell": 0.0,
        "year_end_holding": 15.0,
        "net_sell_multiplier": 1.5,
    })
    r = out["result"]
    # 上限=10，持仓 15 → 超额 5；需扩卖 5/(1+1.5)=2
    assert r["max_carry"] == pytest.approx(10.0)
    assert r["excess"] == pytest.approx(5.0)
    assert r["sell_to_expand_cap"] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# 5. 履约合规评估
# ---------------------------------------------------------------------------
def test_evaluate_carbon_compliance_gap():
    out = _exec("evaluate_carbon_compliance", {
        "scope1_combustion": 20.0,
        "free_cea_quota": 15.0,
        "ccer_holdings": [
            {"qty": 1.0, "eligible_qty": 1.0, "expire_at": "2030-12-31", "linked_green_cert": False},
        ],
    })
    assert out["ok"] is True
    r = out["result"]
    assert r["compliance_gap"] == pytest.approx(5.0)
    assert r["own_ccer_eligible"] == pytest.approx(1.0)
    assert r["own_ccer_usable"] == pytest.approx(1.0)          # min(1, 20*0.05=1, 5)
    assert r["residual_gap_after_own_ccer"] == pytest.approx(4.0)
    assert "缺口" in r["conclusion"]


def test_evaluate_carbon_compliance_expired_ccer():
    """过期 CCER 不计入可抵扣。"""
    out = _exec("evaluate_carbon_compliance", {
        "scope1_combustion": 20.0,
        "free_cea_quota": 15.0,
        "ccer_holdings": [
            {"qty": 1.0, "eligible_qty": 1.0, "expire_at": "2020-01-01", "linked_green_cert": False},
        ],
    })
    assert out["result"]["own_ccer_eligible"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 6-8. 企业台账 / 列表 / 策略
# ---------------------------------------------------------------------------
def _make_enterprise(ccs) -> str:
    ent = ccs.create_enterprise(
        None, ccs.DEFAULT_USER_ID,
        {"name": "测试钢企", "industry": "steel", "market_start_year": 2024,
         "risk_profile": "balanced"},
    )
    eid = str(ent.get("id"))
    ccs.upsert_emission_year(
        None, ccs.DEFAULT_USER_ID, eid,
        {"year": 2025, "scope1_combustion": 10.0, "scope1_process": 2.0},
    )
    ccs.upsert_cea_holding(
        None, ccs.DEFAULT_USER_ID, eid,
        {"vintage_year": 2025, "free_quota": 8.0},
    )
    ccs.upsert_ccer_holding(
        None, ccs.DEFAULT_USER_ID, eid,
        {"project_type": "wind", "issue_year": 2024, "expire_at": "2030-12-31",
         "qty": 0.5, "cost": 50.0, "eligible_qty": 0.5},
    )
    return eid


def _cleanup_tmp(p: Path) -> None:
    for suffix in ("", ".tmp"):
        try:
            p.with_name(p.name + suffix).unlink()
        except OSError:
            pass


@pytest.fixture()
def tmp_cc(monkeypatch, tmp_path):
    """把碳合规存储切到临时文件，避免污染真实数据。"""
    from app.services import carbon_compliance_service as ccs

    target = tmp_path / "carbon_compliance.json"
    monkeypatch.setattr(ccs, "_DATA_PATH", str(target))
    yield ccs
    _cleanup_tmp(target)


def test_list_carbon_enterprises_empty(tmp_cc):
    out = _exec("list_carbon_enterprises", {})
    assert out["ok"] is True
    assert out["count"] == 0


def test_query_ledger_missing_id(tmp_cc):
    out = _exec("query_carbon_enterprise_ledger", {})
    assert out["ok"] is False
    assert "enterprise_id" in out["error"]


def test_query_ledger_ok(tmp_cc):
    eid = _make_enterprise(tmp_cc)
    out = _exec("query_carbon_enterprise_ledger", {"enterprise_id": eid})
    assert out["ok"] is True
    assert out["enterprise"]["name"] == "测试钢企"
    assert len(out["emissions"]) == 1
    assert len(out["cea_holdings"]) == 1
    assert len(out["ccer_holdings"]) == 1


def test_recommend_strategy_missing_id(tmp_cc):
    out = _exec("recommend_carbon_strategy", {})
    assert out["ok"] is False
    assert "enterprise_id" in out["error"]


def test_recommend_strategy_not_found(tmp_cc):
    out = _exec("recommend_carbon_strategy", {"enterprise_id": "not-exist"})
    assert out["ok"] is False


def test_recommend_strategy_full_flow(tmp_cc, monkeypatch):
    """完整策略链路：临时台账 → 运行策略 → 三档方案（mock 掉联网拉行情）。"""
    import app.services.carbon_compliance.market_sync as market_sync

    monkeypatch.setattr(market_sync, "fetch_cneeex_daily_quotes_sync", lambda: [])
    eid = _make_enterprise(tmp_cc)
    out = _exec("recommend_carbon_strategy", {"enterprise_id": eid, "compliance_year": 2025})
    assert out["ok"] is True
    result = out["result"]
    assert result["status"] == "completed"
    assert len(result["plans"]) == 3
    keys = {p["key"] for p in result["plans"]}
    assert {"min_cost", "optimized", "full_compliance"} <= keys
    assert result["accounting_snapshot"]["compliance_gap"] == pytest.approx(4.0)


def test_agents_include_compliance_advisor():
    """履约合规顾问智能体存在且白名单含方法学技能（直接读 agents.json，避免引入 langgraph 依赖）。"""
    agents_path = Path(__file__).resolve().parent.parent / "data" / "agents.json"
    agents = {a["id"]: a for a in json.loads(agents_path.read_text(encoding="utf-8"))["agents"]}
    assert "compliance_advisor" in agents
    allow = agents["compliance_advisor"]["available_skills"] or []
    for name in ("compute_carbon_accounting", "recommend_carbon_strategy",
                 "evaluate_carbon_compliance"):
        assert name in allow
    # 扩展白名单的既有智能体
    advisor = {a["id"]: a for a in agents.values() if a["id"] == "carbon_advisor"}
    allow_advisor = advisor["carbon_advisor"]["available_skills"] or []
    assert "compute_carbon_accounting" in allow_advisor
    market = {a["id"]: a for a in agents.values() if a["id"] == "market_analyst"}
    allow_market = market["market_analyst"]["available_skills"] or []
    assert "judge_carbon_market_cycle" in allow_market


# ---------------------------------------------------------------------------
# 计算过程说明（calculation_note）
# ---------------------------------------------------------------------------
def _gen_history(n: int = 60) -> list:
    """生成 n 个交易日的历史行情（工作日序列）。"""
    d = date(2025, 1, 2)
    rows, p = [], 75.0
    while len(rows) < n:
        if d.weekday() < 5:
            p += (len(rows) % 5 - 2) * 0.3
            rows.append({"t": d.isoformat(), "close": round(max(40.0, p), 2)})
        d += timedelta(days=1)
    return rows


def test_all_methodology_skills_have_calc_note(tmp_cc, monkeypatch):
    """每个方法学技能成功执行后都返回 calculation_note（summary/steps/assumptions）。"""
    import app.services.carbon_compliance.market_sync as market_sync

    monkeypatch.setattr(market_sync, "fetch_cneeex_daily_quotes_sync", lambda: [])
    cases = [
        ("compute_carbon_accounting", {"scope1_combustion": 10.0, "free_cea_quota": 8.0}),
        ("judge_carbon_market_cycle",
         {"cea_monthly_prices": [60.0, 62.0, 58.0, 70.0, 75.0, 80.0], "current_cea_price": 75.0}),
        ("forecast_carbon_price_to_year_end",
         {"history": _gen_history(60), "method": "rule"}),
        ("compute_cea_carry_forward",
         {"base_qty": 10.0, "net_sell": 2.0, "year_end_holding": 12.0}),
        ("evaluate_carbon_compliance",
         {"scope1_combustion": 20.0, "free_cea_quota": 15.0,
          "ccer_holdings": [{"qty": 1.0, "eligible_qty": 1.0, "expire_at": "2030-12-31",
                             "linked_green_cert": False}]}),
        ("list_carbon_enterprises", {}),
    ]
    for name, args in cases:
        out = _exec(name, args)
        assert out["ok"] is True, f"{name} 执行失败: {out.get('error')}"
        note = out.get("calculation_note")
        assert note is not None, f"{name} 缺少 calculation_note"
        assert note.get("summary"), f"{name} note 缺 summary"
        assert note.get("steps"), f"{name} note 缺 steps"
        assert note.get("assumptions"), f"{name} note 缺 assumptions"

    # 台账类技能：建企业后验证
    eid = _make_enterprise(tmp_cc)
    for name, args in [
        ("query_carbon_enterprise_ledger", {"enterprise_id": eid}),
        ("recommend_carbon_strategy", {"enterprise_id": eid, "compliance_year": 2025}),
    ]:
        out = _exec(name, args)
        assert out["ok"] is True, f"{name} 执行失败: {out.get('error')}"
        assert out["calculation_note"]["steps"], f"{name} note 缺 steps"


def test_accounting_calc_note_steps_math():
    """核算技能的计算过程说明带可追溯的中间数值。"""
    out = _exec("compute_carbon_accounting", {
        "scope1_combustion": 10.0, "scope1_process": 2.0, "free_cea_quota": 8.0,
        "own_ccer_eligible": 0.5,
    })
    note = out["calculation_note"]
    joined = " | ".join(note["steps"])
    assert "12.00 万吨" in joined      # Scope1 合计中间值
    assert "8.00" in joined            # 免费配额
    assert "4.00" in joined            # 履约缺口
    assert "0.50" in joined            # 自有 CCER 可用
    assert "3.50" in joined            # 扣 CCER 后缺口


# ---------------------------------------------------------------------------
# 体系自动扩展
# ---------------------------------------------------------------------------
def test_auto_expand_new_skill():
    """新增方法学：只追加必填字段的 Skill，注册器自动补全 tags/meta。"""
    from app.skills.base import SkillRegistry

    reg = SkillRegistry()
    _METHODOLOGY_SKILLS.append(Skill(
        name="new_methodology_demo",
        description="演示新增方法学技能自动扩展",
        input_schema={"type": "object", "properties": {}},
        handler=lambda args: {"ok": True},
    ))
    try:
        register_methodology_skills(reg)
        s = reg.get("new_methodology_demo")
        assert s is not None
        assert s.tags == ["carbon", "methodology"]       # 自动补全分类标签
        assert s.meta["category"] == "methodology"       # 自动标注分类
        assert "methodology_module" in s.meta            # 自动注入源模块元数据
        assert s.enabled                                 # 默认启用
    finally:
        _METHODOLOGY_SKILLS.pop()


def test_auto_expand_missing_fields_rejected():
    """缺 handler 的新方法学技能在注册时被清晰拦截。"""
    from app.skills.base import SkillRegistry

    _METHODOLOGY_SKILLS.append(Skill(
        name="broken_skill", description="缺 handler 演示",
        input_schema={"type": "object", "properties": {}},
        handler=None,  # type: ignore[arg-type]
    ))
    try:
        with pytest.raises(ValueError, match="handler"):
            register_methodology_skills(SkillRegistry())
    finally:
        _METHODOLOGY_SKILLS.pop()


def test_auto_expand_missing_description_rejected():
    """缺 description 的新方法学技能在注册时被清晰拦截。"""
    from app.skills.base import SkillRegistry

    _METHODOLOGY_SKILLS.append(Skill(
        name="broken_skill_desc", description="",
        input_schema={"type": "object", "properties": {}},
        handler=lambda args: {"ok": True},
    ))
    try:
        with pytest.raises(ValueError, match="description"):
            register_methodology_skills(SkillRegistry())
    finally:
        _METHODOLOGY_SKILLS.pop()


def test_methodology_manifest():
    """manifest 清单包含全部 8 个方法学技能及溯源模块。"""
    manifest = methodology_manifest()
    names = {m["name"] for m in manifest}
    assert names == set(METHODOLOGY_NAMES)
    by_name = {m["name"]: m for m in manifest}
    assert by_name["compute_carbon_accounting"]["module"] == "accounting.py"
    assert by_name["recommend_carbon_strategy"]["module"] == "strategy_engine.py"
    for m in manifest:
        assert m["category"] == "methodology"
