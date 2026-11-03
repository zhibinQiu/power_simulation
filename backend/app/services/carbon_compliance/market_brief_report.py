# -*- coding: utf-8 -*-
"""碳交易市场简报：行情 + 价格位置 + 交易窗口 + 政策 + 我方仓位 → AI 简报正文。

与「履约综合分析」的分工：
- 履约报告的主体是企业（缺口、结转、三档策略、减排路径）；
- 本模块的主体是市场（CEA/CCER 价格与成交、历史分位、预测区间、交易窗口），
  企业只作为「我方仓位」一章出现，未选择企业时整章省略。

底稿全部由现有模块实时取数组装，不复用履约底稿，避免两类报告串味。
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any

from .compliance_analysis_report import (
    ContentFn,
    ProgressFn,
    _fmt_wan,
    _parse_ai_context,
    _report_header,
    report_heading_of,
    synthesize_compliance_analysis_stream,
)

logger = logging.getLogger(__name__)

# 行情默认观察窗：近 20 个交易日（约一个自然月），避开自然日带来的节假日空洞
DEFAULT_WINDOW_DAYS = 20


# ---------- 基础计算 ----------


def _f(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct(a: Any, b: Any) -> float | None:
    """涨跌幅（%）：b 相对 a。"""
    fa, fb = _f(a), _f(b)
    if fa in (None, 0.0) or fb is None:
        return None
    return (fb - fa) / fa * 100.0


def _pct_text(v: float | None) -> str:
    return "—" if v is None else f"{v:+.2f}%"


def _price(v: Any) -> str:
    n = _f(v)
    return "—" if n is None else f"{n:.2f}"


def _wan(v: Any) -> str:
    n = _f(v)
    if n is None:
        return "—"
    return f"{n / 10000.0:.2f}"


def _clip(text: Any, n: int = 120) -> str:
    s = str(text or "").strip().replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def _load_cea_daily() -> list[dict[str, Any]]:
    """CEA 日行情（含成交量，单位吨）。取数失败返回空列表，由调用方降级。"""
    from .market_sync import fetch_cneeex_daily_quotes_sync

    try:
        rows = fetch_cneeex_daily_quotes_sync() or []
    except Exception as exc:  # noqa: BLE001 —— 行情异常不应中断整份简报
        logger.warning("market brief cea daily fetch failed: %s", exc)
        return []
    out: list[dict[str, Any]] = []
    for r in rows:
        t = str(r.get("t") or "")[:10]
        close = _f(r.get("close") if r.get("close") is not None else r.get("price"))
        if not t or close is None:
            continue
        out.append(
            {
                "t": t,
                "close": close,
                "open": _f(r.get("open")),
                "high": _f(r.get("high")),
                "low": _f(r.get("low")),
                "volume": _f(r.get("volume")),
            }
        )
    out.sort(key=lambda x: x["t"])
    return out


def _window_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """区间统计：首末收盘、涨跌幅、区间极值、日均收盘、成交合计。"""
    if not rows:
        return {}
    closes = [r["close"] for r in rows if r.get("close") is not None]
    if not closes:
        return {}
    highs = [r["high"] for r in rows if r.get("high") is not None] or closes
    lows = [r["low"] for r in rows if r.get("low") is not None] or closes
    vols = [r["volume"] for r in rows if r.get("volume") is not None]
    return {
        "start": rows[0]["t"],
        "end": rows[-1]["t"],
        "days": len(closes),
        "first": closes[0],
        "last": closes[-1],
        "change_pct": _pct(closes[0], closes[-1]),
        "high": max(highs),
        "low": min(lows),
        "avg": sum(closes) / len(closes),
        "volume_total": sum(vols) if vols else None,
        "volume_avg": (sum(vols) / len(vols)) if vols else None,
        "volume_days": len(vols),
    }


def _monthly_rows(rows: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    """按月聚合（均价=收盘均值，极值取月内高低，成交合计）；limit=0 表示全量。"""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        buckets.setdefault(r["t"][:7], []).append(r)
    out: list[dict[str, Any]] = []
    for ym in sorted(buckets):
        items = buckets[ym]
        closes = [i["close"] for i in items if i.get("close") is not None]
        if not closes:
            continue
        highs = [i["high"] for i in items if i.get("high") is not None] or closes
        lows = [i["low"] for i in items if i.get("low") is not None] or closes
        vols = [i["volume"] for i in items if i.get("volume") is not None]
        out.append(
            {
                "ym": ym,
                "avg": sum(closes) / len(closes),
                "high": max(highs),
                "low": min(lows),
                "close": closes[-1],
                "volume_total": sum(vols) if vols else None,
                "days": len(closes),
            }
        )
    return out[-limit:] if limit and limit > 0 else out


def _percentile_of(values: list[float], price: float | None) -> float | None:
    """price 在 values 中的分位（低于它的比例，%）。"""
    if price is None or len(values) < 12:
        return None
    below = sum(1 for v in values if v < price)
    return below / len(values) * 100.0


async def _load_ccer(max_pages: int = 8) -> dict[str, Any]:
    """CCER 近期成交：取最近若干个交易日，给出最新价、成交量与近 5 日均价。"""
    from .market_sync import fetch_ccer_official_daily_quotes

    try:
        pack = await fetch_ccer_official_daily_quotes(max_pages=max_pages)
    except Exception as exc:  # noqa: BLE001
        logger.warning("market brief ccer fetch failed: %s", exc)
        return {}
    quotes = [q for q in (pack.get("quotes") or []) if getattr(q, "close", None) is not None]
    if not quotes:
        return {}
    quotes.sort(key=lambda q: q.trade_date)
    latest = quotes[-1]
    recent = [float(q.close) for q in quotes[-5:]]
    return {
        "date": latest.trade_date.isoformat(),
        "close": float(latest.close),
        "volume": float(latest.volume) if latest.volume is not None else None,
        "avg5": sum(recent) / len(recent),
        "count": len(quotes),
        "oldest": quotes[0].trade_date.isoformat(),
    }


# ---------- 企业仓位 ----------


def _enterprise_pack(
    db: Any, user_id: str, enterprise_id: str, year: int
) -> dict[str, Any]:
    """读取企业台账并跑一次策略，取缺口、持仓、预算约束与平衡画像动作。"""
    from app.services import carbon_compliance_service as ccs

    ent = ccs.get_enterprise(db, user_id, enterprise_id)
    if not ent:
        return {}
    settings = ccs.get_settings(db)
    run = ccs.run_strategy(db, user_id, enterprise_id, year, notify=False)
    run_d = ccs.run_to_dict(run)
    acc = run_d.get("accounting_snapshot") or {}
    tags = run_d.get("market_tags") or {}
    plans = run_d.get("plans") or []
    industry_params = (settings.get("industry_params") or {}).get(str(ent.industry or "")) or {}
    compliance_cfg = settings.get("compliance") or {}
    cost_cfg = settings.get("cost") or {}

    # 三档方案键：min_cost（保守）/ optimized（平衡）/ full_compliance（进取）
    core_plan: dict[str, Any] = {}
    for p in plans:
        if str(p.get("key") or "") == "optimized":
            core_plan = p
            break
    if not core_plan and len(plans) >= 2:
        core_plan = plans[1]
    if not core_plan and plans:
        core_plan = plans[0]

    # 动作在 planned_actions（方案被预算等约束阻断时 actions 为空）
    actions = list(core_plan.get("planned_actions") or core_plan.get("actions") or [])
    issues = ((core_plan.get("compliance") or {}).get("issues") or [])

    return {
        "enterprise": ccs.enterprise_to_dict(ent),
        # 各年度的「当年免费分配量」：政策摘要要用它核对预分配口径，
        # acc.free_cea_quota 是滚动清缴后的可用量，混入了结存与买卖，不能直接比
        "alloc_by_year": {
            int(h.get("vintage_year") or 0): float(h.get("free_quota") or 0)
            for h in (ent.get("cea_holdings") or [])
            if h.get("vintage_year")
        },
        "accounting": acc,
        "tags": tags,
        "carry": tags.get("carry_forward") or {},
        "core_plan": core_plan,
        "plan_actions": actions,
        "plan_blocked": bool(core_plan.get("blocked")),
        "plan_issues": [str(i.get("message") or "") for i in issues if isinstance(i, dict)],
        "clearance_md": str(industry_params.get("clearance_deadline_md") or "12-31"),
        "ccer_ratio": float(acc.get("ccer_max_ratio") or compliance_cfg.get("ccer_max_ratio") or 0.05),
        "fee_rate": float(
            cost_cfg.get("listing_fee_rate")
            if cost_cfg.get("listing_fee_rate") is not None
            else (cost_cfg.get("trade_fee_rate") or 0.0)
        ),
        "price_low_pct": compliance_cfg.get("price_low_percentile"),
        "price_mid_pct": compliance_cfg.get("price_mid_percentile"),
        # 交易粒度约束：简报里「一批买多少」必须落在单笔限额与市场承接量之内
        "single_trade_limit": float(getattr(ent, "single_trade_limit", 0) or 0),
        "large_split_threshold": float(
            compliance_cfg.get("large_trade_split_threshold") or 5.0
        ),
    }


def _deadline_info(
    md: str, today: date | None = None, compliance_year: int | None = None
) -> dict[str, Any]:
    """把「12-31」这类月日口径换算成清缴截止日与剩余天数。

    `compliance_year` 给出时，截止日固定落在该履约年度，不再向明年顺延：
    2027 年度的报告写「清缴截止 2026-12-31、剩余 58 天」是把履约年度和
    自然年混为一谈，读者会据此排错节奏。不传时保持历史行为（当年或次年
    最近的一个 12-31），旧调用方不受影响。
    """
    today = today or date.today()
    try:
        month, day = (int(x) for x in str(md).replace("/", "-").split("-")[:2])
        if compliance_year:
            deadline = date(int(compliance_year), month, day)
        else:
            deadline = date(today.year, month, day)
            if deadline < today:
                deadline = date(today.year + 1, month, day)
    except Exception:
        return {}
    return {
        "deadline": deadline.isoformat(),
        "days_left": (deadline - today).days,
        "overdue": deadline < today,
    }


def _deadline_text(info: dict[str, Any]) -> str:
    """清缴截止的统一展示口径，避免「剩余 -12 天」这类负数出现在正文。"""
    if not info:
        return "—"
    days = info.get("days_left")
    if days is None:
        return f"{info.get('deadline')}"
    if days < 0:
        return f"{info.get('deadline')}（已过期 {abs(int(days))} 天）"
    return f"{info.get('deadline')}（剩余 {int(days)} 天）"


# ---------- 底稿 ----------


async def build_market_factsheet(
    db: Any,
    user_id: str,
    *,
    enterprise_id: str = "",
    compliance_year: int = 0,
    forecast_method: str = "linear",
    on_progress: ProgressFn | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> dict[str, Any]:
    """组装市场底稿：行情 → CCER → 预测 → 企业仓位 → 周期 → 政策资讯。"""

    def prog(p: int, msg: str) -> None:
        if on_progress:
            on_progress(p, msg)

    year = int(compliance_year or datetime.now().year)

    prog(10, "正在拉取上海环交所 CEA 日行情…")
    rows = _load_cea_daily()
    win = _window_stats(rows[-window_days:]) if rows else {}
    prev_rows = rows[-window_days * 2: -window_days] if len(rows) >= window_days * 2 else []
    prev = _window_stats(prev_rows) if prev_rows else {}

    prog(26, "正在计算区间统计与月度走势…")
    months_all = _monthly_rows(rows, limit=0)
    months = months_all[-6:]
    current = win.get("last")

    prog(38, "正在拉取 CCER 近期成交…")
    ccer = await _load_ccer()

    prog(48, "正在计算价格预测…")
    from .price_forecast import forecast_cea_to_year_end, normalize_forecast_method

    fc: dict[str, Any] = {}
    if rows:
        try:
            fc = forecast_cea_to_year_end(rows, method=forecast_method)
        except Exception as exc:  # noqa: BLE001
            logger.warning("market brief forecast failed: %s", exc)
    fc_summary = (fc.get("summary") or {}) if fc.get("ok") else {}
    fc_method_key = normalize_forecast_method(fc_summary.get("method") or forecast_method)

    prog(56, "正在读取企业台账与履约缺口…")
    ent_pack: dict[str, Any] = {}
    if enterprise_id:
        try:
            ent_pack = _enterprise_pack(db, user_id, enterprise_id, year)
        except Exception as exc:  # noqa: BLE001 —— 台账异常降级为纯市场简报
            logger.warning("market brief enterprise pack failed: %s", exc)
            ent_pack = {}
        if not ent_pack:
            prog(58, "未取到企业台账，本次仅输出市场层面…")

    prog(60, "正在判定价格位置与交易窗口…")
    from .market_cycle import judge_market_cycle

    cycle: dict[str, Any] = {}
    if months_all:
        try:
            _gap_side = _f((ent_pack.get("accounting") or {}).get("compliance_gap"))
            res = judge_market_cycle(
                [m["avg"] for m in months_all],
                current,
                ccer.get("close") if ccer else None,
                side=(
                    "gap"
                    if _gap_side is not None and _gap_side > 0
                    else ("surplus" if _gap_side is not None and _gap_side < 0 else None)
                ),
                low_percentile=float(ent_pack.get("price_low_pct") or 0.30),
                mid_percentile=float(ent_pack.get("price_mid_pct") or 0.70),
            )
            cycle = {
                "price_band": getattr(res, "price_band", None),
                "time_window": getattr(res, "time_window", None),
                "action_tag": getattr(res, "action_tag", None),
                "rationale": getattr(res, "rationale", None),
                "spread": getattr(res, "cea_ccer_spread", None),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("market brief cycle failed: %s", exc)

    percentile = _percentile_of([m["avg"] for m in months_all], current)

    industry = str((ent_pack.get("enterprise") or {}).get("industry") or "")
    from .labels import industry_zh

    industry_label = industry_zh(industry) if industry else "碳市场"

    prog(62, "正在检索近期政策与行业资讯…")
    from .policy_research import research_carbon_market_news

    try:
        policy = await research_carbon_market_news(
            db,
            industry_label=industry_label,
            compliance_year=year,
            industry=industry,
            max_items=12,
            read_full=6,
            social_max=6,
            official_max=6,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("market brief policy research failed: %s", exc)
        policy = {"ok": False, "summary_md": "本次未获取到。", "sources": []}

    prog(70, "市场底稿已就绪…")

    factsheet_md, sources_md = _render_factsheet(
        year=year,
        win=win,
        prev=prev,
        months=months,
        month_count=len(months_all),
        percentile=percentile,
        ccer=ccer,
        fc_summary=fc_summary,
        fc_method_key=fc_method_key,
        cycle=cycle,
        ent_pack=ent_pack,
        policy=policy,
        industry_label=industry_label,
        window_days=window_days,
    )

    return {
        "window": win,
        "months": months,
        "ccer": ccer,
        "forecast_summary": fc_summary,
        "cycle": cycle,
        "enterprise": ent_pack.get("enterprise"),
        "accounting": ent_pack.get("accounting") or {},
        "policy": policy,
        "sources_md": sources_md,
        "factsheet_md": factsheet_md,
    }


# ---------- 底稿渲染 ----------


def _render_factsheet(
    *,
    year: int,
    win: dict[str, Any],
    prev: dict[str, Any],
    months: list[dict[str, Any]],
    month_count: int,
    percentile: float | None,
    ccer: dict[str, Any],
    fc_summary: dict[str, Any],
    fc_method_key: str,
    cycle: dict[str, Any],
    ent_pack: dict[str, Any],
    policy: dict[str, Any],
    industry_label: str,
    window_days: int,
) -> tuple[str, str]:
    from .labels import (
        ACTION_TAG_LABELS,
        FORECAST_METHOD_LABELS,
        PRICE_BAND_LABELS,
        TIME_WINDOW_LABELS,
        plan_action_zh,
        zh,
    )
    from .policy_research import _sources_md

    p: list[str] = []
    ent = ent_pack.get("enterprise") or {}

    # 一、行情
    if win:
        p.append("## 市场行情（CEA，单位 元/吨）\n\n")
        p.append(
            f"- 区间：{win.get('start')} 至 {win.get('end')}，共 {win.get('days')} 个交易日"
            f"（近 {window_days} 个交易日口径）\n\n"
        )
        p.append("| 指标 | 数值 |\n|---|---:|\n")
        p.append(f"| 期末收盘价 | {_price(win.get('last'))} |\n")
        p.append(f"| 期间涨跌幅 | {_pct_text(win.get('change_pct'))} |\n")
        p.append(
            f"| 区间最高 / 最低 | {_price(win.get('high'))} / {_price(win.get('low'))} |\n"
        )
        p.append(f"| 日均收盘价 | {_price(win.get('avg'))} |\n")
        if win.get("volume_total") is not None:
            p.append(f"| 区间成交量合计（万吨） | {_wan(win.get('volume_total'))} |\n")
        if win.get("volume_avg") is not None:
            p.append(f"| 日均成交量（万吨） | {_wan(win.get('volume_avg'))} |\n")
        if prev:
            p.append(
                f"| 上一区间（{prev.get('start')} 至 {prev.get('end')}）涨跌幅 "
                f"| {_pct_text(prev.get('change_pct'))} |\n"
            )
    else:
        p.append("## 市场行情（CEA）\n\n本次未获取到 CEA 日行情。\n")

    if months:
        p.append("\n### 近 6 个月月度走势\n\n")
        p.append("| 月份 | 日均价 | 最高 | 最低 | 月末收盘 | 成交(万吨) |\n")
        p.append("|---|---:|---:|---:|---:|---:|\n")
        for m in months:
            p.append(
                f"| {m['ym']} | {_price(m['avg'])} | {_price(m['high'])} | "
                f"{_price(m['low'])} | {_price(m['close'])} | "
                f"{_wan(m['volume_total']) if m.get('volume_total') is not None else '—'} |\n"
            )

    # 二、CCER
    p.append("\n## CCER 与替代空间\n\n")
    if ccer:
        spread = None
        if win.get("last") is not None and ccer.get("close") is not None:
            spread = float(win["last"]) - float(ccer["close"])
        p.append(f"- 最新成交均价：{_price(ccer.get('close'))} 元/吨（{ccer.get('date')}）\n")
        if ccer.get("avg5") is not None:
            p.append(f"- 近 5 个交易日均价：{_price(ccer.get('avg5'))} 元/吨\n")
        if ccer.get("volume") is not None:
            p.append(f"- 最新成交量：{_wan(ccer.get('volume'))} 万吨\n")
        if spread is not None:
            p.append(
                f"- CEA − CCER 价差：{spread:+.2f} 元/吨"
                f"（{'CCER 更贵，抵销性价比偏低' if spread < 0 else 'CCER 更便宜，抵销更划算'}）\n"
            )
    else:
        p.append("本次未获取到 CCER 成交数据。\n")

    # 三、价格位置
    p.append("\n## 价格位置与预测\n\n")
    if percentile is not None:
        p.append(
            f"- 历史分位：当前价 {_price(win.get('last'))} 元/吨，位于开市以来"
            f" {month_count} 个月月度均价的 {percentile:.0f}% 分位\n"
        )
    if cycle:
        p.append(
            f"- 位置判定：{zh(PRICE_BAND_LABELS, cycle.get('price_band'))}；"
            f"时间窗口：{zh(TIME_WINDOW_LABELS, cycle.get('time_window'))}；"
            f"动作标签：{zh(ACTION_TAG_LABELS, cycle.get('action_tag'))}\n"
        )
        if cycle.get("rationale"):
            p.append(f"- 判定依据：{cycle['rationale']}\n")
        # 动作标签已在取数时按本方方向校正；这里再给出该方向下可执行的动作，
        # 避免正文把市场层面的通用判断写成与本方仓位相反的建议
        _gap = _f((ent_pack.get("accounting") or {}).get("compliance_gap")) or 0.0
        if ent and _gap > 0:
            p.append(
                f"- 本方可用动作：本方为缺口方（{_fmt_wan(_gap)} 万吨），"
                "可执行「自有 CCER 抵销 → 分批买入 CEA」，不存在可出售的盈余\n"
            )
        elif ent and _gap < 0:
            p.append(
                f"- 本方可用动作：本方为盈余方（{_fmt_wan(abs(_gap))} 万吨），"
                "可执行「分批卖出 CEA」或按现行政策全额结转，无需采购\n"
            )
    if fc_summary:
        up = _pct(fc_summary.get("last_close"), fc_summary.get("year_end_price"))
        p.append(
            f"- 预测（现行模型：{zh(FORECAST_METHOD_LABELS, fc_method_key)}）："
            f"现价锚点 {_price(fc_summary.get('last_close'))}，"
            f"预测年底 {_price(fc_summary.get('year_end_price'))}"
            f"（区间 {_price(fc_summary.get('year_end_low'))}–"
            f"{_price(fc_summary.get('year_end_high'))}，{_pct_text(up)}）\n"
            f"- 年内预测高点 {_price(fc_summary.get('peak_price'))}"
            f"（{fc_summary.get('peak_date') or '—'}）；"
            f"预测低点 {_price(fc_summary.get('trough_price'))}"
            f"（{fc_summary.get('trough_date') or '—'}）\n"
        )

    # 四、交易窗口
    deadline = (
        _deadline_info(ent_pack.get("clearance_md") or "12-31", compliance_year=year)
        if ent_pack
        else {}
    )
    p.append("\n## 交易窗口\n\n")
    if deadline:
        p.append(f"- 清缴截止：{_deadline_text(deadline)}\n")
    if ent_pack:
        p.append(
            f"- 价格分档口径：低于 {ent_pack.get('price_low_pct')} 分位视为低位、"
            f"高于 {ent_pack.get('price_mid_pct')} 分位视为高位（当前系统配置）\n"
        )
        # 分批约束：把「一批能买多少」算清楚，正文不得再给超出承接量的单批数量。
        # 单批上限只解决「砸盘」问题，还要过「时间可行性」：缺口远大于日均成交时，
        # 按小单拆批在清缴前根本做不完，此时必须给出时间约束下的单批规模。
        _daily_wan = _f(win.get("volume_avg"))
        _daily_wan = _daily_wan / 10000.0 if _daily_wan else None
        _total_wan = _f(win.get("volume_total"))
        _total_wan = _total_wan / 10000.0 if _total_wan else None
        _single = _f(ent_pack.get("single_trade_limit")) or 0.0
        _split = _f(ent_pack.get("large_split_threshold")) or 0.0
        if _single > 0:
            p.append(f"- 单笔交易限额：{_fmt_wan(_single)} 万吨（企业台账设定）\n")
        if _split > 0:
            p.append(f"- 大额拆分阈值：{_fmt_wan(_split)} 万吨（超过即建议拆分）\n")
        _need = abs(_f((ent_pack.get("accounting") or {}).get("compliance_gap")) or 0.0)
        # 单批上限：台账单笔限额优先；未设限额时按日均成交量的 20% 估算流动性冲击
        _cap = _daily_wan * 0.2 if _daily_wan else None
        if _single > 0:
            _cap = min(_cap, _single) if _cap else _single
        if _cap:
            if _daily_wan and _single > 0:
                basis = f"取「单笔限额」与「日均成交 {_fmt_wan(_daily_wan)} 万吨的 20%」的较小值"
            elif _daily_wan:
                basis = (
                    f"日均成交 {_fmt_wan(_daily_wan)} 万吨的 20%（流动性经验口径，"
                    "台账未设单笔限额）"
                )
            else:
                basis = "企业台账单笔交易限额"
            p.append(f"- 建议单批上限：{_fmt_wan(_cap)} 万吨（{basis}）\n")
            if _need > 0:
                import math

                _batches = max(1, math.ceil(_need / _cap))
                p.append(
                    f"- 分批节奏：需处置 {_fmt_wan(_need)} 万吨，按该上限需拆 {_batches} 批，"
                    f"每批约 {_fmt_wan(_need / _batches)} 万吨\n"
                )
                _trade_days = None
                if deadline and deadline.get("days_left") is not None:
                    _trade_days = max(1, int(deadline["days_left"] * 5 / 7))
                if _trade_days and _batches > _trade_days:
                    _min_batch = _need / _trade_days
                    _surge = (
                        f"，相当于日均成交的 {_min_batch / _daily_wan * 100:.0f}%"
                        if _daily_wan
                        else ""
                    )
                    _over_limit = (
                        f"，即突破台账单笔限额 {_fmt_wan(_single)} 万吨，"
                        "需按大宗交易单笔报备或内部特批"
                        if _single > 0 and _min_batch > _single
                        else ""
                    )
                    p.append(
                        f"- 时间约束：距清缴 {deadline.get('days_left')} 天约 {_trade_days} 个交易日，"
                        f"按上述单批上限需 {_batches} 批，场内竞价承接量与时间都不够；"
                        f"若要按期清缴，单批须提高到约 {_fmt_wan(_min_batch)} 万吨{_surge}"
                        f"{_over_limit}，并走大宗/协议转让或分日挂单撮合\n"
                    )
                if _total_wan:
                    p.append(
                        f"- 流动性压力：需处置量相当于近 {win.get('days')} 个交易日"
                        f"成交合计 {_fmt_wan(_total_wan)} 万吨的 "
                        f"{_need / _total_wan * 100:.0f}%\n"
                    )

    # 五、我方仓位
    acc = ent_pack.get("accounting") or {}
    if ent:
        gap = _f(acc.get("compliance_gap")) or 0.0
        # 台账 annual_budget_cap 单位是「元」，正文按「万元」展示；
        # 采购成本 cost_now 由「万吨 × 元/吨」得到，本身就是万元，须先对齐再比较
        _budget_raw = _f(ent.get("annual_budget_cap"))
        budget = _budget_raw / 10000.0 if _budget_raw is not None else None
        fee = _f(ent_pack.get("fee_rate")) or 0.0
        px_now = _f(win.get("last"))
        px_fc = _f(fc_summary.get("year_end_price"))

        p.append(f"\n## 我方仓位（{ent.get('name') or '—'}，{industry_label}）\n\n")
        p.append("| 指标 | 数值 |\n|---|---:|\n")
        p.append(f"| 核查排放（万吨） | {_fmt_wan(acc.get('verified_emission'))} |\n")
        p.append(f"| 可用 CEA（万吨） | {_fmt_wan(acc.get('free_cea_quota'))} |\n")
        p.append(f"| CCER 抵销上限（万吨） | {_fmt_wan(acc.get('ccer_cap'))} |\n")
        p.append(f"| 本履约可动用 CCER（万吨） | {_fmt_wan(acc.get('own_ccer_usable'))} |\n")
        p.append(
            f"| 履约缺口（已扣 CCER，万吨） | {_fmt_wan(acc.get('compliance_gap'))}"
            f"{'（盈余）' if gap < 0 else ''} |\n"
        )
        carry = ent_pack.get("carry") or {}
        if str(carry.get("policy") or "") == "unlimited":
            p.append("| 结转限制 | 无（现行政策取消配额结转数量限制，盈余可全额结转） |\n")
        elif carry.get("max_carry") is not None:
            p.append(f"| 可结转留存上限（万吨） | {_fmt_wan(carry.get('max_carry'))} |\n")
        if budget is not None:
            p.append(f"| 年度预算上限（万元） | {budget:.2f} |\n")

        fee_note = f"（已含单边手续费 {fee * 100:.2f}%）" if fee > 0 else ""
        if gap > 0 and px_now:
            cost_now = gap * px_now * (1 + fee)
            p.append("\n### 缺口采购成本测算\n\n")
            p.append(f"- 按现价 {_price(px_now)} 元/吨：约 {cost_now:.0f} 万元{fee_note}\n")
            if px_fc:
                p.append(
                    f"- 按预测年底价 {_price(px_fc)} 元/吨：约 {gap * px_fc * (1 + fee):.0f} 万元\n"
                )
            if budget is not None and budget > 0:
                room = budget - cost_now
                p.append(
                    f"- 与年度预算上限比较：{'可用额度剩余' if room >= 0 else '超出预算'}"
                    f" {abs(room):.0f} 万元\n"
                )
        elif gap < 0 and px_now:
            p.append("\n### 盈余处置测算\n\n")
            p.append(
                f"- 按现价 {_price(px_now)} 元/吨全部出售：约回收 "
                f"{abs(gap) * px_now * (1 - fee):.0f} 万元{fee_note}\n"
            )

        plan = ent_pack.get("core_plan") or {}
        if plan:
            p.append(f"\n### 平衡画像方案动作（{plan.get('title') or '—'}）\n\n")
            acts = ent_pack.get("plan_actions") or []
            if acts:
                p.append("| 动作 | 数量（万吨） | 说明 |\n|---|---:|---|\n")
                for a in acts:
                    p.append(
                        f"| {plan_action_zh(a.get('action'))} | {_fmt_wan(a.get('qty'))} | "
                        f"{_clip(a.get('note'), 110)} |\n"
                    )
            else:
                p.append("本期无建议动作。\n")
            if ent_pack.get("plan_blocked") and ent_pack.get("plan_issues"):
                p.append(
                    "\n- 方案约束：" + "；".join(str(x) for x in ent_pack["plan_issues"]) + "\n"
                )

    # 六、政策
    p.append("\n## 政策与资讯\n\n")
    summary = str((policy or {}).get("summary_md") or "本次未获取到。").strip()
    if len(summary) > 3000:
        summary = summary[:2990] + "…"
    p.append(summary + "\n")

    # 来源：政策/社媒 + 行情固定源
    all_sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for src in (policy or {}).get("sources") or []:
        if not isinstance(src, dict):
            continue
        url = str(src.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        all_sources.append(src)

    from .market_sync import CCER_SOURCE_PAGE, CNEEEX_DAILY_URL, PRIMARY_MARKET_URL

    for platform, title, url in (
        ("上海环境能源交易所", "全国碳市场日行情（CEA）", CNEEEX_DAILY_URL),
        ("全国温室气体自愿减排交易市场", "CCER 每日行情", CCER_SOURCE_PAGE),
        ("中国碳市场网", "全国碳市场行情", PRIMARY_MARKET_URL),
    ):
        if url and url not in seen:
            seen.add(url)
            all_sources.append({"platform": platform, "title": title, "url": url})

    sources_md = _sources_md(all_sources, limit=20, start=1)
    return "".join(p).strip() + "\n", sources_md


# ---------- 提示词 ----------


def market_brief_system_prompt(*, subject: str, year: int) -> str:
    """碳交易简报专用系统提示词。

    与履约报告的关键差异：不写减排路径、不做三档策略对比、不评价预测算法，
    操作建议按「本周 / 本月 / 清缴前」三段给，且必须带价格触发条件。
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    heading = report_heading_of("market_brief")
    return (
        f"你是全国碳市场行情分析师，正在为「{subject}」撰写 {year} 年{heading}。\n"
        f"生成时间：{now}\n"
        "定位：给碳资产管理员看的决策简报，只回答三个问题——现在什么价、为什么、接下来怎么做。\n"
        "硬约束：\n"
        "1. 只使用用户消息中的市场底稿数字，禁止编造价格、成交量、涨跌幅、政策条文或排放量；"
        "底稿没有的写「本次未获取到」。引用联网材料时用正文标号 [1][2]…，与文末「信息来源」对应。\n"
        "2. 价格统一用元/吨，成交量统一用万吨，沿用底稿口径，不得自行换算或改变数量级；"
        "底稿给的是月度均价分位，不要改写成日度分位。\n"
        "3. 不写减排路径，不做保守/平衡/进取三档策略对比；操作建议只按「本周 / 本月 / 清缴前」"
        "三个时间档组织。\n"
        "4. 不评价预测算法优劣，只写「按现行预测模型」并给出中枢与区间。\n"
        "5. 全文简体中文；除 CEA、CCER 等专有名词外不出现英文单词"
        "（禁止 mid、buy、hold、Aggressive、price_band、action_tag 等）。\n"
        "6. 严禁元话语与过程性表述：不得出现「用户要求」「系统提示」「硬约束」「事实底稿」"
        "「底稿第×章」「以下是根据」等字样，也不要解释本章写作目的，直接给正文。\n"
        "7. 必须包含以下二级标题，顺序固定，不得增删或改名：\n"
        f"{_report_header(subject, year, 'market_brief')}\n\n"
        "## 本期要点\n"
        "## 行情回顾\n"
        "## 价格位置与展望\n"
        "## 交易窗口判断\n"
        "## 政策与资讯\n"
        "## 我方仓位\n"
        "## 操作建议\n"
        "## 风险提示\n"
        "## 信息来源\n"
        "底稿未提供企业仓位数据时，省略「## 我方仓位」。\n"
        "8. 「本期要点」3–5 条，每条一句话且至少含一个具体数字，先给结论、后给依据。\n"
        "9. 「行情回顾」必须用表格呈现关键指标，正文只做解读，不重复罗列数字。\n"
        "10. 「政策与资讯」只写与 CEA/CCER 价格或本行业履约直接相关的 3–5 条，"
        "每条给「要点 + 对本企业的含义」；与碳无关的商品价格、股市行情、公司经营类资讯不要写入。\n"
        "11. 「操作建议」每条都要带触发条件（例如「CEA 回落至 92 元/吨以下」）"
        "与数量口径（万吨）；不要写「视情况而定」这类无法执行的建议。"
        "若底稿显示方案因预算约束被阻断，须直接点明资金缺口，并给出分批或先小后大的替代节奏。\n"
        "11.1 单批数量硬约束：默认采用底稿「建议单批上限」，需要处置的数量大于该上限时"
        "必须写成拆批方案（批次数、每批吨数、每批间隔），严禁把总量当作单批数量。"
        "但若底稿给出「时间约束」行（按单批上限在清缴前做不完），则一律采用该行给出的"
        "单批规模，并写明走大宗/协议转让，不得仍按小单拆批而导致逾期。"
        "凡底稿给出「流动性压力」，须在风险提示中引用该比例。\n"
        "12. 篇幅 1500–2500 字；每段不超过 4 行；表格与要点列表优先于长段落。\n"
        "13. 「信息来源」放在全文最后，原样使用用户消息中带 http(s) 链接的编号列表，"
        "禁止改写为「底稿第×章」或省略网址；无来源时写「本次无外部可核验链接来源」。"
        "文末附一句「本简报不构成投资建议」。\n"
    )


