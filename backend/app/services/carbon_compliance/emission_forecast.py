# -*- coding: utf-8 -*-
"""排放预测：以台账已有月份为基准，推算同一履约年度剩余月份的排放。

设计取舍（改动前请先读这一段）：

- **不做黑盒拟合**。台账里通常只有 3~8 个月的数据，任何时序模型
  （ARIMA / Prophet / TCN）在这个样本量下都只会给出带假精度的数字，
  报告里无法解释。这里用「已填月份月均 → 按历史同月系数分摊到剩余月份」的
  确定性算法，每一步都能写成一句话，读者可以自己复核。
- **只用更早的年度做参考**。目标年度之后的数据（例如拿 2027 年的实际值去预测
  2026 年）在业务上是「未来信息」，一旦引入，预测就不可解释，也会让同一份历史
  预测随新数据不断变化。
- **台账优先于历史**。同一履约年度已填的月份就是最硬的信息，先取它的月均；
  没有月度数据时才退到年度值 ÷ 12，再退到历史年度。
- **季节形状要求近乎整年**。参考年度覆盖 ≥ 9 个月才算能给出季节形状，否则一律
  等分——用上半年 6 个月算出来的「季节系数」其实是「上半年偏低」这种伪形状，
  摊到下半年会把预测整体带偏。
"""

from __future__ import annotations

from datetime import date
from typing import Any

MONTHS: tuple[int, ...] = tuple(range(1, 13))

# 参考年度覆盖多少个月，才认为它能代表季节形状（少于这个数按等分处理）
SEASON_MIN_MONTHS = 9
# 季节系数 / 趋势系数的截断区间：超出 0.6~1.6 基本都是样本噪声
FACTOR_MIN = 0.6
FACTOR_MAX = 1.6
# 趋势需要的最少重合月份：单月重合算出来的是「当月波动」，不是趋势
TREND_MIN_MONTHS = 2


def _clamp(value: float, lo: float = FACTOR_MIN, hi: float = FACTOR_MAX) -> float:
    return max(lo, min(hi, value))


def _mean(values: Any) -> float:
    vals = [float(v) for v in values if v is not None]
    return sum(vals) / len(vals) if vals else 0.0


def _month_passed(year: int, month: int, today: date) -> bool:
    """该月相对今天是否已经过完。用于提示「月份已过但台账没填」。"""
    if year < today.year:
        return True
    if year > today.year:
        return False
    return month < today.month


def _clean_months(raw: Any) -> dict[int, float]:
    out: dict[int, float] = {}
    for m, v in (raw or {}).items():
        try:
            mi = int(m)
        except (TypeError, ValueError):
            continue
        if mi in MONTHS and v is not None:
            out[mi] = float(v)
    return out


def _year_level(h: dict) -> tuple[float, bool]:
    """历史年度的（月均水平, 是否覆盖整年）。

    年度值并不总是「全年」口径：台账里只要录过月度，年度值就等于月度合计，
    此时上半年填了 6 个月的年份，其「年度值 728」其实只是上半年合计。
    直接拿它除以 12 会把水平压到实际的一半，所以先判断年度值是不是全年的。
    """
    months: dict[int, float] = h.get("months") or {}
    annual = h.get("annual")
    if not months:
        return ((annual / 12.0) if annual else 0.0), True
    total = sum(months.values())
    mean = _mean(months.values())
    if len(months) >= SEASON_MIN_MONTHS:
        # 覆盖近乎整年：年度值若与月度合计不一致，说明年度值另有来源（核定/核查），更可信
        if annual and abs(annual - total) > 1e-6:
            return annual / 12.0, True
        return mean, True
    # 覆盖不足一年：年度值明显大于已填月份之和，才认为它是全年口径
    if annual and annual > total * 1.05:
        return annual / 12.0, False
    return mean, False


def _normalize_plan_months(raw: Any) -> dict[int, float]:
    """生产计划只保留 1~12 月、数值 > 0 的月份；0/空的月份视为「未单独排产」。"""
    out: dict[int, float] = {}
    if not isinstance(raw, dict):
        return out
    for m, v in raw.items():
        try:
            mi = int(str(m).strip())
        except (TypeError, ValueError):
            continue
        if mi not in MONTHS or v is None or v == "":
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv > 0:
            out[mi] = fv
    return out


