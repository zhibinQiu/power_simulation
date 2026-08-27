"""碳价日度预测（CEA / CCER）。

支持算法（method）：
- rule：衰减趋势 + 去均值季节 + 履约季冲高回落
- ets：Holt-Winters 加法季节（交易周 period=5）
- sarimax：SARIMAX / ARX，外生变量=履约月(10–12)
- prophet：Prophet（周/年季节 + 履约月回归器；未安装则回退 rule）

波动带统一：近 60 日收益标准差 × √前瞻天数。
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable


@dataclass
class ForecastPoint:
    t: str  # YYYY-MM-DD
    price: float
    low: float
    high: float
    is_forecast: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ForecastSummary:
    as_of: str
    end_date: str
    last_close: float
    year_end_price: float
    year_end_low: float
    year_end_high: float
    peak_price: float
    peak_date: str
    trough_price: float
    trough_date: str
    trading_days: int
    method: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _closes_from_history(history: Iterable[dict[str, Any]]) -> list[tuple[date, float]]:
    rows: list[tuple[date, float]] = []
    for h in history:
        t = h.get("t") or h.get("trade_date")
        px = h.get("close")
        if px is None:
            px = h.get("price")
        if t is None or px is None:
            continue
        try:
            d = date.fromisoformat(str(t)[:10])
            p = float(px)
        except Exception:
            continue
        if p <= 0:
            continue
        rows.append((d, p))
    rows.sort(key=lambda x: x[0])
    out: list[tuple[date, float]] = []
    seen: set[date] = set()
    for d, p in rows:
        if d in seen:
            out[-1] = (d, p)
        else:
            seen.add(d)
            out.append((d, p))
    return out


def _iter_trading_days(start: date, end: date) -> list[date]:
    days: list[date] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            days.append(cur)
        cur += timedelta(days=1)
    return days


def _ma(values: list[float], n: int) -> float | None:
    if len(values) < n or n <= 0:
        return None
    return sum(values[-n:]) / n


def _daily_returns(closes: list[float]) -> list[float]:
    rets: list[float] = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            rets.append((closes[i] - closes[i - 1]) / closes[i - 1])
    return rets


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.02
    m = sum(xs) / len(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(max(var, 1e-12))


def _seasonal_week_returns(series: list[tuple[date, float]]) -> dict[int, float]:
    by_week: dict[int, list[float]] = defaultdict(list)
    for i in range(1, len(series)):
        d0, p0 = series[i - 1]
        d1, p1 = series[i]
        if p0 <= 0:
            continue
        if (d1 - d0).days > 10:
            continue
        week = d1.isocalendar()[1]
        by_week[week].append((p1 - p0) / p0)
    raw = {w: sum(v) / len(v) for w, v in by_week.items() if v}
    # 去均值：去掉跨年结构性上涨，保留周内相对强弱
    if not raw:
        return {}
    mean_s = sum(raw.values()) / len(raw)
    return {w: v - mean_s for w, v in raw.items()}


def _q4_vs_h1_premium_ratio(series: list[tuple[date, float]]) -> float:
    """四季度均价相对当年上半年均价的溢价率（可正可负）。

    正：往年四季度均价高于上半年；负：四季度相对偏弱。
    无足够样本时默认 +4%（履约季相对偏强的保守先验）。
    """
    by_year: dict[int, dict[str, list[float]]] = defaultdict(lambda: {"h1": [], "q4": []})
    for d, p in series:
        if d.month <= 6:
            by_year[d.year]["h1"].append(p)
        elif d.month >= 10:
            by_year[d.year]["q4"].append(p)
    ratios: list[float] = []
    for _y, buckets in by_year.items():
        if buckets["h1"] and buckets["q4"]:
            h1 = sum(buckets["h1"]) / len(buckets["h1"])
            q4 = sum(buckets["q4"]) / len(buckets["q4"])
            if h1 > 0:
                ratios.append(q4 / h1 - 1.0)
    if not ratios:
        return 0.04
    ratios.sort()
    return ratios[len(ratios) // 2]


# 兼容旧名
_q4_premium_ratio = _q4_vs_h1_premium_ratio


def _compliance_season_daily_bump(d: date, *, amp: float) -> float:
    """履约季日度加成：四季度前中段偏强、年末回吐（冲高回落）。

    进度 p：10/1→0，12/31→1。
    形态接近往年履约窗口：10–11 月抬升，约 12 月初附近见顶，12 月下旬回落。
    amp 为溢价幅度量级（绝对值为主，符号表示整体偏强/偏弱）。
    """
    if d.month < 10:
        return 0.0
    start = date(d.year, 10, 1)
    end = date(d.year, 12, 31)
    p = (d - start).days / max(1, (end - start).days)
    # 非对称驼峰：峰约在 p=0.62（约 12 月初），其后转负回吐
    peak_p = 0.62
    if p <= peak_p:
        shape = math.sin(0.5 * math.pi * (p / peak_p))  # 0→1
    else:
        # 从峰值降到年末约 -0.45（回吐部分履约溢价，年底不是最高点）
        t = (p - peak_p) / max(1e-6, 1.0 - peak_p)
        shape = 1.0 - 1.45 * (t**1.15)
    # 分到四季度约 60 个交易日量级，避免单日过大
    scale = float(amp) / 55.0
    return scale * shape


def forecast_to_year_end(
    history: list[dict[str, Any]],
    *,
    as_of: date | None = None,
    year: int | None = None,
    instrument: str = "cea",
    method: str = "rule",
) -> dict[str, Any]:
    """
    基于历史日线，预测 as_of 次日 → 年底每个交易日的中枢价及高低带。
    method: rule | ets | sarimax | prophet
    """
    m = _normalize_forecast_method(method)
    if m == "ets":
        return _forecast_ets(history, as_of=as_of, year=year, instrument=instrument)
    if m == "sarimax":
        return _forecast_sarimax(history, as_of=as_of, year=year, instrument=instrument)
    if m == "prophet":
        return _forecast_prophet(history, as_of=as_of, year=year, instrument=instrument)
    return _forecast_rule(history, as_of=as_of, year=year, instrument=instrument)


FORECAST_METHODS = (
    ("rule", "规则模型（趋势+季节+履约季）"),
    ("ets", "ETS（Holt-Winters）"),
    ("sarimax", "SARIMAX（履约月外生变量）"),
    ("prophet", "Prophet"),
)


def normalize_forecast_method(method: str | None) -> str:
    m = str(method or "rule").strip().lower()
    aliases = {
        "rule": "rule",
        "trend_seasonal_compliance": "rule",
        "default": "rule",
        "ets": "ets",
        "holt": "ets",
        "holt_winters": "ets",
        "sarimax": "sarimax",
        "arima": "sarimax",
        "prophet": "prophet",
    }
    return aliases.get(m, "rule")


def _normalize_forecast_method(method: str | None) -> str:
    return normalize_forecast_method(method)

def _forecast_context(
    history: list[dict[str, Any]],
    *,
    as_of: date | None,
    year: int | None,
) -> dict[str, Any] | None:
    series = _closes_from_history(history)
    today = as_of or date.today()
    if series:
        last_hist = series[-1][0]
        if last_hist > today:
            today = last_hist
    y = year or today.year
    end = date(y, 12, 31)
    if today >= end:
        end = date(y + 1, 12, 31)
    if len(series) < 5:
        return None
    last_date, last_close = series[-1]
    start_fc = last_date + timedelta(days=1)
    while start_fc.weekday() >= 5:
        start_fc += timedelta(days=1)
    if start_fc > end:
        return None
    future_days = _iter_trading_days(start_fc, end)
    closes = [p for _, p in series]
    rets = _daily_returns(closes[-61:])
    vol = _std(rets[-60:] if len(rets) >= 20 else rets)
    vol = max(0.005, min(0.05, vol))
    return {
        "series": series,
        "closes": closes,
        "today": today,
        "end": end,
        "last_date": last_date,
        "last_close": last_close,
        "future_days": future_days,
        "vol": vol,
    }


def _pack_forecast_result(
    *,
    ctx: dict[str, Any],
    prices: list[float],
    instrument: str,
    method: str,
    note: str,
) -> dict[str, Any]:
    last_close = float(ctx["last_close"])
    vol = float(ctx["vol"])
    future_days: list[date] = ctx["future_days"]
    points: list[ForecastPoint] = []
    for i, (d, price) in enumerate(zip(future_days, prices), start=1):
        px = max(10.0, float(price))
        band = last_close * vol * math.sqrt(i)
        band = min(band, last_close * 0.25)
        points.append(
            ForecastPoint(
                t=d.isoformat(),
                price=round(px, 2),
                low=round(max(10.0, px - band), 2),
                high=round(px + band, 2),
            )
        )
    if not points:
        return {"ok": False, "error": "no_future_days", "points": [], "summary": None}
    peak = max(points, key=lambda p: p.price)
    trough = min(points, key=lambda p: p.price)
    year_end = points[-1]
    label = "CEA" if str(instrument).lower() == "cea" else "CCER"
    summary = ForecastSummary(
        as_of=ctx["today"].isoformat(),
        end_date=ctx["end"].isoformat(),
        last_close=round(last_close, 2),
        year_end_price=year_end.price,
        year_end_low=year_end.low,
        year_end_high=year_end.high,
        peak_price=peak.price,
        peak_date=peak.t,
        trough_price=trough.price,
        trough_date=trough.t,
        trading_days=len(points),
        method=method,
        note=f"{note} {label} 公开侧无实时挂单，输入为历史日均/收盘；仅供履约择机参考，不构成投资建议。",
    )
    return {
        "ok": True,
        "points": [p.to_dict() for p in points],
        "summary": summary.to_dict(),
        "anchor_date": ctx["last_date"].isoformat(),
        "anchor_price": round(last_close, 2),
        "instrument": str(instrument).lower(),
        "method": method,
    }


def _forecast_rule(
    history: list[dict[str, Any]],
    *,
    as_of: date | None = None,
    year: int | None = None,
    instrument: str = "cea",
) -> dict[str, Any]:
    """确定性规则模型：衰减趋势 + 去均值季节 + 履约季冲高回落。"""
    ctx = _forecast_context(history, as_of=as_of, year=year)
    if ctx is None:
        return {"ok": False, "error": "insufficient_history", "points": [], "summary": None}

    closes = ctx["closes"]
    last_close = ctx["last_close"]
    series = ctx["series"]
    future_days = ctx["future_days"]

    ma20 = _ma(closes, 20) or last_close
    ma60 = _ma(closes, 60) or ma20
    # 初始漂移；后续按半衰期衰减，避免「天天同向加」滚到年底单调走高
    drift0 = (ma20 - ma60) / max(ma60, 1e-6) / 40.0
    drift0 = max(-0.002, min(0.002, drift0))
    drift_halflife = 35.0  # 约 35 个交易日后衰减一半

    seasonal = _seasonal_week_returns(series)
    prem = _q4_vs_h1_premium_ratio(series)
    # 履约季形态振幅：用溢价绝对值，限制在合理区间
    amp = max(0.02, min(0.12, abs(float(prem))))
    if prem < 0:
        amp = -amp  # 历史上四季度相对偏弱时，整段履约季偏空

    prices: list[float] = []
    price = last_close
    for h, d in enumerate(future_days, start=1):
        week = d.isocalendar()[1]
        seas = seasonal.get(week, 0.0)
        seas = max(-0.008, min(0.008, seas))

        decay = 0.5 ** ((h - 1) / drift_halflife)
        drift = drift0 * decay
        # 弱均值回归：向 MA60 缓慢靠拢，抑制单边发散
        mr = 0.015 * (ma60 - price) / max(ma60, 1e-6)
        mr = max(-0.0015, min(0.0015, mr))

        compliance_bump = _compliance_season_daily_bump(d, amp=amp)
        day_ret = drift + mr + 0.30 * seas + compliance_bump
        day_ret = max(-0.025, min(0.025, day_ret))
        price = max(10.0, price * (1.0 + day_ret))
        prices.append(price)

    return _pack_forecast_result(
        ctx=ctx,
        prices=prices,
        instrument=instrument,
        method="trend_seasonal_compliance",
        note=(
            "算法=规则模型：衰减趋势(均线差日漂移)+去均值同周季节+"
            "履约季冲高回落（四季度相对上半年溢价定振幅；约12月初见顶、年底回吐）；"
            "波动带=近60日收益标准差×√天数。"
        ),
    )


def _forecast_ets(
    history: list[dict[str, Any]],
    *,
    as_of: date | None = None,
    year: int | None = None,
    instrument: str = "cea",
) -> dict[str, Any]:
    """Holt-Winters 加法季节（交易周 period=5）。"""
    ctx = _forecast_context(history, as_of=as_of, year=year)
    if ctx is None:
        return {"ok": False, "error": "insufficient_history", "points": [], "summary": None}

    closes = ctx["closes"]
    period = 5
    alpha, beta, gamma = 0.35, 0.15, 0.25
    n = len(closes)
    if n < period * 2:
        # 样本不足时退回规则模型
        out = _forecast_rule(history, as_of=as_of, year=year, instrument=instrument)
        if out.get("summary"):
            out["summary"]["note"] = (
                "ETS 样本不足（需≥10 个交易日），已回退规则模型。" + (out["summary"].get("note") or "")
            )
            out["summary"]["method"] = "ets_fallback_rule"
            out["method"] = "ets_fallback_rule"
        return out

    level = sum(closes[:period]) / period
    trend = (sum(closes[period : period * 2]) - sum(closes[:period])) / (period * period)
    season = [closes[i] - level for i in range(period)]

    for t in range(period, n):
        val = closes[t]
        s = season[t % period]
        last_level = level
        level = alpha * (val - s) + (1 - alpha) * (level + trend)
        trend = beta * (level - last_level) + (1 - beta) * trend
        season[t % period] = gamma * (val - level) + (1 - gamma) * s

    prices: list[float] = []
    for h, _d in enumerate(ctx["future_days"], start=1):
        px = level + h * trend + season[(n + h - 1) % period]
        prices.append(max(10.0, px))

    return _pack_forecast_result(
        ctx=ctx,
        prices=prices,
        instrument=instrument,
        method="ets",
        note="算法=ETS Holt-Winters 加法季节（交易周 period=5）；波动带=近60日收益标准差×√天数。",
    )


def _compliance_exog(d: date) -> float:
    """履约月外生变量：10–12 月为 1，否则 0。"""
    return 1.0 if d.month >= 10 else 0.0


def _forecast_sarimax(
    history: list[dict[str, Any]],
    *,
    as_of: date | None = None,
    year: int | None = None,
    instrument: str = "cea",
) -> dict[str, Any]:
    """SARIMAX：优先 statsmodels；否则用 AR(1)+履约月外生的最小二乘近似。"""
    ctx = _forecast_context(history, as_of=as_of, year=year)
    if ctx is None:
        return {"ok": False, "error": "insufficient_history", "points": [], "summary": None}

    series: list[tuple[date, float]] = ctx["series"]
    closes = ctx["closes"]
    dates = [d for d, _ in series]
    future_days: list[date] = ctx["future_days"]
    note_suffix = ""

    try:
        import numpy as np
        from statsmodels.tsa.statespace.sarimax import SARIMAX  # type: ignore

        y = np.asarray(closes, dtype=float)
        exog = np.asarray([_compliance_exog(d) for d in dates], dtype=float).reshape(-1, 1)
        # 样本较短时用简单阶数，避免过拟合
        order = (1, 1, 1) if len(y) >= 40 else (1, 0, 0)
        seasonal_order = (0, 0, 0, 0)
        model = SARIMAX(
            y,
            exog=exog,
            order=order,
            seasonal_order=seasonal_order,
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        fitted = model.fit(disp=False)
        fut_exog = np.asarray([_compliance_exog(d) for d in future_days], dtype=float).reshape(-1, 1)
        pred = fitted.get_forecast(steps=len(future_days), exog=fut_exog)
        prices = [float(x) for x in pred.predicted_mean]
        note_suffix = f"statsmodels SARIMAX{order} + 履约月(10–12)外生。"
    except Exception:
        # 简易 ARX：Δp_t = a + b·Δp_{t-1} + c·compliance_t
        import numpy as np

        dy = np.diff(np.asarray(closes, dtype=float))
        if len(dy) < 8:
            out = _forecast_rule(history, as_of=as_of, year=year, instrument=instrument)
            if out.get("summary"):
                out["summary"]["note"] = (
                    "SARIMAX 样本不足，已回退规则模型。" + (out["summary"].get("note") or "")
                )
                out["summary"]["method"] = "sarimax_fallback_rule"
                out["method"] = "sarimax_fallback_rule"
            return out
        x_lag = dy[:-1]
        x_ex = np.asarray([_compliance_exog(d) for d in dates[2:]], dtype=float)
        y = dy[1:]
        # 对齐长度
        n = min(len(x_lag), len(x_ex), len(y))
        x_lag, x_ex, y = x_lag[-n:], x_ex[-n:], y[-n:]
        X = np.column_stack([np.ones(n), x_lag, x_ex])
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        a, b, c = [float(v) for v in coef]
        prices = []
        price = float(closes[-1])
        prev_dy = float(dy[-1])
        for d in future_days:
            dy_hat = a + b * prev_dy + c * _compliance_exog(d)
            price = max(10.0, price + dy_hat)
            prev_dy = dy_hat
            prices.append(price)
        note_suffix = "未安装/拟合 statsmodels 时使用 AR(1)+履约月外生最小二乘近似。"

    return _pack_forecast_result(
        ctx=ctx,
        prices=prices,
        instrument=instrument,
        method="sarimax",
        note=f"算法=SARIMAX（带履约月外生变量）；{note_suffix} 波动带=近60日收益标准差×√天数。",
    )


def _forecast_prophet(
    history: list[dict[str, Any]],
    *,
    as_of: date | None = None,
    year: int | None = None,
    instrument: str = "cea",
) -> dict[str, Any]:
    """Prophet；未安装时回退规则模型并标注。"""
    ctx = _forecast_context(history, as_of=as_of, year=year)
    if ctx is None:
        return {"ok": False, "error": "insufficient_history", "points": [], "summary": None}

    try:
        import pandas as pd
        from prophet import Prophet  # type: ignore
    except Exception:
        out = _forecast_rule(history, as_of=as_of, year=year, instrument=instrument)
        if out.get("summary"):
            out["summary"]["note"] = (
                "未安装 prophet 包，已回退规则模型。若需启用请在 API 环境安装 prophet。"
                + (out["summary"].get("note") or "")
            )
            out["summary"]["method"] = "prophet_fallback_rule"
            out["method"] = "prophet_fallback_rule"
        return out

    series = ctx["series"]
    df = pd.DataFrame({"ds": [d for d, _ in series], "y": [p for _, p in series]})
    # 履约月作为额外回归器
    df["compliance"] = [ _compliance_exog(d) for d, _ in series ]
    m = Prophet(
        daily_seasonality=False,
        weekly_seasonality=True,
        yearly_seasonality=True,
        changepoint_prior_scale=0.05,
    )
    m.add_regressor("compliance")
    m.fit(df)
    future = pd.DataFrame({"ds": ctx["future_days"]})
    future["compliance"] = [_compliance_exog(d) for d in ctx["future_days"]]
    fc = m.predict(future)
    prices = [float(x) for x in fc["yhat"].tolist()]

    return _pack_forecast_result(
        ctx=ctx,
        prices=prices,
        instrument=instrument,
        method="prophet",
        note="算法=Prophet（周/年季节性 + 履约月回归器）；波动带=近60日收益标准差×√天数。",
    )


def forecast_cea_to_year_end(
    history: list[dict[str, Any]],
    *,
    as_of: date | None = None,
    year: int | None = None,
    method: str = "rule",
) -> dict[str, Any]:
    """兼容旧名：等同 forecast_to_year_end(instrument='cea')。"""
    return forecast_to_year_end(
        history, as_of=as_of, year=year, instrument="cea", method=method
    )

def build_forecast_chart_payload(
    history_points: list[dict[str, Any]],
    forecast: dict[str, Any],
    *,
    source_name: str,
    source_page: str,
    source_api: str,
    title: str | None = None,
    instrument: str = "cea",
) -> dict[str, Any]:
    """历史收盘 + 预测中枢/高低带，供前端叠加折线。"""
    hist = [
        {
            "t": h["t"],
            "price": h.get("close") if h.get("close") is not None else h.get("price"),
            "open": h.get("open"),
            "high": h.get("high"),
            "low": h.get("low"),
            "close": h.get("close") if h.get("close") is not None else h.get("price"),
            "volume": h.get("volume"),
            "is_forecast": False,
        }
        for h in history_points
        if (h.get("close") is not None or h.get("price") is not None)
    ]
    fc_pts = forecast.get("points") or []
    label = "CEA" if str(instrument).lower() == "cea" else "CCER"
    return {
        "ok": bool(hist or fc_pts) and bool(forecast.get("ok")),
        "kind": "forecast",
        "title": title or f"{label} 日度预测（当前→年底）",
        "unit": "元/吨",
        "instrument": str(instrument).lower(),
        "source_name": source_name,
        "source_page": source_page,
        "source_api": source_api,
        "queried_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "points": hist,
        "forecast_points": fc_pts,
        "summary": forecast.get("summary"),
        "latest": {
            "close": forecast.get("anchor_price"),
            "price": forecast.get("anchor_price"),
        },
        "method_note": (forecast.get("summary") or {}).get("note"),
        "note": (forecast.get("summary") or {}).get("note"),
    }
