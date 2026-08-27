"""控排企业履约综合分析报告：台账 + 策略引擎 + 预测 + 联网政策 + AI 叙事。

照搬自 pdf_trans 参考项目（backend/app/services/carbon_compliance/compliance_analysis_report.py），
适配本平台：无 SQLAlchemy（db 传 None）、企业/用户 ID 为字符串。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from typing import Any, Callable

logger = logging.getLogger(__name__)

ProgressFn = Callable[[int, str], None]
ContentFn = Callable[[str], None]


def _parse_ai_context(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {"note": text[:500]}


def _fmt_num(v: Any, digits: int = 0) -> str:
    try:
        n = float(v)
    except Exception:
        return "—"
    if digits <= 0:
        return f"{n:.0f}"
    return f"{n:.{digits}f}"


def _fmt_wan(v: Any, digits: int = 2) -> str:
    """数量展示（库内已为万吨）。"""
    try:
        n = float(v)
    except Exception:
        return "—"
    return f"{n:.{digits}f}".rstrip("0").rstrip(".") or "0"


def _plans_md(plans: list[dict[str, Any]]) -> str:
    from app.services.carbon_compliance.labels import (
        TIME_WINDOW_LABELS,
        plan_action_zh,
        zh,
    )

    lines: list[str] = []
    for p in plans or []:
        title = p.get("title") or p.get("key") or "方案"
        lines.append(f"### {title}")
        if p.get("description"):
            lines.append(str(p["description"]))
        lines.append(
            f"- 总成本（含手续费=成交总额×费率）：{_fmt_num(p.get('total_cost'))} 元；"
            f"净节约：{_fmt_num(p.get('net_saving'))} 元；"
            f"窗口：{zh(TIME_WINDOW_LABELS, p.get('time_window'))}"
        )
        actions = p.get("actions") or []
        if actions:
            lines.append("")
            lines.append("| 动作 | 数量(万吨) | 单价(元/吨) | 窗口 | 说明 |")
            lines.append("|---|---:|---:|---|---|")
            for a in actions:
                lines.append(
                    f"| {plan_action_zh(a.get('action'))} | {_fmt_wan(a.get('qty'))} | "
                    f"{_fmt_num(a.get('unit_price'), 2)} | "
                    f"{zh(TIME_WINDOW_LABELS, a.get('window'))} | "
                    f"{(a.get('note') or '').replace('|', '/')} |"
                )
        notes = (p.get("compliance") or {}).get("notes") or []
        if notes:
            lines.append("")
            for n in notes:
                lines.append(f"- {n}")
        lines.append("")
    return "\n".join(lines).strip() or "（暂无策略动作）"


def _alerts_md(alerts: list[dict[str, Any]]) -> str:
    from app.services.carbon_compliance.labels import (
        ALERT_LEVEL_LABELS,
        ALERT_TYPE_LABELS,
        zh,
    )

    if not alerts:
        return "（当前无触发预警）"
    lines = ["| 级别 | 类型 | 说明 |", "|---|---|---|"]
    for a in alerts:
        level = zh(ALERT_LEVEL_LABELS, a.get("level"))
        atype = zh(ALERT_TYPE_LABELS, a.get("alert_type"))
        lines.append(
            f"| {level} | {atype} | "
            f"{(a.get('message') or '').replace('|', '/')} |"
        )
    return "\n".join(lines)


async def build_compliance_factsheet(
    db: Any,
    user_id: str,
    *,
    enterprise_id: str,
    compliance_year: int,
    forecast_method: str = "rule",
    on_progress: ProgressFn | None = None,
) -> dict[str, Any]:
    """核算/策略/预测/政策检索，返回事实底稿与结构化快照。"""
    from app.services import carbon_compliance_service as ccs
    from app.services.carbon_compliance.market_sync import fetch_cneeex_daily_quotes_sync
    from app.services.carbon_compliance.price_forecast import forecast_cea_to_year_end

    def prog(p: int, msg: str) -> None:
        if on_progress:
            on_progress(p, msg)

    prog(8, "正在加载企业档案与策略配置…")
    ent = ccs.get_enterprise(db, user_id, enterprise_id)
    if not ent:
        raise LookupError("企业不存在或无权访问")
    settings = ccs.get_settings(db)

    prog(18, "正在读取排放 / CEA / CCER 台账…")
    emissions = ccs.list_emission_years(db, enterprise_id)
    cea_rows = ccs.list_cea_holdings(db, enterprise_id)
    ccer_rows = ccs.list_ccer_holdings(db, enterprise_id)

    prog(30, "正在核算履约缺口并生成三档策略…")
    run = ccs.run_strategy(db, user_id, enterprise_id, compliance_year, notify=False)
    run_dict = ccs.run_to_dict(run)
    accounting = run_dict.get("accounting_snapshot") or {}
    market_tags = run_dict.get("market_tags") or {}
    plans = run_dict.get("plans") or []

    from app.services.carbon_compliance.alerts import build_alerts
    from app.services.carbon_compliance.carry_forward import CarryForwardResult
    from app.services.carbon_compliance.defaults import default_settings

    industry_params = (settings.get("industry_params") or {}).get(str(ent.industry or "")) or {}
    if not industry_params:
        industry_params = (default_settings().get("industry_params") or {}).get(
            str(ent.industry or "")
        ) or {}
    compliance_cfg_early = settings.get("compliance") or {}
    ccer_planned = 0.0
    for p in plans:
        for a in p.get("actions") or []:
            if a.get("action") in ("use_ccer", "buy_ccer"):
                ccer_planned = max(ccer_planned, float(a.get("qty") or 0))
                break
    carry_raw = market_tags.get("carry_forward") or {}
    carry_obj = None
    if carry_raw:
        try:
            carry_obj = CarryForwardResult(
                deadline_md=str(carry_raw.get("deadline_md") or "06-10"),
                deadline=(
                    date.fromisoformat(str(carry_raw["deadline"])[:10])
                    if carry_raw.get("deadline")
                    else None
                ),
                base_qty=float(carry_raw.get("base_qty") or 0),
                net_sell=float(carry_raw.get("net_sell") or 0),
                net_sell_multiplier=float(carry_raw.get("net_sell_multiplier") or 1.5),
                year_end_holding=float(carry_raw.get("year_end_holding") or 0),
                formula_cap=float(carry_raw.get("formula_cap") or 0),
                max_carry=float(carry_raw.get("max_carry") or 0),
                excess=float(carry_raw.get("excess") or 0),
                sell_to_expand_cap=float(carry_raw.get("sell_to_expand_cap") or 0),
            )
        except Exception:
            carry_obj = None
    alert_rows = build_alerts(
        compliance_year=compliance_year,
        clearance_deadline_md=str(industry_params.get("clearance_deadline_md") or "12-31"),
        warn_days=list(compliance_cfg_early.get("clearance_warn_days") or [90, 30, 15]),
        compliance_gap=float(accounting.get("compliance_gap") or 0),
        ccer_used=ccer_planned,
        ccer_cap=float(accounting.get("ccer_cap") or 0),
        price_band=str(market_tags.get("price_band") or ""),
        carry_forward=carry_obj,
    )

    prog(48, "正在计算至年底碳价预测…")
    hist = fetch_cneeex_daily_quotes_sync()
    fc = forecast_cea_to_year_end(hist, method=forecast_method)
    fc_summary = (fc.get("summary") or {}) if fc.get("ok") else {}

    prog(62, "正在检索政策资讯、社媒观点与行业减碳实践…")
    from app.services.carbon_compliance.industry_playbook import (
        industry_strategy_md,
        research_industry_abatement,
    )
    from app.services.carbon_compliance.labels import (
        ACTION_TAG_LABELS,
        FORECAST_METHOD_LABELS,
        PRICE_BAND_LABELS,
        TIME_WINDOW_LABELS,
        bool_zh,
        industry_zh,
        risk_profile_zh,
        zh,
    )
    from app.services.carbon_compliance.policy_research import (
        _sources_md,
        research_carbon_market_news,
    )

    industry = str(ent.industry or "")
    industry_label = industry_zh(industry)
    try:
        policy = await research_carbon_market_news(
            db,
            industry_label=industry_label,
            compliance_year=compliance_year,
            max_items=16,
            read_full=10,
            social_max=8,
            official_max=8,
        )
    except Exception as exc:
        logger.warning("policy deep-research failed: %s", exc)
        policy = {
            "ok": False,
            "summary_md": "本次未获取到。",
            "sources": [],
        }

    carry_early = market_tags.get("carry_forward") or {}
    try:
        industry_pack = await research_industry_abatement(
            db,
            industry=industry,
            industry_label=industry_label,
            compliance_year=compliance_year,
            compliance_gap=float(accounting.get("compliance_gap") or 0),
            carry_excess=float(carry_early.get("excess") or 0),
        )
    except Exception as exc:
        logger.warning("industry abatement research failed: %s", exc)
        industry_pack = {
            "ok": False,
            "summary_md": industry_strategy_md(
                industry,
                compliance_gap=float(accounting.get("compliance_gap") or 0),
                carry_excess=float(carry_early.get("excess") or 0),
            ),
            "sources": [],
        }

    ent_d = ccs.enterprise_to_dict(ent)
    profile_cfg = (settings.get("strategy_profiles") or {}).get(ent.risk_profile) or {}
    compliance_cfg = settings.get("compliance") or {}
    channel_cfg = settings.get("channel") or {}
    cost_cfg = settings.get("cost") or {}
    carry_info = market_tags.get("carry_forward") or {}

    # 统一编号来源（政策/社媒 + 行业减碳）
    all_sources: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for src in list((policy or {}).get("sources") or []) + list(
        (industry_pack or {}).get("sources") or []
    ):
        if not isinstance(src, dict):
            continue
        url = str(src.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        all_sources.append(src)
    sources_block = _sources_md(all_sources, limit=24, start=1)

    parts: list[str] = []
    parts.append("## 一、企业基本情况\n")
    parts.append(
        f"- 行业：{industry_label}；风险画像：{risk_profile_zh(ent_d.get('risk_profile'))}；"
        f"纳入年：{ent_d.get('market_start_year')}；信用代码：{ent_d.get('uscc') or '—'}\n"
        f"- 年度预算上限：{_fmt_num(ent_d.get('annual_budget_cap'))} 元\n"
        f"- 履约年份：{compliance_year}\n"
    )
    parts.append("\n### 台账摘要\n")
    parts.append(
        f"- 排放年份：{len(emissions)} 年；CEA 持仓记录：{len(cea_rows)}；"
        f"CCER 持仓记录：{len(ccer_rows)}\n"
    )

    parts.append("\n## 二、履约核算结果\n")
    parts.append(
        "### 计算过程\n"
        "- 可用 CEA = 当年分配 + 结转量\n"
        "- 履约缺口 = 核查排放 − 可用 CEA（负值表示盈余）\n"
        "- 台账可抵扣 CCER = 未过期且非绿证双计的持仓可抵扣量之和（且不超过持有存量）\n"
        "- 本履约可动用 CCER = min(台账可抵扣, CCER 上限, max(履约缺口, 0))；"
        "盈余企业为 0\n"
        "- 扣自有 CCER 后缺口 = 履约缺口 − 本履约可动用 CCER\n\n"
    )
    parts.append(
        f"| 指标 | 数值 |\n|---|---:|\n"
        f"| 核查排放(万吨) | {_fmt_wan(accounting.get('verified_emission'))} |\n"
        f"| 可用 CEA 合计(万吨) | {_fmt_wan(accounting.get('free_cea_quota'))} |\n"
        f"| 其中当年分配(万吨) | {_fmt_wan(accounting.get('allocated_free_cea'))} |\n"
        f"| 其中结转量(万吨) | {_fmt_wan(accounting.get('carry_forward_qty'))} |\n"
        f"| 履约缺口(万吨) | {_fmt_wan(accounting.get('compliance_gap'))} |\n"
        f"| CCER 上限(万吨) | {_fmt_wan(accounting.get('ccer_cap'))} |\n"
        f"| 台账可抵扣 CCER(万吨) | {_fmt_wan(accounting.get('own_ccer_eligible'))} |\n"
        f"| 本履约可动用 CCER(万吨) | {_fmt_wan(accounting.get('own_ccer_usable'))} |\n"
        f"| 扣自有 CCER 后缺口(万吨) | {_fmt_wan(accounting.get('residual_gap_after_own_ccer'))} |\n"
    )

    if carry_info:
        b = _fmt_wan(carry_info.get("base_qty"))
        n = _fmt_wan(carry_info.get("net_sell"))
        m = _fmt_num(carry_info.get("net_sell_multiplier"), 2)
        fc = _fmt_wan(carry_info.get("formula_cap"))
        h = _fmt_wan(carry_info.get("year_end_holding"))
        mc = _fmt_wan(carry_info.get("max_carry"))
        ex = _fmt_wan(carry_info.get("excess"))
        parts.append("\n### 结转测算过程\n")
        parts.append(
            f"1. 结转日：{carry_info.get('deadline') or carry_info.get('deadline_md') or '—'}\n"
            f"2. 基础额度 B = {b} 万吨；当前净卖出 N = {n} 万吨；倍数 M = {m}\n"
            f"3. 公式上限 = B + max(N,0)×M = {fc} 万吨\n"
            f"4. 年末持仓估算 H ≈ max(0, −min(0, 履约缺口)) = {h} 万吨\n"
            f"5. 最大可结转 = min(公式上限, H) = {mc} 万吨\n"
            f"6. 超额 = max(0, H − 最大可结转) = {ex} 万吨\n"
            f"7. 若以扩净卖出覆盖超额，建议至少再卖："
            f"{_fmt_wan(carry_info.get('sell_to_expand_cap'))} 万吨"
            f"（Δ ≥ 超额/(1+M)）\n"
        )

    parts.append("\n## 三、市场研判与价格预测\n")
    parts.append(
        f"- 价格带：{zh(PRICE_BAND_LABELS, market_tags.get('price_band'))}；"
        f"时间窗：{zh(TIME_WINDOW_LABELS, market_tags.get('time_window'))}；"
        f"建议动作：{zh(ACTION_TAG_LABELS, market_tags.get('action_tag'))}\n"
        f"- 研判说明：{market_tags.get('rationale') or '—'}\n"
    )
    if fc_summary:
        parts.append(
            f"- 预测算法：{zh(FORECAST_METHOD_LABELS, fc_summary.get('method') or forecast_method)}\n"
            f"- 现价锚点：{_fmt_num(fc_summary.get('last_close'), 2)} 元/吨；"
            f"预测年底：{_fmt_num(fc_summary.get('year_end_price'), 2)} "
            f"（{_fmt_num(fc_summary.get('year_end_low'), 2)}–"
            f"{_fmt_num(fc_summary.get('year_end_high'), 2)}）\n"
            f"- 预测高点：{_fmt_num(fc_summary.get('peak_price'), 2)}（"
            f"{fc_summary.get('peak_date') or '—'}）；"
            f"预测低点：{_fmt_num(fc_summary.get('trough_price'), 2)}（"
            f"{fc_summary.get('trough_date') or '—'}）\n"
        )
    elif market_tags.get("price_forecast"):
        pf = market_tags["price_forecast"]
        parts.append(
            f"- 策略内嵌预测年底：{_fmt_num(pf.get('year_end_price'), 2)}；"
            f"高点：{_fmt_num(pf.get('peak_price'), 2)}（{pf.get('peak_date') or '—'}）\n"
        )

    parts.append("\n## 四、分析预警\n")
    parts.append(_alerts_md(alert_rows))
    parts.append("\n")

    parts.append("\n## 五、策略约束配置（当前生效）\n")
    parts.append(
        f"- CCER 抵扣比例：{compliance_cfg.get('ccer_max_ratio')}；"
        f"低/中高价分位：{compliance_cfg.get('price_low_percentile')} / "
        f"{compliance_cfg.get('price_mid_percentile')}\n"
        f"- 优先线下撮合：{bool_zh(channel_cfg.get('prefer_offline'))}；"
        f"线下假定折扣：{channel_cfg.get('offline_discount_vs_listed')}；"
        f"挂牌手续费率(单边)：{cost_cfg.get('listing_fee_rate', cost_cfg.get('trade_fee_rate'))}；"
        f"大宗手续费率(单边)：{cost_cfg.get('block_fee_rate', cost_cfg.get('trade_fee_rate'))}；"
        f"逾期罚款：{_fmt_num(cost_cfg.get('overdue_penalty_per_t'))} 元/吨\n"
        f"- 手续费口径：手续费=成交总额×单边费率；买入应付=总额+手续费，卖出实收=总额−手续费；"
        f"挂牌走挂牌费率，线下/大宗走大宗费率；成交总额=万吨×10000×元/吨\n"
        f"- 当前画像开关：允许外购 CCER={bool_zh(profile_cfg.get('allow_buy_external_ccer'))}；"
        f"允许出售盈余={bool_zh(profile_cfg.get('allow_sell_surplus'))}；"
        f"允许低位囤存={bool_zh(profile_cfg.get('allow_stockpile'))}\n"
    )

    parts.append("\n## 六、规则引擎三档策略（保守/平衡/进取口径）\n")
    parts.append(_plans_md(plans))

    parts.append("\n## 七、政策与社媒观点\n")
    parts.append(str((policy or {}).get("summary_md") or "本次未获取到"))

    parts.append("\n## 八、行业特征与节能降碳发展建议\n")
    parts.append(
        str(
            (industry_pack or {}).get("summary_md")
            or industry_strategy_md(
                industry,
                compliance_gap=float(accounting.get("compliance_gap") or 0),
                carry_excess=float(carry_info.get("excess") or 0),
            )
        )
    )

    if sources_block:
        # 来源不写入底稿正文（避免模型改写成「第七章/第八章」）；单独交给撰写阶段强制贴到文末
        pass

    factsheet = "\n".join(parts)
    return {
        "enterprise": ent_d,
        "run": run_dict,
        "alerts": alert_rows,
        "forecast_summary": fc_summary,
        "policy": policy,
        "industry_abatement": industry_pack,
        "sources": all_sources,
        "sources_md": sources_block,
        "settings_slice": {
            "compliance": compliance_cfg,
            "channel": channel_cfg,
            "cost": cost_cfg,
            "profile": profile_cfg,
        },
        "factsheet_md": factsheet,
    }


def _analysis_system_prompt(*, subject: str, year: int) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"你是全国碳市场控排企业履约顾问，正在为「{subject}」出具 {year} 年履约综合分析报告。\n"
        f"生成时间：{now}\n"
        "硬约束：\n"
        "1. 仅基于用户提供的事实底稿与结构化数字，禁止编造碳价、政策条文、排放量或成本。\n"
        "2. 缺口写「本次未获取到」；引用联网材料时用正文标号 [1][2]…，"
        "与文末「信息来源」中带网址的条目对应。"
        "禁止把「事实底稿第×章」或章节名当作信息来源。\n"
        "3. 策略推荐必须覆盖三档：保守 / 平衡 / 进取，并说明适用条件与主要动作、成本量级。\n"
        "4. 全文使用简体中文表述；除 CEA、CCER 等碳市场专有名词外，不要出现英文单词"
        "（禁止 mid、Aggressive、price_spike、buy_cea、True/False 等）。\n"
        "5. 「节能降碳与中长期发展建议」必须写细：吸收底稿第八章行业共性 + 联网最新实践，"
        "按「措施—适用条件—与履约/结转协同」展开，不少于 6 条可执行要点。\n"
        "6. 须吸收底稿第七章社媒摘要：归纳市场情绪，标注「社媒观点、非官方结论」。\n"
        "7. 只写对决策有用的结论与计算过程；禁止出现检索流程、Deep-research、"
        "「正文不入报告」「事实底稿附录」等过程性提示。\n"
        "8. 履约缺口、结转上限等须保留简明计算过程（可用编号步骤）。\n"
        "9. 输出纯 Markdown，必须包含以下标题（顺序可微调但不可缺）：\n"
        f"# 「{subject}」{year} 履约综合分析报告\n\n"
        "## 先看结论\n"
        "## 分析所用关键数据\n"
        "## 企业与履约形势研判\n"
        "## 行情与价格预测解读\n"
        "## 分析预警\n"
        "## 政策与合规要点\n"
        "## 社媒观点与市场情绪\n"
        "## 策略推荐：保守\n"
        "## 策略推荐：平衡\n"
        "## 策略推荐：进取\n"
        "## 节能降碳与中长期发展建议\n"
        "## 执行节奏与风险提示\n"
        "## 研究边界\n"
        "## 信息来源\n"
        "「信息来源」必须放在全文最后；请原样使用用户消息中给出的带 http(s) 链接的编号列表，"
        "禁止改写为「事实底稿第×章」或省略网址。"
        "无来源列表时写「本次无外部可核验链接来源」。"
        "不构成投资或合规承诺。\n"
        "10. 严禁输出任务指令、思考过程、草稿或任何元话语：正文不得复述、解释或总结收到的要求，"
        "不得出现「用户要求」「请撰写」「请输出」「系统提示」「硬约束」「事实底稿」「底稿第×章」"
        "「每段××字」「只输出」「字数要求」等表述，也不要写「以下是根据…生成」之类的前缀，直接给出报告正文。\n"
        "11. 排版要求：使用规范的 Markdown 层级（## 章节、### 小节），善用要点列表、表格与引用；"
        "合理分段，每段不超过 4~5 行，段与段之间空一行，避免超长段落与连续无换行的文本。\n"
    )


def _strip_sources_section(text: str) -> str:
    """去掉文末模型自拟的「信息来源」节，便于替换为真实链接列表。"""
    import re

    return re.sub(
        r"\n+##\s*信息来源\s*\n[\s\S]*\Z",
        "",
        (text or "").rstrip(),
        count=1,
        flags=re.IGNORECASE,
    ).rstrip()


# 提示词/思考链泄漏特征：这些是仅供模型阅读的指令或草稿措辞，绝不应出现在交付报告正文中
_LEAK_PATTERNS: tuple = (
    r"我们需要回答", r"我们需要撰写", r"我们需要解读", r"我们需要输出",
    r"我们需要思考", r"我们需要合理", r"我们需",
    r"请撰写报告", r"撰写报告「", r"请输出完整\s*Markdown",
    r"输出完整\s*Markdown报告", r"输出纯\s*Markdown",
    r"用户要求", r"用户说", r"用户禁止", r"根据用户", r"用户提供的事实底稿",
    r"系统提示", r"系统已计算",
    r"硬约束",
    r"事实底稿", r"底稿第",
    r"只输出该段", r"不要输出标题", r"不要重复数据", r"可含短列表",
    r"每段\s*\d+\s*[-~—]\s*\d+\s*字", r"字数要求",
    r"请严格依据", r"请原样使用",
)


def _is_leak_para(para: str) -> bool:
    """判断一段是否为提示词/思考链泄漏（应剔除）。"""
    p = para.strip()
    if not p:
        return False
    if re.search("|".join(_LEAK_PATTERNS), p):
        return True
    # 思考链自指特征：第一人称任务语言 / 草稿标记 / 自我提问
    if re.match(r"^(我们需要|我们需|可能内容|草稿[:：]|先起草|开始起草)", p):
        return True
    if p.count("？") + p.count("?") >= 2:
        return True
    return False


def _polish_report_text(text: str) -> str:
    """清洗提示词/思考链泄漏段落，并统一 Markdown 排版（分段、压缩空行、标题前空行、去行尾空格）。"""
    paras = re.split(r"\n\s*\n", (text or ""))
    kept = [p for p in paras if not _is_leak_para(p)]
    body = "\n\n".join(kept).strip()
    # 排版统一：压缩多余空行、去除行尾空格、标题前保证空行
    body = re.sub(r"\n{3,}", "\n\n", body)
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"(?<!^)\n(#{1,4}\s)", r"\n\n\1", body)
    return body


def _apply_sources_footer(text: str, sources_md: str) -> str:
    """强制文末为带网址的信息来源（覆盖模型改写的章节伪来源）。"""
    body = _strip_sources_section(text)
    src = (sources_md or "").strip()
    if src:
        return body + "\n\n## 信息来源\n\n" + src + "\n"
    return body + "\n\n## 信息来源\n\n本次无外部可核验链接来源。\n"


async def synthesize_compliance_analysis_stream(
    *,
    subject: str,
    compliance_year: int,
    factsheet_md: str,
    sources_md: str = "",
    on_progress: ProgressFn | None = None,
    on_content: ContentFn | None = None,
) -> str:
    """流式撰写分析正文；失败时自动改非流式兜底，避免空报告。"""
    from app.integrations.deepseek_client import (
        chat_completion_message_async,
        chat_completion_stream_parts,
        is_configured,
    )

    if on_progress:
        on_progress(78, "正在由 AI 综合撰写分析报告…")

    header = f"# 「{subject}」{compliance_year} 履约综合分析报告\n\n"
    buf = [header]
    if on_content:
        on_content("".join(buf))

    sheet = (factsheet_md or "")[:14000]
    src = (sources_md or "").strip()
    messages = [
        {
            "role": "system",
            "content": _analysis_system_prompt(subject=subject, year=compliance_year),
        },
        {
            "role": "user",
            "content": (
                "## 事实底稿（请严格依据；勿把底稿原文整段粘贴进报告）\n\n"
                f"{sheet}\n\n"
                + (
                    "## 外部参考链接（正文可用 [1][2]… 引用；文末信息来源将由系统按下列列表写入，"
                    "请勿自拟「事实底稿第×章」伪来源）\n\n"
                    f"{src}\n\n"
                    if src
                    else ""
                )
                + "输出 Markdown 正文（可含「信息来源」占位，系统会替换为真实链接），无需任何说明性前缀。"
            ),
        },
    ]

    got = False
    stream_err = ""
    try:
        if not is_configured():
            stream_err = "语言模型未配置"
        else:
            async for part in chat_completion_stream_parts(
                messages=messages,
                temperature=0.35,
                timeout=360.0,
                unlimited_output=True,
            ):
                kind = part.get("kind")
                text_part = str(part.get("text") or "")
                if kind == "error":
                    stream_err = text_part or "流式调用失败"
                    logger.warning("compliance analysis stream error: %s", stream_err)
                    break
                if kind == "content" and text_part:
                    got = True
                    buf.append(text_part)
                    if on_content:
                        on_content("".join(buf))
    except Exception as exc:
        stream_err = f"{type(exc).__name__}: {exc}"
        logger.warning("compliance analysis stream failed: %s", exc)

    text = "".join(buf).strip()
    if not got or len(text) < len(header) + 80:
        if on_progress:
            on_progress(82, "流式撰写未完成，改用非流式补写…")
        try:
            choice = await chat_completion_message_async(
                messages=messages,
                temperature=0.35,
                timeout=360.0,
            )
            msg = (choice or {}).get("message") or {}
            body = str(msg.get("content") or "").strip()
            if body:
                got = True
                text = (header + body).strip()
                if on_content:
                    on_content(text)
        except Exception as exc:
            logger.warning("compliance analysis non-stream fallback failed: %s", exc)
            if not stream_err:
                stream_err = f"{type(exc).__name__}"

    if not got or len(text) < len(header) + 80:
        reason = stream_err or "模型未返回有效正文"
        text = (
            f"# 「{subject}」{compliance_year} 履约综合分析报告\n\n"
            "## 先看结论\n\n"
            f"- 本次未能完成 AI 叙事生成（{reason}）。\n"
            "- 请结合三档策略表与政策摘要审慎决策。\n\n"
            "## 分析所用关键数据\n\n"
            f"{sheet}\n\n"
            "## 研究边界\n\n不构成投资或合规承诺。\n"
        )

    text = _polish_report_text(text)
    text = _apply_sources_footer(text, src)
    if on_content:
        on_content(text)

    if on_progress:
        on_progress(96, "正在整理报告版式…")
    return text


async def run_compliance_analysis_report(
    db: Any,
    report,
    *,
    on_progress: ProgressFn,
    on_content: ContentFn,
) -> str:
    """完整流水线：取数 → 策略 → 政策 → 流式撰写。"""
    ctx = _parse_ai_context(report.ai_context or "")
    ent_id_raw = ctx.get("enterprise_id") or ""
    if not ent_id_raw:
        raise ValueError("ai_context.enterprise_id 为空，请选择企业")
    enterprise_id = str(ent_id_raw)
    year = int(ctx.get("compliance_year") or report.target_year or datetime.now().year)
    method = str(ctx.get("forecast_method") or "rule")

    pack = await build_compliance_factsheet(
        db,
        report.user_id,
        enterprise_id=enterprise_id,
        compliance_year=year,
        forecast_method=method,
        on_progress=on_progress,
    )
    on_progress(72, "事实底稿已就绪，开始综合分析…")
    on_content(
        f"# 「{report.subject}」{year} 履约综合分析报告\n\n"
        "## 先看结论\n\n- 正在生成 AI 综合研判…\n\n"
        + pack["factsheet_md"]
    )

    return await synthesize_compliance_analysis_stream(
        subject=report.subject,
        compliance_year=year,
        factsheet_md=pack["factsheet_md"],
        sources_md=str(pack.get("sources_md") or ""),
        on_progress=on_progress,
        on_content=on_content,
    )
