"""碳市场实时行情服务：CEA（上海环交所 K 线）+ CCER 报价。

数据源与解析逻辑参考 pdf_trans 项目
`app/services/carbon_compliance/market_sync.py`：
- CEA 日线  https://www.cneeex.com/zhhq/jsonData/hiskline.json?{ms_ts}
- CEA 分时  https://www.cneeex.com/zhhq/jsonData/kline.json?{ms_ts}
- CCER      https://www.ccn.ac.cn/cets （HTML 解析，失败走官方行情列表）

架构说明：
- 行情「数据获取」为策略模式（domain/market/sources.py）：
  RemoteQuoteSource（远程官方源）失败时自动降级 SimulatedQuoteSource（本地模拟），
  保证数字孪生「碳市场」视图始终有实时变化的数值展示；
- 走势「预测算法」为策略模式（domain/market/forecast.py）：
  linear / moving_average / exponential 可插拔，新增算法注册即可；
- 60s TTL 缓存，避免频繁请求外部站点。
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
from datetime import date, timedelta
from html import unescape
from typing import Any

from .domain.market import SimulatedQuoteSource, create_forecast_method, create_quote_source
from .netutil import UA, TtlCache, fetch_json, fetch_text, now_iso

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": UA,
    "Referer": "https://www.cneeex.com/",
    "Accept": "application/json,text/plain,*/*",
}

CNEEEX_DAILY_URL = "https://www.cneeex.com/zhhq/jsonData/hiskline.json"
CNEEEX_INTRADAY_URL = "https://www.cneeex.com/zhhq/jsonData/kline.json"
CCER_HOME_URL = "https://www.ccer.com.cn/"
CCER_DAILY_LIST_URL = "https://www.ccer.com.cn/wcm/ccer/data/2502lshq.json"
CCER_SOURCE_PAGE = "https://www.ccer.com.cn/wcm/ccer/html/2502lshq/index.html"
CCER_WP_HISTORY_URL = (
    "https://www.ccn.ac.cn/wp-json/wp/v2/posts?categories=61&per_page=20&page=1"
)
PRIMARY_MARKET_URL = "https://www.ccn.ac.cn/cets"

CACHE_TTL = 60.0  # 秒


# ── 数值/日期工具 ──────────────────────────────────────────────


def _f(v: Any) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("%", "")
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _today() -> date:
    return date.today()


def period_tag_for_month(month: int) -> str:
    if month <= 4:
        return "early"
    if month <= 9:
        return "mid"
    return "late"


def html_to_text(html: str) -> str:
    text = unescape(re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html or ""))
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_cn_date(y: str, m: str, d: str) -> date:
    return date(int(y), int(m), int(d))


# ── CEA：环交所 K 线解析 ───────────────────────────────────────


def parse_cneeex_daily_bars(rows: list[Any]) -> list[dict[str, Any]]:
    """日线：[日期, 开, 收, 低, 高, 量] → 结构化点。"""
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            continue
        try:
            trade_date = date.fromisoformat(str(row[0])[:10])
        except Exception:  # noqa: BLE001
            continue
        o, c, low, high = _f(row[1]), _f(row[2]), _f(row[3]), _f(row[4])
        vol = _f(row[5]) if len(row) > 5 else None
        if c is None and o is None:
            continue
        close = c if c is not None else o
        out.append(
            {
                "t": trade_date.isoformat(),
                "open": o,
                "close": close,
                "high": high if high is not None else close,
                "low": low if low is not None else close,
                "volume": vol,
                "price": close,
            }
        )
    return out


def parse_cneeex_intraday_latest(rows: list[Any]) -> dict[str, Any] | None:
    """分时：[时刻, 最新价, 开, 高, 低, ...] → 最后一个有效成交行。"""
    today = _today()
    best: dict[str, Any] | None = None
    for row in rows or []:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            continue
        last_px = _f(row[1])
        o, high, low = _f(row[2]), _f(row[3]), _f(row[4])
        if last_px is None or last_px <= 0:
            continue
        best = {
            "t": today.isoformat(),
            "open": o if o and o > 0 else last_px,
            "high": high if high and high > 0 else last_px,
            "low": low if low and low > 0 else last_px,
            "close": last_px,
            "price": last_px,
            "volume": _f(row[6]) if len(row) > 6 else None,
            "source": "intraday",
        }
    return best


def aggregate_daily_to_monthly(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按自然月聚合：均价=收盘均值，高低=月内极值，并保留月末收盘。"""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for p in points:
        buckets.setdefault(p["t"][:7], []).append(p)
    aggs: list[dict[str, Any]] = []
    for ym, items in sorted(buckets.items()):
        closes = [float(i["close"]) for i in items if i.get("close") is not None]
        highs = [float(i["high"]) for i in items if i.get("high") is not None]
        lows = [float(i["low"]) for i in items if i.get("low") is not None]
        if not closes:
            continue
        month = int(ym.split("-")[1])
        aggs.append(
            {
                "year_month": ym,
                "avg_price": round(sum(closes) / len(closes), 4),
                "high": max(highs) if highs else max(closes),
                "low": min(lows) if lows else min(closes),
                "last_close": closes[-1],
                "trade_days": len(items),
                "period_tag": period_tag_for_month(month),
            }
        )
    return aggs