def _plan_targets(
    plan_months: Any, capacity_output: Any
) -> tuple[dict[int, float], float, list[str]]:
    """把「年计划产量 + 部分月份排产」补全成 12 个月的产量，返回 (月产量, 年产量, 提示)。

    规则（每一步都写在界面上，用户能自己复核）：
    - 只填了部分月份：剩余产量 = 年计划产量 − 已排产月份合计，均分到没填的月份；
    - 只填了年计划产量：12 个月等分；
    - 只填了月度排产、没填年产量：年产量取已排产月份的合计，未排产月份按 0；
    - 已排产合计超过年计划产量：以排产为准（排产是企业自己填的），并给出提示。
    """
    filled = _normalize_plan_months(plan_months)
    cap = float(capacity_output or 0)
    warns: list[str] = []
    if filled:
        scheduled = sum(filled.values())
        mean = scheduled / len(filled)
        if cap <= 0:
            # 只填了月度排产：未排产月份按已排产月均值延续，而不是按 0——
            # 用户往往只填前几个月做试探，按 0 会把全年直接砍掉一半
            for m in MONTHS:
                filled.setdefault(m, mean)
            cap = round(sum(filled.values()), 4)
            warns.append(
                "未填年计划产量，按已排产月份的月均 {:.2f} 万吨延续未排产月份，全年 {:.2f} 万吨。".format(mean, cap)
            )
        elif scheduled > cap * 1.0001:
            # 排产合计已超年计划：以排产为准（企业自己填的），未排产月份按月均延续
            for m in MONTHS:
                filled.setdefault(m, mean)
            cap = round(sum(filled.values()), 4)
            warns.append(
                "月度排产合计 {:.2f} 万吨已超过年计划产量，按排产原值测算，未排产月份按月均 {:.2f} 万吨延续，"
                "全年 {:.2f} 万吨，请确认计划口径。".format(scheduled, mean, cap)
            )
        else:
            rest_months = [m for m in MONTHS if m not in filled]
            if rest_months:
                each = (cap - scheduled) / len(rest_months)
                for m in rest_months:
                    filled[m] = each
    elif cap > 0:
        each = cap / 12.0
        filled = {m: each for m in MONTHS}
    else:
        return {}, 0.0, warns
    return {m: round(v, 4) for m, v in filled.items()}, round(cap, 4), warns


