"""方法学 Skills：把碳合规计算方法学注册为智能体可调用的技能。

覆盖方法学（backend/app/services/carbon_compliance/）：
- accounting       碳排放量核算（Scope1/2 → 总量/履约缺口/CCER 上限）
- market_cycle     碳市场行情周期判断（价格分位带 + 时间窗口 → 买卖建议）
- price_forecast   碳价日度预测至年底（rule/ets/sarimax/prophet 多算法）
- carry_forward    CEA 结转额度测算（最大可结转/超额/扩卖需求）
- compliance       履约合规评估（CCER 可抵扣 + 缺口 + 上限）
- strategy_engine  三档履约策略推荐（保守/平衡/进取，需企业台账）
- carbon_compliance_service  企业碳资产台账查询

约定：
- handler 均为同步函数，返回可 JSON 化的 dict；SkillRegistry 统一转文本。
- 数量类参数单位统一为「万吨」（与碳合规方法学一致），价格单位为「元/吨」。
- 需要企业台账的技能：enterprise_id 必填；缺失时返回带 hint 的友好错误，
  引导先调用 list_carbon_enterprises / query_carbon_enterprise_ledger。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import Skill

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数值工具
# ---------------------------------------------------------------------------
def _num(v: Any, default: float = 0.0) -> float:
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _opt_num(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int_arg(v: Any, default: int = 0) -> int:
    n = int(_num(v, default))
    return n if n > 0 else default


def _now_year() -> int:
    return datetime.now().year


def _ent_not_found(enterprise_id: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "error": f"企业不存在或无权访问: {enterprise_id}",
        "hint": "先调用 list_carbon_enterprises 查看企业列表，再传 enterprise_id",
    }


def _require_enterprise(enterprise_id: str) -> Optional[Dict[str, Any]]:
    from app.services import carbon_compliance_service as ccs

    if not enterprise_id:
        return {
            "ok": False,
            "error": "缺少必填参数 enterprise_id（企业 id）",
            "hint": "先调用 list_carbon_enterprises 查看企业列表",
        }
    ent = ccs.get_enterprise(None, ccs.DEFAULT_USER_ID, enterprise_id)
    if not ent:
        return _ent_not_found(enterprise_id)
    return None


# ---------------------------------------------------------------------------
# 1. 碳排放量核算
# ---------------------------------------------------------------------------
def _compute_carbon_accounting(args: Dict[str, Any]) -> Dict[str, Any]:
    """碳排放量核算（履约核查口径）。"""
    from app.services.carbon_compliance.accounting import (
        AccountingInput,
        compute_accounting,
    )

    inp = AccountingInput(
        scope1_combustion=_num(args.get("scope1_combustion")),
        scope1_process=_num(args.get("scope1_process")),
        scope2_power=_num(args.get("scope2_power")),
        purchased_mwh=_num(args.get("purchased_mwh")),
        market_green_mwh=_num(args.get("market_green_mwh")),
        self_gen_mwh=_num(args.get("self_gen_mwh")),
        free_cea_quota=_num(args.get("free_cea_quota")),
        own_ccer_eligible=_num(args.get("own_ccer_eligible")),
        grid_emission_factor=_num(args.get("grid_emission_factor"), 0.5703) or 0.5703,
        ccer_max_ratio=_num(args.get("ccer_max_ratio"), 0.05) or 0.05,
        verified_override=_opt_num(args.get("verified_override")),
    )
    return {"ok": True, "method": "accounting", "result": compute_accounting(inp).to_dict()}


# ---------------------------------------------------------------------------
# 2. 碳市场行情周期判断
# ---------------------------------------------------------------------------
def _judge_carbon_market_cycle(args: Dict[str, Any]) -> Dict[str, Any]:
    """碳市场行情周期判断（价格分位带 + 时间窗口 → 买卖建议动作）。"""
    from app.services import carbon_compliance_service as ccs
    from app.services.carbon_compliance.market_cycle import judge_market_cycle

    prices: List[float] = []
    raw = args.get("cea_monthly_prices") or []
    if raw:
        prices = [_num(p, None) for p in raw]  # type: ignore[list-item]
        prices = [p for p in prices if p is not None]
    current_cea = _opt_num(args.get("current_cea_price"))
    current_ccer = _opt_num(args.get("current_ccer_price"))

    # 未显式给出历史价格时，从市场月度台账回退取数
    if not prices:
        rows = ccs.list_market_cea(None, limit=24)
        prices = [float(r.get("avg_price") or 0) for r in reversed(rows)]
        prices = [p for p in prices if p > 0]
        if current_cea is None and prices:
            current_cea = prices[-1]

    result = judge_market_cycle(
        prices,
        current_cea,
        current_ccer,
        low_percentile=_num(args.get("low_percentile"), 0.30) or 0.30,
        mid_percentile=_num(args.get("mid_percentile"), 0.70) or 0.70,
    )
    out = result.to_dict()
    out["data_note"] = (
        "价格序列来自市场月度台账（公开日均，非实时挂单）" if not raw else "价格序列来自入参"
    )
    return {"ok": True, "method": "market_cycle", "result": out}


# ---------------------------------------------------------------------------
# 3. 碳价日度预测至年底
# ---------------------------------------------------------------------------
def _forecast_carbon_price_to_year_end(args: Dict[str, Any]) -> Dict[str, Any]:
    """碳价日度预测至年底（rule/ets/sarimax/prophet）。"""
    from app.services.carbon_compliance.price_forecast import forecast_to_year_end

    instrument = str(args.get("instrument") or "cea").strip().lower() or "cea"
    if instrument not in ("cea", "ccer"):
        instrument = "cea"
    method = str(args.get("method") or "rule").strip().lower() or "rule"

    hist = args.get("history")
    if hist is None:
        # 仅在调用方未显式提供历史数据时才联网拉取
        from app.services.carbon_compliance.market_sync import (
            fetch_cneeex_daily_quotes_sync,
        )

        hist = fetch_cneeex_daily_quotes_sync() or []
    if not hist:
        return {
            "ok": False,
            "method": "price_forecast",
            "error": "未获取到历史行情，无法预测",
            "hint": "可尝试调用 get_carbon_market_quote 或稍后重试",
        }

    fc = forecast_to_year_end(
        hist,
        instrument=instrument,
        method=method,
        year=_int_arg(args.get("year"), 0) or None,
    )
    if not fc.get("ok"):
        return {"ok": False, "method": "price_forecast",
                "error": fc.get("error") or "预测失败", "points": [], "summary": None}
    return {
        "ok": True,
        "method": "price_forecast",
        "instrument": instrument,
        "anchor": {"date": fc.get("anchor_date"), "price": fc.get("anchor_price")},
        "summary": fc.get("summary"),
        "points": (fc.get("points") or [])[:30],  # 防上下文爆炸，只给前 30 个交易日
    }


# ---------------------------------------------------------------------------
# 4. CEA 结转额度测算
# ---------------------------------------------------------------------------
def _compute_cea_carry_forward(args: Dict[str, Any]) -> Dict[str, Any]:
    """CEA 结转额度测算（最大可结转/超额/需扩卖量）。"""
    from app.services.carbon_compliance.carry_forward import compute_carry_forward

    r = compute_carry_forward(
        base_qty=_num(args.get("base_qty")),
        net_sell=_num(args.get("net_sell")),
        year_end_holding=_num(args.get("year_end_holding")),
        net_sell_multiplier=_num(args.get("net_sell_multiplier"), 1.5) or 1.5,
        deadline_md=str(args.get("deadline_md") or "06-10"),
        deadline_year=_int_arg(args.get("deadline_year"), 0) or None,
    )
    return {"ok": True, "method": "carry_forward", "result": r.to_dict()}


# ---------------------------------------------------------------------------
# 5. 履约合规评估（核算 + CCER 可抵扣 + 上限）
# ---------------------------------------------------------------------------
def _evaluate_carbon_compliance(args: Dict[str, Any]) -> Dict[str, Any]:
    """履约合规评估：核查排放 → 可用配额 → 履约缺口 → CCER 上限与缺口覆盖。"""
    from app.services.carbon_compliance.accounting import (
        AccountingInput,
        compute_accounting,
    )
    from app.services.carbon_compliance.compliance import eligible_ccer_qty

    holdings: List[Dict[str, Any]] = []
    raw_holdings = args.get("ccer_holdings")
    if isinstance(raw_holdings, list):
        for h in raw_holdings:
            if isinstance(h, dict):
                holdings.append({
                    "qty": h.get("qty"),
                    "eligible_qty": h.get("eligible_qty"),
                    "expire_at": h.get("expire_at"),
                    "linked_green_cert": h.get("linked_green_cert"),
                })

    # 未显式传 CCER 持仓时，若给了 enterprise_id 则从台账读取
    from app.services import carbon_compliance_service as ccs

    enterprise_id = str(args.get("enterprise_id") or "").strip()
    if not holdings and enterprise_id:
        if ccs.get_enterprise(None, ccs.DEFAULT_USER_ID, enterprise_id):
            holdings = [
                {
                    "qty": h.get("qty"),
                    "eligible_qty": h.get("eligible_qty"),
                    "expire_at": h.get("expire_at"),
                    "linked_green_cert": h.get("linked_green_cert"),
                }
                for h in ccs.list_ccer_holdings(None, enterprise_id)
            ]

    own_ccer = eligible_ccer_qty(holdings)
    inp = AccountingInput(
        scope1_combustion=_num(args.get("scope1_combustion")),
        scope1_process=_num(args.get("scope1_process")),
        scope2_power=_num(args.get("scope2_power")),
        purchased_mwh=_num(args.get("purchased_mwh")),
        free_cea_quota=_num(args.get("free_cea_quota")),
        own_ccer_eligible=own_ccer,
        grid_emission_factor=_num(args.get("grid_emission_factor"), 0.5703) or 0.5703,
        ccer_max_ratio=_num(args.get("ccer_max_ratio"), 0.05) or 0.05,
        verified_override=_opt_num(args.get("verified_override")),
    )
    acc = compute_accounting(inp)
    result = acc.to_dict()
    gap = float(result.get("compliance_gap") or 0)
    if gap > 1e-9:
        result["conclusion"] = "存在履约缺口，需购买配额或外购 CCER"
    elif gap < -1e-9:
        result["conclusion"] = "配额盈余，可评估结转留存或择机出售"
    else:
        result["conclusion"] = "配额收支平衡"
    return {"ok": True, "method": "compliance", "result": result}


# ---------------------------------------------------------------------------
# 6. 履约策略推荐（三档方案）
# ---------------------------------------------------------------------------
def _recommend_carbon_strategy(args: Dict[str, Any]) -> Dict[str, Any]:
    """基于企业台账运行三档履约策略（保守/平衡/进取）。"""
    from app.services import carbon_compliance_service as ccs

    enterprise_id = str(args.get("enterprise_id") or "").strip()
    err = _require_enterprise(enterprise_id)
    if err:
        return err
    year = _int_arg(args.get("compliance_year"), _now_year())
    try:
        run = ccs.run_strategy(
            None, ccs.DEFAULT_USER_ID, enterprise_id, year, notify=False
        )
    except Exception as exc:  # noqa: BLE001 —— 方法学错误转文本
        return {"ok": False, "method": "strategy",
                "error": f"策略运行失败: {exc}"}
    result = ccs.run_to_dict(run)
    # report_md 为超长 markdown 报告，技能输出有长度上限，转为截断摘要
    md = result.pop("report_md", "") or ""
    result["report_summary"] = (md[:600] + "…") if len(md) > 600 else md
    # plans 中每个 action 含大文本 note/meta，精简为数字字段避免截断
    for plan in result.get("plans") or []:
        plan["actions"] = [
            {k: a.get(k) for k in ("action", "qty", "unit_price", "window")}
            for a in plan.get("actions") or []
        ]
    # market_tags 的研判长文本截短
    tags = result.get("market_tags")
    if isinstance(tags, dict) and tags.get("rationale"):
        tags["rationale"] = (tags["rationale"][:200] + "…") if len(tags["rationale"]) > 200 else tags["rationale"]
    return {"ok": True, "method": "strategy", "result": result}


# ---------------------------------------------------------------------------
# 7. 企业碳资产台账查询
# ---------------------------------------------------------------------------
def _query_carbon_enterprise_ledger(args: Dict[str, Any]) -> Dict[str, Any]:
    """查询企业碳资产台账（排放/预测/CEA/CCER/绿电绿证/预警）。"""
    from app.services import carbon_compliance_service as ccs

    enterprise_id = str(args.get("enterprise_id") or "").strip()
    err = _require_enterprise(enterprise_id)
    if err:
        return err
    uid = ccs.DEFAULT_USER_ID
    return {
        "ok": True,
        "method": "ledger",
        "enterprise": ccs.enterprise_to_dict(ccs.get_enterprise(None, uid, enterprise_id)),
        "emissions": [dict(r) for r in ccs.list_emission_years(None, enterprise_id)],
        "forecasts": [dict(r) for r in ccs.list_forecasts(None, enterprise_id)],
        "cea_holdings": [dict(r) for r in ccs.list_cea_holdings(None, enterprise_id)],
        "cea_trades": [dict(r) for r in ccs.list_cea_trades(None, enterprise_id)],
        "ccer_holdings": [dict(r) for r in ccs.list_ccer_holdings(None, enterprise_id)],
        "green_power": [dict(r) for r in ccs.list_green_power(None, enterprise_id)],
        "green_certs": [dict(r) for r in ccs.list_green_certs(None, enterprise_id)],
        "alerts": [
            dict(r)
            for r in ccs.list_alerts(None, uid, enterprise_id=enterprise_id, limit=20)
        ],
    }


# ---------------------------------------------------------------------------
# 8. 企业列表
# ---------------------------------------------------------------------------
def _list_carbon_enterprises(args: Dict[str, Any]) -> Dict[str, Any]:
    """列出平台已录入的控排企业（履约主体）。"""
    from app.services import carbon_compliance_service as ccs

    rows = ccs.list_enterprises(None, ccs.DEFAULT_USER_ID)
    return {
        "ok": True,
        "method": "enterprises",
        "count": len(rows),
        "enterprises": [ccs.enterprise_to_dict(e) for e in rows],
    }


# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------
_METHODOLOGY_SKILLS: List[Skill] = [
    Skill(
        name="compute_carbon_accounting",
        description=(
            "【方法学·碳排放量核算】按履约核查口径统计企业碳排放量并测算履约缺口。"
            "输入 Scope1 燃料燃烧/工艺过程排放与 Scope2 外购电排放（万吨）、免费配额、"
            "自有 CCER 可抵扣量等，输出核查总量、履约缺口、CCER 上限、扣自有 CCER 后缺口。"
            "数量单位均为万吨；grid_emission_factor 为电网排放因子（默认 0.5703 吨CO2/MWh），"
            "ccer_max_ratio 为 CCER 抵扣比例上限（默认 0.05）。"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "scope1_combustion": {"type": "number", "description": "燃料燃烧排放（万吨CO2）"},
                "scope1_process": {"type": "number", "description": "工艺过程排放（万吨CO2）"},
                "scope2_power": {"type": "number", "description": "外购电力间接排放（万吨CO2，不参与履约核查口径）"},
                "purchased_mwh": {"type": "number", "description": "外购电量（MWh，用于核算 Scope2）"},
                "free_cea_quota": {"type": "number", "description": "免费 CEA 配额（万吨）"},
                "own_ccer_eligible": {"type": "number", "description": "自有 CCER 可抵扣量（万吨）"},
                "grid_emission_factor": {"type": "number", "description": "电网排放因子（吨CO2/MWh），默认 0.5703"},
                "ccer_max_ratio": {"type": "number", "description": "CCER 抵扣上限比例，默认 0.05"},
                "verified_override": {"type": "number", "description": "官方核查总量覆盖（万吨），可选"},
            },
        },
        handler=_compute_carbon_accounting,
        source="builtin",
        tags=["carbon", "methodology", "accounting", "compliance"],
    ),
    Skill(
        name="judge_carbon_market_cycle",
        description=(
            "【方法学·碳市场行情周期判断】基于 CEA 历史价格序列判断当前市场所处位置"
            "（价格分位带 low/mid/high）与时间窗口（early/mid/late），输出买卖建议动作"
            "（buy/sell/hold）与研判说明。可传 cea_monthly_prices 价格序列（元/吨）与"
            "当前 CEA/CCER 价格；不传时自动从市场月度台账取数。"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "cea_monthly_prices": {
                    "type": "array", "items": {"type": "number"},
                    "description": "CEA 月度均价序列（元/吨，时间升序），可选",
                },
                "current_cea_price": {"type": "number", "description": "当前 CEA 价格（元/吨），可选"},
                "current_ccer_price": {"type": "number", "description": "当前 CCER 价格（元/吨），可选"},
                "low_percentile": {"type": "number", "description": "低价分位阈值，默认 0.30"},
                "mid_percentile": {"type": "number", "description": "中价分位阈值，默认 0.70"},
            },
        },
        handler=_judge_carbon_market_cycle,
        source="builtin",
        tags=["carbon", "methodology", "market"],
        timeout=20.0,
    ),
    Skill(
        name="forecast_carbon_price_to_year_end",
        description=(
            "【方法学·碳价日度预测】基于历史日线把 CEA/CCER 价格外推预测至年底，"
            "返回逐交易日预测序列与年底预测价、高低带、峰值谷值摘要。"
            "method 可选 rule（规则模型，默认）/ets（Holt-Winters）/sarimax/prophet；"
            "instrument 可选 cea（默认）/ccer。数据来自交易所官方历史行情。"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "instrument": {"type": "string", "enum": ["cea", "ccer"], "description": "品种，默认 cea"},
                "method": {"type": "string", "enum": ["rule", "ets", "sarimax", "prophet"],
                           "description": "预测算法，默认 rule"},
                "year": {"type": "integer", "description": "预测目标年份，默认当前年"},
                "history": {"type": "array", "description": "可选：自定义历史日线 [{t,close}]，缺省自动拉取"},
            },
        },
        handler=_forecast_carbon_price_to_year_end,
        source="builtin",
        tags=["carbon", "methodology", "market", "forecast"],
        timeout=30.0,
    ),
    Skill(
        name="compute_cea_carry_forward",
        description=(
            "【方法学·CEA 结转额度测算】测算配额年末最大可结转量、超额与为覆盖超额"
            "需要扩大的净卖出量。公式：最大可结转=min(基础+净卖出×倍数, 年末持仓)。"
            "base_qty 为基础额度（万吨，通常取当年免费配额），net_sell 为当前净卖出（万吨），"
            "year_end_holding 为年末持仓估算（万吨），net_sell_multiplier 为净卖出倍数（默认 1.5），"
            "deadline_md 为结转截止日（默认 06-10），deadline_year 为结转年（默认次年）。"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "base_qty": {"type": "number", "description": "基础额度（万吨）"},
                "net_sell": {"type": "number", "description": "当前净卖出（万吨）"},
                "year_end_holding": {"type": "number", "description": "年末持仓估算（万吨）"},
                "net_sell_multiplier": {"type": "number", "description": "净卖出倍数，默认 1.5"},
                "deadline_md": {"type": "string", "description": "结转截止日 MM-DD，默认 06-10"},
                "deadline_year": {"type": "integer", "description": "结转年，默认次年"},
            },
        },
        handler=_compute_cea_carry_forward,
        source="builtin",
        tags=["carbon", "methodology", "compliance", "carry_forward"],
    ),
    Skill(
        name="evaluate_carbon_compliance",
        description=(
            "【方法学·履约合规评估】对控排企业做履约合规测算：核查排放 → 可用配额 → "
            "履约缺口 → CCER 抵扣上限 → 扣自有 CCER 后缺口，并给出合规结论。"
            "scope1_combustion/scope1_process 为燃料燃烧/工艺过程排放（万吨），"
            "free_cea_quota 为免费配额（万吨）；可选传 enterprise_id 自动读取企业 CCER 台账，"
            "或传 ccer_holdings 持仓列表 [{qty,eligible_qty,expire_at,linked_green_cert}]。"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "enterprise_id": {"type": "string", "description": "企业 id（可选，用于读取 CCER 台账）"},
                "scope1_combustion": {"type": "number", "description": "燃料燃烧排放（万吨CO2）"},
                "scope1_process": {"type": "number", "description": "工艺过程排放（万吨CO2）"},
                "scope2_power": {"type": "number", "description": "外购电力间接排放（万吨CO2）"},
                "purchased_mwh": {"type": "number", "description": "外购电量（MWh）"},
                "free_cea_quota": {"type": "number", "description": "免费 CEA 配额（万吨）"},
                "ccer_holdings": {"type": "array", "description": "CCER 持仓列表，可选"},
                "verified_override": {"type": "number", "description": "官方核查总量覆盖（万吨），可选"},
            },
        },
        handler=_evaluate_carbon_compliance,
        source="builtin",
        tags=["carbon", "methodology", "compliance"],
    ),
    Skill(
        name="recommend_carbon_strategy",
        description=(
            "【方法学·履约策略推荐】基于企业台账运行规则引擎，输出三档履约方案"
            "（最低成本/成本优化/稳健履约），含核算快照、市场研判、具体买卖动作"
            "（数量/单价/窗口/渠道）、总成本与预警。需先有企业台账（enterprise_id 必填），"
            "建议先用 list_carbon_enterprises / query_carbon_enterprise_ledger 确认企业。"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "enterprise_id": {"type": "string", "description": "企业 id（必填）"},
                "compliance_year": {"type": "integer", "description": "履约年份，默认当前年"},
            },
            "required": ["enterprise_id"],
        },
        handler=_recommend_carbon_strategy,
        source="builtin",
        tags=["carbon", "methodology", "strategy", "compliance"],
        timeout=90.0,
    ),
    Skill(
        name="query_carbon_enterprise_ledger",
        description=(
            "【方法学·企业碳资产台账查询】查询控排企业的完整碳资产台账：企业档案、"
            "历史排放、排放预测、CEA 持仓与交易、CCER 持仓、绿电绿证、履约预警。"
            "enterprise_id 必填；可用 list_carbon_enterprises 先查看企业列表。"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "enterprise_id": {"type": "string", "description": "企业 id（必填）"},
            },
            "required": ["enterprise_id"],
        },
        handler=_query_carbon_enterprise_ledger,
        source="builtin",
        tags=["carbon", "methodology", "ledger", "compliance"],
    ),
    Skill(
        name="list_carbon_enterprises",
        description=(
            "【方法学·企业列表】列出平台已录入的控排企业（履约主体）档案，"
            "返回企业 id、名称、行业、风险画像、纳入市场年份、预算等。"
            "用户询问某企业履约情况、想运行策略时，先调用本技能确认 enterprise_id。"
        ),
        input_schema={"type": "object", "properties": {}},
        handler=_list_carbon_enterprises,
        source="builtin",
        tags=["carbon", "methodology", "ledger"],
    ),
]


def register_methodology_skills(registry) -> None:
    """把全部方法学 skills 注册到给定 SkillRegistry。"""
    for s in _METHODOLOGY_SKILLS:
        registry.register(s)