def fetch_cea_series() -> dict[str, Any]:
    """拉取环交所 CEA 日线 + 分时，返回日序列、最新行情与月聚合。"""
    daily_url = f"{CNEEEX_DAILY_URL}?{int(time.time() * 1000)}"
    intra_url = f"{CNEEEX_INTRADAY_URL}?{int(time.time() * 1000)}"
    daily_raw = fetch_json(daily_url, extra_headers=_HEADERS)
    intra_raw = fetch_json(intra_url, extra_headers=_HEADERS)
    points = parse_cneeex_daily_bars(daily_raw if isinstance(daily_raw, list) else [])
    intra = parse_cneeex_intraday_latest(intra_raw if isinstance(intra_raw, list) else [])
    if intra and intra.get("price"):
        t = intra["t"]
        if points and points[-1]["t"] == t:
            points[-1] = {**points[-1], **intra}
        elif not points or points[-1]["t"] < t:
            points.append(intra)
    monthly = aggregate_daily_to_monthly(points)
    latest = points[-1] if points else None
    return {
        "ok": bool(points),
        "sources_tried": [daily_url, intra_url],
        "points": points,
        "latest": latest,
        "intraday": intra,
        "monthly": monthly,
        "daily_url": daily_url,
    }


# ── CCER：官方日行情 + HTML 兜底 ──────────────────────────────


def parse_ccer_daily_article(
    html: str, *, trade_date: date | None = None, source: str = ""
) -> dict[str, Any] | None:
    """解析官方每日行情正文：成交量/成交额/成交均价；无成交返回 None。"""
    text = html_to_text(html)
    if "无成交" in text:
        return None
    if trade_date is None:
        m_date = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
        if m_date:
            trade_date = _parse_cn_date(m_date.group(1), m_date.group(2), m_date.group(3))
    if trade_date is None:
        return None
    m_avg = re.search(r"成交均价\s*([\d,.]+)\s*元\s*/\s*吨", text)
    m_vol = re.search(r"(?:成交量|总成交量)\s*([\d,]+)\s*吨", text)
    m_amt = re.search(r"(?:成交额|总成交额)\s*([\d,.]+)\s*元", text)
    avg = _f(m_avg.group(1)) if m_avg else None
    vol = _f(m_vol.group(1)) if m_vol else None
    amt = _f(m_amt.group(1)) if m_amt else None
    if avg is None and vol and amt and vol > 0:
        avg = round(amt / vol, 2)
    if avg is None:
        return None
    return {
        "t": trade_date.isoformat(),
        "price": avg,
        "close": avg,
        "volume": vol,
        "source": source or CCER_SOURCE_PAGE,
    }


def parse_ccn_ccer_quote(text: str) -> dict[str, Any] | None:
    m = re.search(
        r"全国温室气体自愿减排交易行情\s*[（(](\d{4})年(\d{1,2})月(\d{1,2})日[）)]"
        r".{0,160}?"
        r"均价\s*[（(]元/吨[）)]"
        r".{0,80}?"
        r"(\d+)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)",
        text,
    )
    if m:
        return {
            "t": _parse_cn_date(m.group(1), m.group(2), m.group(3)).isoformat(),
            "price": float(m.group(6)),
            "close": float(m.group(6)),
            "source": PRIMARY_MARKET_URL,
        }
    m2 = re.search(
        r"全国温室气体自愿减排交易行情\s*[（(](\d{4})年(\d{1,2})月(\d{1,2})日[）)]"
        r".{0,240}?均价[^\d]{0,40}(\d{2,3}(?:\.\d{1,2})?)",
        text,
    )
    if not m2:
        return None
    avg = float(m2.group(4))
    return {
        "t": _parse_cn_date(m2.group(1), m2.group(2), m2.group(3)).isoformat(),
        "price": avg,
        "close": avg,
        "source": PRIMARY_MARKET_URL,
    }


