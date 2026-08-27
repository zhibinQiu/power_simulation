"""碳市场行情自动拉取与结构化解析（入库用）。

CEA 主源：上海环境能源交易所全国碳市场 K 线 JSON
- 日线 hiskline.json?[ms_ts]  → [日期, 开, 收, 低, 高, 量]
- 分时 kline.json?[ms_ts]     → [时刻, 最新价, 开, 高, 低, ..., 量, 额, 涨跌幅]

CCER 主源：全国温室气体自愿减排交易系统（北京绿色交易所运营）每日行情
- 列表 /wcm/ccer/data/2502lshq.json
- 详情 /wcm/ccer/html/{url}（成交均价；无分时盘口公开 JSON）
碳中和网 HTML / WP 表可作为补充。
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from html import unescape
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Referer": "https://www.cneeex.com/",
    "Accept": "application/json,text/plain,*/*",
}

CNEEEX_DAILY_URL = "https://www.cneeex.com/zhhq/jsonData/hiskline.json"
CNEEEX_INTRADAY_URL = "https://www.cneeex.com/zhhq/jsonData/kline.json"
# CCER 官方日行情（需先访问首页获取 Cookie，否则可能 403）
CCER_HOME_URL = "https://www.ccer.com.cn/"
CCER_DAILY_LIST_URL = "https://www.ccer.com.cn/wcm/ccer/data/2502lshq.json"
CCER_DAILY_HTML_BASE = "https://www.ccer.com.cn/wcm/ccer/html/"
CCER_SOURCE_PAGE = "https://www.ccer.com.cn/wcm/ccer/html/2502lshq/index.html"
CCER_WP_HISTORY_URL = (
    "https://www.ccn.ac.cn/wp-json/wp/v2/posts?categories=61&per_page=20&page=1"
)
# CCER / 兜底 HTML
PRIMARY_MARKET_URL = "https://www.ccn.ac.cn/cets"
FALLBACK_PRICE_URLS = (
    "https://www.cets.org.cn",
    "https://www.cneeex.com",
)


@dataclass
class DailyQuote:
    trade_date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    avg_price: float | None = None
    volume: float | None = None
    source: str = ""
    instrument: str = "cea"  # cea | ccer

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["trade_date"] = self.trade_date.isoformat()
        return d

    @property
    def year_month(self) -> str:
        return f"{self.trade_date.year:04d}-{self.trade_date.month:02d}"

    @property
    def primary_price(self) -> float | None:
        if self.avg_price is not None:
            return float(self.avg_price)
        if self.close is not None:
            return float(self.close)
        return None


@dataclass
class MonthlyAgg:
    year_month: str
    avg_price: float
    high: float
    low: float
    last_close: float
    trade_days: int
    period_tag: str
    source: str = CNEEEX_DAILY_URL

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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


def period_tag_for_month(month: int) -> str:
    if month <= 4:
        return "early"
    if month <= 9:
        return "mid"
    return "late"


def cneeex_url(base: str, *, ts_ms: int | None = None) -> str:
    """环交所 K 线地址，查询参数为毫秒时间戳。"""
    ts = int(ts_ms if ts_ms is not None else time.time() * 1000)
    return f"{base}?{ts}"


def parse_cneeex_daily_bars(rows: list[Any]) -> list[DailyQuote]:
    """日线：[日期, 开, 收, 低, 高, 量]。"""
    out: list[DailyQuote] = []
    for row in rows or []:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            continue
        try:
            trade_date = date.fromisoformat(str(row[0])[:10])
        except Exception:
            continue
        o, c, low, high = _f(row[1]), _f(row[2]), _f(row[3]), _f(row[4])
        vol = _f(row[5]) if len(row) > 5 else None
        if c is None and o is None:
            continue
        close = c if c is not None else o
        out.append(
            DailyQuote(
                trade_date=trade_date,
                open=o,
                high=high if high is not None else close,
                low=low if low is not None else close,
                close=close,
                avg_price=close,
                volume=vol,
                source=CNEEEX_DAILY_URL,
                instrument="cea",
            )
        )
    return out


def parse_cneeex_intraday_latest(rows: list[Any], *, as_of: date | None = None) -> DailyQuote | None:
    """分时：取最后一个有效成交行 → [时刻, 最新价, 开, 高, 低, ...]。"""
    today = as_of or date.today()
    best: DailyQuote | None = None
    for row in rows or []:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            continue
        last_px = _f(row[1])
        o, high, low = _f(row[2]), _f(row[3]), _f(row[4])
        # 无成交时段多为 0
        if last_px is None or last_px <= 0:
            continue
        if (o is None or o <= 0) and (high is None or high <= 0):
            # 仅有昨收/参考价
            best = DailyQuote(
                trade_date=today,
                close=last_px,
                avg_price=last_px,
                source=CNEEEX_INTRADAY_URL,
                instrument="cea",
            )
            continue
        best = DailyQuote(
            trade_date=today,
            open=o if o and o > 0 else last_px,
            high=high if high and high > 0 else last_px,
            low=low if low and low > 0 else last_px,
            close=last_px,
            avg_price=last_px,
            volume=_f(str(row[6]).replace(",", "")) if len(row) > 6 else None,
            source=CNEEEX_INTRADAY_URL,
            instrument="cea",
        )
    return best


def aggregate_daily_to_monthly(quotes: list[DailyQuote]) -> list[MonthlyAgg]:
    """按自然月聚合：均价=收盘均值，高低=月内极值，并保留月末收盘。"""
    buckets: dict[str, list[DailyQuote]] = defaultdict(list)
    for q in quotes:
        if q.instrument != "cea":
            continue
        buckets[q.year_month].append(q)
    aggs: list[MonthlyAgg] = []
    for ym, items in sorted(buckets.items()):
        items = sorted(items, key=lambda x: x.trade_date)
        closes = [float(i.close) for i in items if i.close is not None]
        highs = [float(i.high) for i in items if i.high is not None]
        lows = [float(i.low) for i in items if i.low is not None]
        if not closes:
            continue
        month = int(ym.split("-")[1])
        aggs.append(
            MonthlyAgg(
                year_month=ym,
                avg_price=round(sum(closes) / len(closes), 4),
                high=max(highs) if highs else max(closes),
                low=min(lows) if lows else min(closes),
                last_close=closes[-1],
                trade_days=len(items),
                period_tag=period_tag_for_month(month),
                source=items[-1].source or CNEEEX_DAILY_URL,
            )
        )
    return aggs


async def _fetch_json(url: str, *, timeout: float = 20.0) -> Any | None:
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(5.0, timeout)),
            verify=False,
            follow_redirects=True,
            headers=_HEADERS,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("cneeex json fetch failed url=%s err=%s", url, exc)
        return None


async def fetch_cneeex_cea() -> dict[str, Any]:
    """拉取环交所 CEA 日线 + 分时，返回日序列与月聚合。"""
    daily_url = cneeex_url(CNEEEX_DAILY_URL)
    intra_url = cneeex_url(CNEEEX_INTRADAY_URL)
    daily_raw, intra_raw = await _fetch_json(daily_url), await _fetch_json(intra_url)
    sources = [daily_url, intra_url]
    daily_quotes = parse_cneeex_daily_bars(daily_raw if isinstance(daily_raw, list) else [])
    intra = parse_cneeex_intraday_latest(intra_raw if isinstance(intra_raw, list) else [])
    # 若分时有当日有效价，覆盖/追加到日序列末
    if intra and intra.primary_price:
        if daily_quotes and daily_quotes[-1].trade_date == intra.trade_date:
            daily_quotes[-1] = intra
        elif not daily_quotes or daily_quotes[-1].trade_date < intra.trade_date:
            daily_quotes.append(intra)
    monthly = aggregate_daily_to_monthly(daily_quotes)
    latest = daily_quotes[-1] if daily_quotes else None
    return {
        "ok": bool(daily_quotes),
        "sources_tried": sources,
        "daily_count": len(daily_quotes),
        "monthly": [m.to_dict() for m in monthly],
        "cea": latest.to_dict() if latest else None,
        "intraday": intra.to_dict() if intra else None,
        "daily_quotes": daily_quotes,
        "intraday_rows": intra_raw if isinstance(intra_raw, list) else [],
        "daily_url": daily_url,
        "intraday_url": intra_url,
    }


async def fetch_cea_chart_series(kind: str = "daily", *, method: str = "rule") -> dict[str, Any]:
    """供前端图表：daily / forecast（历史+至年底预测）。不再提供分时序列。"""
    from app.services.carbon_compliance.price_forecast import (
        build_forecast_chart_payload,
        forecast_cea_to_year_end,
        normalize_forecast_method,
    )

    k = (kind or "daily").strip().lower()
    if k in ("forecast", "predict", "prediction", "year_end"):
        k = "forecast"
    else:
        k = "daily"
    fc_method = normalize_forecast_method(method)

    pack = await fetch_cneeex_cea()
    source_page = "https://www.cneeex.com/zhhq/quotshown.html?area=0"

    points = [
        {
            "t": q.trade_date.isoformat(),
            "price": q.close if q.close is not None else q.avg_price,
            "open": q.open,
            "high": q.high,
            "low": q.low,
            "close": q.close,
            "volume": q.volume,
        }
        for q in (pack.get("daily_quotes") or [])
        if (q.close is not None or q.avg_price is not None)
    ]

    if k == "forecast":
        fc = forecast_cea_to_year_end(points, method=fc_method)
        method_label = {
            "rule": "规则预测",
            "ets": "ETS 预测",
            "sarimax": "SARIMAX 预测",
            "prophet": "Prophet 预测",
        }.get(fc_method, "规则预测")
        payload = build_forecast_chart_payload(
            points,
            fc,
            source_name=f"上海环境能源交易所历史日线 + 本平台{method_label}",
            source_page=source_page,
            source_api=pack.get("daily_url") or CNEEEX_DAILY_URL,
            title=f"CEA 日度预测（{method_label} · 当前→年底）",
            instrument="cea",
        )
        payload["forecast_method"] = fc.get("method") or fc_method
        return payload

    return {
        "ok": bool(points),
        "kind": "daily",
        "title": "CEA 日K线（蜡烛图）",
        "unit": "元/吨",
        "source_name": "上海环境能源交易所 · 全国碳市场",
        "source_page": source_page,
        "source_api": pack.get("daily_url") or CNEEEX_DAILY_URL,
        "queried_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "points": points,
        "latest": pack.get("cea"),
        "monthly_count": len(pack.get("monthly") or []),
    }


def fetch_cneeex_daily_quotes_sync() -> list[dict[str, Any]]:
    """同步拉取日线，供策略引擎（同步上下文）使用。"""
    url = cneeex_url(CNEEEX_DAILY_URL)
    try:
        with httpx.Client(
            timeout=httpx.Timeout(20.0, connect=5.0),
            verify=False,
            follow_redirects=True,
            headers=_HEADERS,
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            raw = resp.json()
    except Exception as exc:
        logger.warning("sync cneeex daily fetch failed: %s", exc)
        return []
    quotes = parse_cneeex_daily_bars(raw if isinstance(raw, list) else [])
    return [
        {
            "t": q.trade_date.isoformat(),
            "close": q.close,
            "price": q.close,
            "open": q.open,
            "high": q.high,
            "low": q.low,
        }
        for q in quotes
    ]


async def fetch_cea_forecast_to_year_end() -> dict[str, Any]:
    """仅返回预测序列与摘要（策略引擎可复用）。"""
    from app.services.carbon_compliance.price_forecast import forecast_cea_to_year_end

    series = await fetch_cea_chart_series("daily")
    points = series.get("points") or []
    fc = forecast_cea_to_year_end(points)
    return {
        "ok": bool(fc.get("ok")),
        "source_name": "上海环境能源交易所历史日线 + 本平台规则预测",
        "source_page": series.get("source_page"),
        "queried_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        **fc,
    }


# ── CCER 日线折线 + HTML 兜底 ─────────────────────────────────


def _parse_cn_date(y: str, m: str, d: str) -> date:
    return date(int(y), int(m), int(d))


def parse_ccer_list_trade_date(title: str) -> date | None:
    """从「2026年7月20日全国温室气体自愿减排…」标题解析交易日。"""
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", title or "")
    if not m:
        return None
    return _parse_cn_date(m.group(1), m.group(2), m.group(3))


def parse_ccer_daily_article(html: str, *, trade_date: date | None = None, source: str = "") -> DailyQuote | None:
    """解析官方每日行情正文：成交量/成交额/成交均价；无成交则返回 None。"""
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
    return DailyQuote(
        trade_date=trade_date,
        avg_price=avg,
        close=avg,
        volume=vol,
        source=source or CCER_SOURCE_PAGE,
        instrument="ccer",
    )


def parse_ccn_ccer_history_table(html_or_text: str, *, source: str = "") -> list[DailyQuote]:
    """解析碳中和网 CCER 历史表：时间 / 成交量 / 成交额 / 均价 / 涨跌幅。"""
    text = html_to_text(html_or_text) if "<" in (html_or_text or "") else (html_or_text or "")
    out: list[DailyQuote] = []
    for m in re.finditer(
        r"(\d{4})/(\d{1,2})/(\d{1,2})\s+([\d,]+)\s+([\d,]+\.\d{2})\s+(\d+(?:\.\d+)?)",
        text,
    ):
        td = _parse_cn_date(m.group(1), m.group(2), m.group(3))
        vol = _f(m.group(4))
        avg = _f(m.group(6))
        if avg is None:
            continue
        out.append(
            DailyQuote(
                trade_date=td,
                avg_price=avg,
                close=avg,
                volume=vol,
                source=source or "https://www.ccn.ac.cn/carbon-market/ccer/ccerdate",
                instrument="ccer",
            )
        )
    # 按日期去重，后写覆盖前写
    by_date: dict[date, DailyQuote] = {q.trade_date: q for q in out}
    return sorted(by_date.values(), key=lambda q: q.trade_date)


async def _ccer_http_client(*, timeout: float = 25.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=min(6.0, timeout)),
        verify=False,
        follow_redirects=True,
        headers={
            "User-Agent": _UA,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )


async def fetch_ccer_official_daily_quotes(
    *,
    max_pages: int | None = None,
    concurrency: int = 12,
) -> dict[str, Any]:
    """拉取官方每日行情列表并并发解析详情页，得到成交均价序列。"""
    sources_tried: list[str] = [CCER_HOME_URL, CCER_DAILY_LIST_URL]
    quotes: list[DailyQuote] = []
    try:
        async with await _ccer_http_client() as client:
            # 首页 Cookie，避免列表/详情 403
            await client.get(CCER_HOME_URL)
            list_resp = await client.get(
                CCER_DAILY_LIST_URL,
                headers={
                    "Accept": "application/json,text/javascript,*/*;q=0.01",
                    "Referer": CCER_SOURCE_PAGE,
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            list_resp.raise_for_status()
            payload = list_resp.json()
            rows = payload.get("rows") if isinstance(payload, dict) else None
            if not isinstance(rows, list):
                rows = []
            if max_pages is not None:
                rows = rows[: max(0, int(max_pages))]

            sem = asyncio.Semaphore(max(1, int(concurrency)))

            async def _one(row: dict[str, Any]) -> DailyQuote | None:
                if not isinstance(row, dict):
                    return None
                rel = str(row.get("url") or "").lstrip("/")
                if not rel:
                    return None
                trade_date = parse_ccer_list_trade_date(str(row.get("title") or ""))
                detail_url = CCER_DAILY_HTML_BASE + rel
                async with sem:
                    try:
                        resp = await client.get(
                            detail_url,
                            headers={"Referer": CCER_SOURCE_PAGE, "Accept": "text/html,*/*"},
                        )
                        resp.raise_for_status()
                    except Exception as exc:
                        logger.debug("ccer detail fetch failed url=%s err=%s", detail_url, exc)
                        return None
                return parse_ccer_daily_article(
                    resp.text, trade_date=trade_date, source=detail_url
                )

            results = await asyncio.gather(*[_one(r) for r in rows])
            quotes = [q for q in results if q is not None]
    except Exception as exc:
        logger.warning("ccer official daily fetch failed: %s", exc)
        return {
            "ok": False,
            "quotes": [],
            "sources_tried": sources_tried,
            "error": str(exc),
        }

    quotes.sort(key=lambda q: q.trade_date)
    by_date: dict[date, DailyQuote] = {q.trade_date: q for q in quotes}
    ordered = sorted(by_date.values(), key=lambda q: q.trade_date)
    return {
        "ok": bool(ordered),
        "quotes": ordered,
        "sources_tried": sources_tried,
        "list_total": len(ordered),
    }


async def fetch_ccer_wp_history_quotes() -> list[DailyQuote]:
    """碳中和网 WP 分类「CCER行情数据」年表，作官方拉取失败时的兜底。"""
    try:
        async with await _ccer_http_client(timeout=20.0) as client:
            resp = await client.get(
                CCER_WP_HISTORY_URL,
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            posts = resp.json()
    except Exception as exc:
        logger.warning("ccer wp history fetch failed: %s", exc)
        return []
    if not isinstance(posts, list):
        return []
    merged: list[DailyQuote] = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        content = ((post.get("content") or {}) if isinstance(post.get("content"), dict) else {}).get(
            "rendered"
        ) or ""
        link = str(post.get("link") or "")
        merged.extend(parse_ccn_ccer_history_table(content, source=link or CCER_WP_HISTORY_URL))
    by_date: dict[date, DailyQuote] = {q.trade_date: q for q in merged}
    return sorted(by_date.values(), key=lambda q: q.trade_date)


async def fetch_ccer_chart_series(kind: str = "daily", *, method: str = "rule") -> dict[str, Any]:
    """供前端折线图：daily / 至年底预测（不做分时）。"""
    from app.services.carbon_compliance.price_forecast import (
        build_forecast_chart_payload,
        forecast_to_year_end,
        normalize_forecast_method,
    )

    k = (kind or "daily").strip().lower()
    if k in ("forecast", "predict", "prediction", "year_end"):
        k = "forecast"
    else:
        k = "daily"
    fc_method = normalize_forecast_method(method)

    pack = await fetch_ccer_official_daily_quotes()
    quotes: list[DailyQuote] = list(pack.get("quotes") or [])
    source_name = "全国温室气体自愿减排交易系统 · 北京绿色交易所"
    source_api = CCER_DAILY_LIST_URL
    if not quotes:
        quotes = await fetch_ccer_wp_history_quotes()
        source_name = "碳中和网整理 · 北京绿色交易所口径"
        source_api = CCER_WP_HISTORY_URL
        latest = await fetch_ccer_quote()
        if latest:
            by_date = {q.trade_date: q for q in quotes}
            by_date[latest.trade_date] = latest
            quotes = sorted(by_date.values(), key=lambda q: q.trade_date)

    points = [
        {
            "t": q.trade_date.isoformat(),
            "price": q.avg_price if q.avg_price is not None else q.close,
            "open": q.open,
            "high": q.high,
            "low": q.low,
            "close": q.close if q.close is not None else q.avg_price,
            "volume": q.volume,
        }
        for q in quotes
        if (q.avg_price is not None or q.close is not None)
    ]
    latest_q = quotes[-1] if quotes else None
    queried_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    if k == "forecast":
        fc = forecast_to_year_end(points, instrument="ccer", method=fc_method)
        method_label = {
            "rule": "规则预测",
            "ets": "ETS 预测",
            "sarimax": "SARIMAX 预测",
            "prophet": "Prophet 预测",
        }.get(fc_method, "规则预测")
        payload = build_forecast_chart_payload(
            points,
            fc,
            source_name=source_name + f" 历史日线 + 本平台{method_label}",
            source_page=CCER_SOURCE_PAGE,
            source_api=source_api,
            title=f"CCER 日度预测（{method_label} · 当前→年底）",
            instrument="ccer",
        )
        payload["queried_at"] = queried_at
        payload["forecast_method"] = fc.get("method") or fc_method
        return payload

    return {
        "ok": bool(points),
        "kind": "daily",
        "title": "CCER 日K线（蜡烛图）",
        "unit": "元/吨",
        "instrument": "ccer",
        "source_name": source_name,
        "source_page": CCER_SOURCE_PAGE,
        "source_api": source_api,
        "queried_at": queried_at,
        "points": points,
        "latest": latest_q.to_dict() if latest_q else None,
    }


def html_to_text(html: str) -> str:
    text = unescape(re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html or ""))
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_ccn_cea_quote(text: str) -> DailyQuote | None:
    m = re.search(
        r"全国碳市场综合价格行情[（(]CEA[）)]\s*[（(](\d{4})年(\d{1,2})月(\d{1,2})日[）)]"
        r".{0,120}?"
        r"开盘\s*[（(]元/吨[）)]\s*最高\s*[（(]元/吨[）)]\s*最低\s*[（(]元/吨[）)]\s*收盘\s*[（(]元/吨[）)]"
        r".{0,40}?"
        r"(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)",
        text,
    )
    if not m:
        m2 = re.search(
            r"全国碳市场综合价格行情[（(]CEA[）)]\s*[（(](\d{4})年(\d{1,2})月(\d{1,2})日[）)]"
            r".{0,200}?(\d{2,3}\.\d{1,2})\s+(\d{2,3}\.\d{1,2})\s+(\d{2,3}\.\d{1,2})\s+(\d{2,3}\.\d{1,2})",
            text,
        )
        if not m2:
            return None
        m = m2
    trade_date = _parse_cn_date(m.group(1), m.group(2), m.group(3))
    o, h, low, c = (float(m.group(i)) for i in range(4, 8))
    return DailyQuote(
        trade_date=trade_date,
        open=o,
        high=h,
        low=low,
        close=c,
        avg_price=c,
        source=PRIMARY_MARKET_URL,
        instrument="cea",
    )


def parse_ccn_ccer_quote(text: str) -> DailyQuote | None:
    m = re.search(
        r"全国温室气体自愿减排交易行情\s*[（(](\d{4})年(\d{1,2})月(\d{1,2})日[）)]"
        r".{0,160}?"
        r"均价\s*[（(]元/吨[）)]"
        r".{0,80}?"
        r"(\d+)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)",
        text,
    )
    if m:
        trade_date = _parse_cn_date(m.group(1), m.group(2), m.group(3))
        avg = float(m.group(6))
        return DailyQuote(
            trade_date=trade_date,
            avg_price=avg,
            close=avg,
            source=PRIMARY_MARKET_URL,
            instrument="ccer",
        )
    m2 = re.search(
        r"全国温室气体自愿减排交易行情\s*[（(](\d{4})年(\d{1,2})月(\d{1,2})日[）)]"
        r".{0,240}?均价[^\d]{0,40}(\d{2,3}(?:\.\d{1,2})?)",
        text,
    )
    if not m2:
        return None
    trade_date = _parse_cn_date(m2.group(1), m2.group(2), m2.group(3))
    avg = float(m2.group(4))
    return DailyQuote(
        trade_date=trade_date,
        avg_price=avg,
        close=avg,
        source=PRIMARY_MARKET_URL,
        instrument="ccer",
    )


def parse_fallback_prices(text: str, *, as_of: date | None = None) -> list[DailyQuote]:
    out: list[DailyQuote] = []
    today = as_of or date.today()
    for line in re.split(r"[。；\n]", text):
        line = line.strip()
        if not line or "元" not in line:
            continue
        nums = [float(x.replace(",", "")) for x in re.findall(r"\d{2,3}(?:\.\d{1,2})?", line)]
        nums = [n for n in nums if 20 <= n <= 200]
        if not nums:
            continue
        price = nums[0]
        instrument = "ccer" if "CCER" in line.upper() or "自愿减排" in line else "cea"
        if "碳价" in line or "CEA" in line.upper() or "配额" in line or instrument == "ccer":
            out.append(
                DailyQuote(
                    trade_date=today,
                    avg_price=price,
                    close=price,
                    source="fallback",
                    instrument=instrument,
                )
            )
            if len(out) >= 2:
                break
    return out


def parse_market_page(html: str, *, url: str = PRIMARY_MARKET_URL) -> dict[str, DailyQuote | None]:
    text = html_to_text(html)
    cea = parse_ccn_cea_quote(text)
    ccer = parse_ccn_ccer_quote(text)
    if cea:
        cea.source = url
    if ccer:
        ccer.source = url
    if not cea and not ccer:
        for q in parse_fallback_prices(text):
            q.source = url
            if q.instrument == "cea" and not cea:
                cea = q
            elif q.instrument == "ccer" and not ccer:
                ccer = q
    return {"cea": cea, "ccer": ccer}


async def fetch_market_html(
    url: str = PRIMARY_MARKET_URL,
    *,
    timeout: float = 12.0,
) -> str | None:
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(4.0, timeout)),
            verify=False,
            follow_redirects=True,
            headers={"User-Agent": _UA},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception as exc:
        logger.warning("carbon market fetch failed url=%s err=%s", url, exc)
        return None


async def fetch_ccer_quote() -> DailyQuote | None:
    html = await fetch_market_html(PRIMARY_MARKET_URL)
    if not html:
        return None
    return parse_market_page(html, url=PRIMARY_MARKET_URL).get("ccer")


async def fetch_structured_quotes() -> dict[str, Any]:
    """拉取 CEA（环交所 K 线）+ CCER（HTML 补充）。"""
    sources_tried: list[str] = []
    cea_pack = await fetch_cneeex_cea()
    sources_tried.extend(cea_pack.get("sources_tried") or [])
    ccer = await fetch_ccer_quote()
    if ccer:
        sources_tried.append(PRIMARY_MARKET_URL)
    # 环交所失败时回退 HTML CEA
    if not cea_pack.get("ok"):
        html = await fetch_market_html(PRIMARY_MARKET_URL)
        sources_tried.append(PRIMARY_MARKET_URL)
        if html:
            parsed = parse_market_page(html, url=PRIMARY_MARKET_URL)
            if parsed.get("cea"):
                cea_pack["cea"] = parsed["cea"].to_dict()
                cea_pack["monthly"] = [
                    MonthlyAgg(
                        year_month=parsed["cea"].year_month,
                        avg_price=float(parsed["cea"].primary_price or 0),
                        high=float(parsed["cea"].high or parsed["cea"].primary_price or 0),
                        low=float(parsed["cea"].low or parsed["cea"].primary_price or 0),
                        last_close=float(parsed["cea"].close or parsed["cea"].primary_price or 0),
                        trade_days=1,
                        period_tag=period_tag_for_month(parsed["cea"].trade_date.month),
                        source=PRIMARY_MARKET_URL,
                    ).to_dict()
                ]
                cea_pack["ok"] = True
            if not ccer and parsed.get("ccer"):
                ccer = parsed["ccer"]

    return {
        "ok": bool(cea_pack.get("ok") or ccer),
        "queried_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "sources_tried": sources_tried,
        "cea": cea_pack.get("cea"),
        "ccer": ccer.to_dict() if ccer else None,
        "cea_monthly": cea_pack.get("monthly") or [],
        "daily_count": cea_pack.get("daily_count") or 0,
        "intraday": cea_pack.get("intraday"),
    }