BRIEF_USER_INSTRUCTION = (
    "输出 Markdown 正文（可含「信息来源」占位，系统会替换为真实链接），"
    "无需任何说明性前缀。全文按决策简报组织，不要写成论文。"
)

BRIEF_FALLBACK_HINT = "请先核对底稿中的行情与缺口数字，再决定采购或出售节奏。"


# ---------- 章节兜底 ----------


def _ensure_risk_section(text: str, pack: dict[str, Any]) -> str:
    """模型偶尔会漏写「风险提示」章节：按底稿数字补一段确定性的风险提示。

    只使用底稿里已有的价格、预测与缺口，不引入任何新事实。
    """
    body = text or ""
    if not re.search(r"^##\s*风险提示", body, flags=re.M):
        win = pack.get("window") or {}
        fc = pack.get("forecast_summary") or {}
        acc = pack.get("accounting") or {}
        gap = _f(acc.get("compliance_gap")) or 0.0

        lines = ["## 风险提示", ""]
        if win.get("last") is not None:
            lines.append(
                f"- 价格风险：CEA 现价 {_price(win.get('last'))} 元/吨处于高位区间，"
                "年末集中采购可能推高成交价。"
            )
        if fc.get("year_end_price") is not None:
            lines.append(
                f"- 预测偏差：年底预测 {_price(fc.get('year_end_price'))} 元/吨"
                f"（区间 {_price(fc.get('year_end_low'))}–{_price(fc.get('year_end_high'))}）"
                "为模型外推，实际价格可能超出该区间。"
            )
        if gap > 0:
            lines.append(
                f"- 履约风险：尚余缺口 {_fmt_wan(gap)} 万吨，逾期未清缴将按相关规定处理。"
            )
        lines.append(
            "- 数据口径：公开侧无实时挂单，本简报价格为日均/收盘与预测锚定值，"
            "不代表可成交报价。"
        )
        block = "\n".join(lines) + "\n\n"

        idx = body.find("## 信息来源")
        body = (body[:idx] + block + body[idx:]) if idx >= 0 else (body.rstrip() + "\n\n" + block)

    if "不构成投资建议" not in body[-400:]:
        body = body.rstrip() + "\n\n本简报不构成投资建议。\n"
    return body