def parse_ccn_ccer_history_table(text: str, *, source: str = "") -> list[dict[str, Any]]:
    """碳中和网 CCER 历史表：时间 / 成交量 / 成交额 / 均价 / 涨跌幅。"""
    out: list[dict[str, Any]] = []
    for m in re.finditer(
        r"(\d{4})/(\d{1,2})/(\d{1,2})\s+([\d,]+)\s+([\d,]+\.\d{2})\s+(\d+(?:\.\d+)?)",
        text,
    ):
        td = _parse_cn_date(m.group(1), m.group(2), m.group(3))
        avg = _f(m.group(6))
        if avg is None:
            continue
        out.append(
            {
                "t": td.isoformat(),
                "price": avg,
                "close": avg,
                "volume": _f(m.group(4)),
                "source": source or CCER_WP_HISTORY_URL,
            }
        )
    by_date: dict[str, dict[str, Any]] = {q["t"]: q for q in out}
    return [by_date[k] for k in sorted(by_date)]


def fetch_ccer_quote() -> dict[str, Any] | None:
    """HTML 兜底解析 CCER 最新成交均价。"""
    html = fetch_text(PRIMARY_MARKET_URL, timeout=12.0)
    if not html:
        return None
    return parse_ccn_ccer_quote(html_to_text(html))