def _planned_forecast(
    *,
    year: int,
    actual: dict[int, float],
    plan_months: Any,
    capacity_output: Any,
    intensity: Any,
    target_annual: float | None,
    closed: bool,
    today: date,
) -> dict | None:
    """按「生产计划 × 排放强度」逐月出数；凑不齐计划或强度时返回 None，退回历史外推。

    台账已填月份永远取实际值——计划是「打算排多少」，台账是「实际排了多少」，
    两者冲突时以台账为准，计划只负责补未来月份。
    """
    plan, cap, warns = _plan_targets(plan_months, capacity_output)
    if not plan:
        return None
    inten = float(intensity or 0)
    if inten <= 0:
        if cap > 0 and target_annual and float(target_annual) > 0:
            inten = float(target_annual) / cap
            warns.append(
                "排放强度未设置，按台账年度值 {:.2f} 万吨 ÷ 年计划产量 {:.2f} 万吨 = {:.3f} 吨/吨 反推。".format(
                    float(target_annual), cap, inten
                )
            )
        else:
            return None

    rows: list[dict] = []
    for m in MONTHS:
        passed = _month_passed(year, m, today)
        if m in actual:
            rows.append({
                "month": m,
                "value": round(actual[m], 2),
                "source": "ledger",
                "factor": 1.0,
                "passed": passed,
                "overdue": False,
            })
        else:
            planned_value = plan.get(m, 0.0) * inten
            rows.append({
                "month": m,
                "value": round(planned_value, 2),
                # 沿用 ledger/forecast 两种来源：计划推算也是推算，界面标「按计划」
                "source": "forecast",
                "factor": round(plan.get(m, 0.0), 4),
                "passed": passed,
                "overdue": passed and not closed,
            })

    # 与均摊算法同样的残差归位：把逐月四舍五入的差额补到最后一个未填月份，
    # 保证「12 个月加总」与「计划产量 × 强度」严格一致
    raw_total = sum(
        actual.get(r["month"]) if r["source"] == "ledger" else plan.get(r["month"], 0.0) * inten
        for r in rows
    )
    rounded_total = round(sum(r["value"] for r in rows), 2)
    diff = round(round(raw_total, 2) - rounded_total, 2)
    if abs(diff) >= 0.01:
        for r in reversed(rows):
            if r["source"] != "ledger":
                r["value"] = round(r["value"] + diff, 2)
                break

    actual_total = round(sum(actual.values()), 2)
    rest_total = round(sum(r["value"] for r in rows if r["source"] != "ledger"), 2)
    total = round(actual_total + rest_total, 2)
    overdue_months = [r["month"] for r in rows if r["overdue"]]
    planned_total = round(cap * inten, 2)
    if actual:
        basis_text = (
            "按生产计划测算：年计划产量 {:.2f} 万吨 × 排放强度 {:.3f} 吨/吨 = {:.2f} 万吨；"
            "台账已填 {} 个月取实际值，其余月份按排产分配。"
        ).format(cap, inten, planned_total, len(actual))
    else:
        basis_text = "按生产计划测算：年计划产量 {:.2f} 万吨 × 排放强度 {:.3f} 吨/吨 = {:.2f} 万吨，逐月按排产分配。".format(
            cap, inten, planned_total
        )

    if closed:
        warns.append("{} 年度已结束，测算只用于补全空白月份，建议直接在排放台账录入实际值。".format(year))
    if overdue_months:
        warns.append(
            "{} 月已过但台账未填，当前按计划排产值代位，补录实际值后请重新测算。".format(
                "、".join(str(m) for m in overdue_months)
            )
        )
    if total and target_annual and abs(total - float(target_annual)) / float(target_annual) >= 0.2:
        # 只在与「全年口径」的台账值比较时才有意义：如果台账只填了几个月，
        # 年度值本身只是这几个月的合计，拿它当分母会报出 +500% 这种无意义的偏差
        annual_is_full = (not actual) or (float(target_annual) > actual_total * 1.05) or len(actual) >= 12
        if annual_is_full:
            warns.append(
                "按计划测算得 {:.2f} 万吨，与台账年度值 {:.2f} 万吨相差 {:+.1%}，请确认计划产量或强度是否已更新。".format(
                    total, float(target_annual), (total - float(target_annual)) / float(target_annual)
                )
            )

    rest_months = 12 - len(actual)
    return {
        "year": year,
        "basis": "planned",
        "basis_text": basis_text,
        "months": rows,
        "filled_months": len(actual),
        "base_monthly": round(rest_total / rest_months, 2) if rest_months else 0.0,
        "trend_factor": 1.0,
        "trend_months": [],
        "seasonal": False,
        "ref_year": None,
        "actual_total": actual_total,
        "rest_total": rest_total,
        "total": total,
        "overdue_months": overdue_months,
        "warnings": warns,
        # 计划口径的附加信息：界面展示「计划产量 / 强度 / 逐月排产」，报告也能引用
        "plan_output": cap,
        "plan_intensity": round(inten, 4),
        "plan_months": {str(m): round(v, 2) for m, v in plan.items()},
        "plan_total": planned_total,
    }