# ---------- 入口 ----------


async def run_market_brief_report(
    db: Any,
    report: Any,
    *,
    ctx: dict[str, Any] | None = None,
    on_progress: ProgressFn,
    on_content: ContentFn,
) -> str:
    """碳交易简报完整流水线：取数 → 市场底稿 → 流式撰写。"""
    ctx = ctx if isinstance(ctx, dict) else _parse_ai_context(getattr(report, "ai_context", "") or "")
    year = int(ctx.get("compliance_year") or getattr(report, "target_year", 0) or datetime.now().year)
    method = str(ctx.get("forecast_method") or "linear")
    enterprise_id = str(ctx.get("enterprise_id") or "").strip()

    pack = await build_market_factsheet(
        db,
        report.user_id,
        enterprise_id=enterprise_id,
        compliance_year=year,
        forecast_method=method,
        on_progress=on_progress,
    )

    on_progress(74, "市场底稿已就绪，正在撰写简报正文…")
    on_content(f"{_report_header(report.subject, year, 'market_brief')}\n\n" + pack["factsheet_md"])

    text = await synthesize_compliance_analysis_stream(
        subject=report.subject,
        compliance_year=year,
        factsheet_md=pack["factsheet_md"],
        sources_md=str(pack.get("sources_md") or ""),
        report_type="market_brief",
        on_progress=on_progress,
        on_content=on_content,
        system_prompt=market_brief_system_prompt(subject=report.subject, year=year),
        user_instruction=BRIEF_USER_INSTRUCTION,
        fallback_hint=BRIEF_FALLBACK_HINT,
        fallback_conclusion="本期要点",
        fallback_data_heading="市场数据",
    )

    # 章节兜底：模型漏写「风险提示」时按底稿数字补齐，保证简报结构完整
    fixed = _ensure_risk_section(text, pack)
    if fixed != text and on_content:
        on_content(fixed)
    return fixed