def fetch_ccer_series() -> dict[str, Any]:
    """拉取 CCER 官方日行情列表；失败回退碳中和网历史表。"""
    sources_tried: list[str] = [CCER_HOME_URL, CCER_DAILY_LIST_URL]
    quotes: list[dict[str, Any]] = []
    try:
        import httpx

        with httpx.Client(
            timeout=httpx.Timeout(20.0, connect=6.0),
            verify=False,
            follow_redirects=True,
            headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
        ) as client:
            client.get(CCER_HOME_URL)
            resp = client.get(
                CCER_DAILY_LIST_URL,
                headers={
                    "Accept": "application/json,text/javascript,*/*;q=0.01",
                    "Referer": CCER_SOURCE_PAGE,
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ccer official daily fetch failed: %s", exc)
        payload = {}

    rows = payload.get("rows") if isinstance(payload, dict) else None
    if isinstance(rows, list):
        import asyncio

        async def _gather() -> list[dict[str, Any]]:
            sem = asyncio.Semaphore(8)

            async def _one(row: dict[str, Any]) -> dict[str, Any] | None:
                rel = str(row.get("url") or "").lstrip("/")
                if not rel:
                    return None
                m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", str(row.get("title") or ""))
                td = _parse_cn_date(m.group(1), m.group(2), m.group(3)) if m else None
                detail_url = CCER_SOURCE_PAGE.rsplit("/index.html", 1)[0] + "/" + rel
                async with sem:
                    try:
                        import httpx

                        async with httpx.AsyncClient(
                            timeout=httpx.Timeout(12.0, connect=5.0),
                            verify=False,
                            follow_redirects=True,
                            headers={"User-Agent": UA, "Referer": CCER_SOURCE_PAGE},
                        ) as c:
                            r = await c.get(detail_url)
                            r.raise_for_status()
                            return parse_ccer_daily_article(
                                r.text, trade_date=td, source=detail_url
                            )
                    except Exception:  # noqa: BLE001
                        return None

            results = await asyncio.gather(*[_one(r) for r in rows[:20]])
            return [q for q in results if q is not None]

        try:
            quotes = asyncio.run(_gather())
        except Exception as exc:  # noqa: BLE001
            logger.warning("ccer gather failed: %s", exc)
            quotes = []

    source_name = "全国温室气体自愿减排交易系统 · 北京绿色交易所"
    source_api = CCER_DAILY_LIST_URL
    if not quotes:
        html = fetch_text(CCER_WP_HISTORY_URL, timeout=20.0)
        if html:
            try:
                posts = json.loads(html)
            except Exception:  # noqa: BLE001
                posts = []
            if isinstance(posts, list):
                for post in posts:
                    if not isinstance(post, dict):
                        continue
                    content = (
                        ((post.get("content") or {}) if isinstance(post.get("content"), dict) else {})
                        .get("rendered")
                        or ""
                    )
                    quotes.extend(parse_ccn_ccer_history_table(html_to_text(content)))
        source_name = "碳中和网整理 · 北京绿色交易所口径"
        source_api = CCER_WP_HISTORY_URL
        latest = fetch_ccer_quote()
        if latest:
            by_date = {q["t"]: q for q in quotes}
            by_date[latest["t"]] = latest
            quotes = [by_date[k] for k in sorted(by_date)]

    by_date: dict[str, dict[str, Any]] = {q["t"]: q for q in quotes}
    ordered = [by_date[k] for k in sorted(by_date)]
    return {
        "ok": bool(ordered),
        "points": ordered,
        "latest": ordered[-1] if ordered else None,
        "sources_tried": sources_tried,
        "source_name": source_name,
        "source_api": source_api,
    }


# ── 降级模拟行情（外网不可用时保证界面实时变化） ────────────────


# ── 对外服务（TTL 缓存） ───────────────────────────────────────


_cache = TtlCache(CACHE_TTL)

# 模拟数据源单例（确定性模拟序列，供图表兜底使用）
_sim_source = SimulatedQuoteSource()


def fetch_quotes() -> dict[str, Any]:
    """结构化报价：CEA + CCER 最新价、涨跌幅、月聚合、查询时间。

    数据获取委托给行情源策略（create_quote_source）：远程失败自动降级模拟。
    """

    def _fetch() -> dict[str, Any]:
        source = create_quote_source()
        cea_pack = source.fetch_cea() or {}
        ccer = source.fetch_ccer()
        sources_tried = list(cea_pack.get("sources_tried") or [])
        cea_latest = cea_pack.get("latest")
        # CEA 模拟包补齐月度聚合（远程包在解析阶段已生成）
        if cea_pack.get("points") and not cea_pack.get("monthly"):
            cea_pack["monthly"] = aggregate_daily_to_monthly(cea_pack["points"])

        latest = cea_latest
        prev = cea_pack["points"][-2] if len(cea_pack["points"]) > 1 else latest
        chg_pct = (
            (latest["close"] - prev["close"]) / prev["close"] * 100
            if prev.get("close")
            else 0
        )
        latest = {**latest, "change_pct": round(chg_pct, 2)}
        simulated = (
            getattr(source, "cea_source", source.name) == "simulated"
            or getattr(source, "ccer_source", source.name) == "simulated"
        )
        if simulated:
            latest["source"] = "simulated"

        return {
            "ok": True,
            "simulated": simulated,
            "queried_at": now_iso(),
            "sources_tried": sources_tried,
            "cea": latest,
            "ccer": ccer,
            "cea_monthly": cea_pack.get("monthly") or [],
            "daily_count": len(cea_pack.get("points") or []),
            "intraday": cea_pack.get("intraday"),
        }

    return _cache.get_or("quotes", _fetch)


def fetch_chart(instrument: str = "cea", kind: str = "daily") -> dict[str, Any]:
    """供前端图表的序列数据：cea → 日K线，ccer → 成交均价折线。"""
    instrument = (instrument or "cea").strip().lower()
    kind = (kind or "daily").strip().lower()
    if instrument not in ("cea", "ccer"):
        instrument = "cea"

    def _fetch() -> dict[str, Any]:
        if instrument == "cea":
            pack = fetch_cea_series()
            points = pack.get("points") or []
            if not points:
                points = _sim_source.fetch_cea()["points"]
            return {
                "ok": bool(points),
                "instrument": "cea",
                "kind": "daily",
                "title": "CEA 日K线（蜡烛图）",
                "unit": "元/吨",
                "source_name": "上海环境能源交易所 · 全国碳市场",
                "source_page": "https://www.cneeex.com/zhhq/quotshown.html?area=0",
                "queried_at": now_iso(),
                "points": points,
            }
        pack = fetch_ccer_series()
        points = pack.get("points") or []
        if not points:
            points = _sim_source.fetch_ccer()["points"]
        return {
            "ok": bool(points),
            "instrument": "ccer",
            "kind": "daily",
            "title": "CCER 成交均价（折线图）",
            "unit": "元/吨",
            "source_name": pack.get("source_name") or "全国温室气体自愿减排交易系统",
            "source_page": CCER_SOURCE_PAGE,
            "queried_at": now_iso(),
            "points": points,
        }

    return _cache.get_or(f"chart:{instrument}:{kind}", _fetch)


# ── 走势预测（策略模式：linear / moving_average / exponential） ──


def _next_trade_date(day: date, step: int) -> date:
    """向前推进 step 个交易日（跳过周六/周日）。"""
    cur = day
    added = 0
    while added < step:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            added += 1
    return cur


def forecast_series(instrument: str = "cea", days: int = 10,
                    method: str = "linear") -> dict[str, Any]:
    """基于历史收盘价外推未来 days 个交易日价格与置信区间。

    预测方法 method：
      - linear          线性回归（最小二乘） + 残差置信带（默认）
      - moving_average  最近 N 日移动平均水平外推
      - exponential     指数平滑 SES 水平外推（α=0.3）

    - 取最近 90 个历史点拟合，标准差给出 ±1.65σ（约 90%）置信带；
    - 日期按历史平均间隔推进并跳过周末；
    - 复用 fetch_chart 的 60s TTL 缓存，不额外请求外部站点。
    """
    instrument = (instrument or "cea").strip().lower()
    if instrument not in ("cea", "ccer"):
        instrument = "cea"
    days = max(3, min(int(days or 10), 30))
    method = (method or "linear").strip().lower()

    chart = fetch_chart(instrument, "daily")
    points = chart.get("points") or []
    data = (points or [])[-90:]
    pairs: list[tuple[int, float]] = []
    for i, p in enumerate(data):
        v = p.get("close")
        if v is None:
            v = p.get("price")
        if v is not None:
            pairs.append((i, float(v)))
    if len(pairs) < 5:
        return {
            "ok": False,
            "instrument": instrument,
            "error": "历史数据不足，无法预测",
            "points": points,
        }

    xs = [float(x) for x, _ in pairs]
    ys = [y for _, y in pairs]
    z = 1.65  # ~90% 置信区间
    # 预测算法（策略模式）：linear / moving_average / exponential，可插拔注册
    forecaster = create_forecast_method(method)
    forecaster.fit(xs, ys)
    s = forecaster.sigma(xs, ys)
    method_label = forecaster.label

    # 历史点平均间隔（交易日天数），用于外推日期
    gaps = []
    for i in range(1, len(data)):
        try:
            d0 = date.fromisoformat(str(data[i - 1]["t"])[:10])
            d1 = date.fromisoformat(str(data[i]["t"])[:10])
            gaps.append(max(1, (d1 - d0).days))
        except Exception:  # noqa: BLE001
            continue
    step = round(sum(gaps) / len(gaps)) if gaps else 1
    step = max(1, min(step, 3))

    try:
        cursor = date.fromisoformat(str(data[-1]["t"])[:10])
    except Exception:  # noqa: BLE001
        cursor = _today()

    forecast: list[dict[str, Any]] = []
    for i in range(1, days + 1):
        cursor = _next_trade_date(cursor, step)
        center = forecaster.predict(i)
        band = z * s * math.sqrt(1.0 + i / max(1, len(pairs)))
        forecast.append(
            {
                "t": cursor.isoformat(),
                "price": round(center, 2),
                "close": round(center, 2),
                "high": round(center + band, 2),
                "low": round(center - band, 2),
                "forecast": True,
            }
        )

    return {
        "ok": True,
        "instrument": instrument,
        "days": days,
        "method": method_label,
        "confidence": "±1.65σ ≈ 90%",
        "slope": round(forecaster.slope, 4),
        "base_date": data[-1]["t"] if data else None,
        "source_name": chart.get("source_name", ""),
        "history_tail": data[-5:],
        "forecast": forecast,
    }


def market_forecast(instrument: str = "cea", days: int = 10,
                    method: str = "linear") -> dict[str, Any]:
    """行情预测别名：供报告生成等服务调用，透传预测方法。"""
    return forecast_series(instrument=instrument, days=days, method=method)


market_quotes = fetch_quotes  # 行情别名：供报告生成等服务调用