def build_emission_forecast(
    year: int,
    target_months: dict[int, float] | None = None,
    history: list[dict] | None = None,
    target_annual: float | None = None,
    today: date | None = None,
    plan_months: dict[int, float] | None = None,
    capacity_output: float | None = None,
    intensity: float | None = None,
) -> dict:
    """算出某一履约年度的 12 个月排放：已填月份取台账值，其余按月均推算。

    参数
    ----
    year           目标履约年度
    target_months  该年度台账已填月份 {月: 核查排放}
    history        其它年度 [{"year": 2025, "months": {月: 值}, "annual": 全年值}]
    target_annual  该年度台账的全年值（无月度数据时作为水平基准）
    today          注入「今天」便于测试
    plan_months    生产计划：{月: 计划产量（万吨）}，可只填部分月份
    capacity_output 产能计划：年计划产量（万吨）
    intensity      排放强度（吨 CO2 / 吨产品），缺省时用「台账年度值 ÷ 年计划产量」反推

    生产计划优先：只要「计划产量 + 排放强度」能凑齐，就按排产逐月出数
    （台账已填月份仍取实际值），而不是拿历史均值去平摊——排产本身就是
    企业对这个年度最确定的判断，比任何时序外推都硬。
    """
    today = today or date.today()
    year = int(year or 0)
    actual = _clean_months(target_months)
    # 已结束的年度谈「剩余月份预测」意义有限：那 12 个月都过去了，
    # 该做的是补录实际值，而不是继续外推
    closed = year < today.year

    # ---- 零、生产计划优先 ----
    planned = _planned_forecast(
        year=year,
        actual=actual,
        plan_months=plan_months,
        capacity_output=capacity_output,
        intensity=intensity,
        target_annual=target_annual,
        closed=closed,
        today=today,
    )
    if planned is not None:
        return planned

    # 参考年度：只取目标年度之前的，按年份倒序找到第一个有月度数据的
    prior: list[dict] = []
    for h in history or []:
        try:
            hy = int(h.get("year") or 0)
        except (TypeError, ValueError):
            continue
        if not hy or hy >= year:
            continue
        months = _clean_months(h.get("months"))
        annual = h.get("annual")
        if months or annual:
            prior.append({"year": hy, "months": months, "annual": float(annual) if annual else None})
    prior.sort(key=lambda x: x["year"], reverse=True)

    ref_months: dict | None = next((h for h in prior if h["months"]), None)

    # ---- 一、水平基准：本年度月度 > 本年度年度值 > 历史年度 ----
    base = 0.0
    basis = "none"
    ref_level: dict | None = None
    ref_level_partial = False
    if actual:
        base = _mean(actual.values())
        basis = "ledger_monthly"
    elif target_annual:
        base = float(target_annual) / 12.0
        basis = "ledger_annual"
    else:
        for h in prior:
            level, complete = _year_level(h)
            if level > 0:
                base = level
                ref_level = h
                ref_level_partial = not complete
                basis = "history_annual" if complete else "history_monthly"
                break

    # ---- 二、季节形状：参考年度必须近乎整年 ----
    season: dict[int, float] = {}
    season_ok = bool(ref_months) and len(ref_months["months"]) >= SEASON_MIN_MONTHS
    if season_ok:
        ref_mean = _mean(ref_months["months"].values())
        if ref_mean > 0:
            for m in MONTHS:
                if m in ref_months["months"]:
                    season[m] = _clamp(ref_months["months"][m] / ref_mean)
            season_ok = bool(season)
        else:
            season_ok = False

    # ---- 三、趋势：用「同月重合段」比出今年的量级变化（季节影响被同月抵消）----
    trend = 1.0
    trend_months: list[int] = []
    if actual and ref_months:
        common = sorted(set(actual) & set(ref_months["months"]))
        if len(common) >= TREND_MIN_MONTHS:
            ref_mean_c = _mean(ref_months["months"][m] for m in common)
            if ref_mean_c:
                trend = _clamp(_mean(actual[m] for m in common) / ref_mean_c)
                trend_months = common

    level = base * trend

    # ---- 四、逐月出数 ----
    rows: list[dict] = []
    for m in MONTHS:
        passed = _month_passed(year, m, today)
        if m in actual:
            rows.append({
                "month": m,
                "value": round(actual[m], 2),
                "source": "ledger",
                "factor": 1.0,
                "passed": passed,
                # 已填月份不存在「待补录」问题
                "overdue": False,
            })
        else:
            factor = season.get(m, 1.0)
            rows.append({
                "month": m,
                "value": round(level * factor, 2),
                "source": "forecast",
                "factor": round(factor, 4),
                "passed": passed,
                # 已过去的月份台账还空着：预测值只是代位，补录后应重算
                "overdue": passed and not closed,
            })

    # 逐月四舍五入会留下几分钱级残差（1600/12 → 12 × 133.33 = 1599.96），
    # 补到最后一个预测月，保证「12 个月加起来」与合计严格相等
    raw_total = sum(
        (actual.get(r["month"]) if r["source"] == "ledger" else level * (r["factor"] or 1.0))
        for r in rows
    )
    rounded_total = round(sum(r["value"] for r in rows), 2)
    diff = round(round(raw_total, 2) - rounded_total, 2)
    if abs(diff) >= 0.01:
        for r in reversed(rows):
            if r["source"] == "forecast":
                r["value"] = round(r["value"] + diff, 2)
                break

    actual_total = round(sum(actual.values()), 2)
    rest_total = round(sum(r["value"] for r in rows if r["source"] == "forecast"), 2)
    total = round(actual_total + rest_total, 2)
    overdue_months = [r["month"] for r in rows if r["overdue"]]

    # ---- 五、给人看的一句话依据（界面与报告共用，避免两边口径漂移）----
    basis_text = _basis_text(
        basis=basis,
        base=base,
        trend=trend,
        season_ok=season_ok,
        ref_year=ref_months["year"] if ref_months else (ref_level["year"] if ref_level else None),
        filled=len(actual),
        rest=12 - len(actual),
        target_annual=target_annual,
    )

    warnings: list[str] = []
    # 填了产量计划却没用上：说明缺少排放强度（企业属性没配、该年度也没有台账年度值可以反推），
    # 必须明说，否则用户会以为计划已经参与测算
    if _normalize_plan_months(plan_months) or float(capacity_output or 0) > 0:
        warnings.append(
            "已填产能/生产计划，但缺少排放强度（企业属性未设置，且该年度没有台账年度值可反推），"
            "本次仍按台账与历史外推；补上企业排放强度或台账年度值后即可按计划测算。"
        )
    if basis == "none":
        warnings.append("台账与历史均无可用数据，无法自动测算，只能手工填写全年预测排放。")
    if closed:
        warnings.append(
            "{} 年度已结束，测算只用于补全空白月份，建议直接在排放台账录入实际值。".format(year)
        )
    if overdue_months:
        warnings.append(
            "{} 月已过但台账未填，当前按预测值代位，补录实际值后请重新测算。".format(
                "、".join(str(m) for m in overdue_months)
            )
        )
    if basis in ("ledger_annual", "history_annual"):
        warnings.append("没有月度数据支撑，12 个月按均值等分，季节性差异未体现。")
    if ref_level_partial and ref_level:
        warnings.append(
            "参考年度 {} 只填了 {} 个月，月均取自这几个月，不代表全年水平。".format(
                ref_level["year"], len(ref_level["months"])
            )
        )
    if ref_months and not season_ok and actual and len(ref_months["months"]) < SEASON_MIN_MONTHS:
        warnings.append(
            "参考年度 {} 仅覆盖 {} 个月，不足以判断季节形状，剩余月份按等分推算。".format(
                ref_months["year"], len(ref_months["months"])
            )
        )

    return {
        "year": year,
        "basis": basis,
        "basis_text": basis_text,
        "months": rows,
        "filled_months": len(actual),
        "base_monthly": round(base, 2),
        "trend_factor": round(trend, 4),
        "trend_months": trend_months,
        "seasonal": season_ok,
        "ref_year": ref_months["year"] if ref_months else None,
        "actual_total": actual_total,
        "rest_total": rest_total,
        "total": total,
        "overdue_months": overdue_months,
        "warnings": warnings,
    }


def _basis_text(
    *,
    basis: str,
    base: float,
    trend: float,
    season_ok: bool,
    ref_year: int | None,
    filled: int,
    rest: int,
    target_annual: float | None,
) -> str:
    if basis == "ledger_monthly":
        head = "以本年度台账已填 {} 个月为基准（月均 {:.2f} 万吨）".format(filled, base)
    elif basis == "ledger_annual":
        head = "本年度台账无月度数据，按年度值 {:.2f} 万吨均摊（{:.2f} 万吨/月）".format(
            float(target_annual or 0), base
        )
    elif basis == "history_annual":
        head = "本年度台账无数据，按 {} 年年度值均摊（{:.2f} 万吨/月）".format(ref_year or "—", base)
    elif basis == "history_monthly":
        head = "本年度台账无数据，取 {} 年已填月份的均值 {:.2f} 万吨".format(ref_year or "—", base)
    else:
        return "无可用数据，未生成测算。"

    parts = [head]
    if trend != 1.0:
        parts.append("按重合月份同比修正 {:.3f}".format(trend))
    if season_ok:
        parts.append("套用 {} 年同月季节系数".format(ref_year or "—"))
    parts.append("推算剩余 {} 个月".format(rest))
    return "，".join(parts) + "。"
