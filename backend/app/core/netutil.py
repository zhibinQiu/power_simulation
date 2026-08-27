"""共享网络工具：UA 池、TTL 缓存、带编码回退的文本/JSON 拉取（内置反爬规避）。

供碳市场行情与快讯等外部抓取模块复用（基础设施层，不依赖业务模块）。

反爬规避策略（仅针对公开行情/资讯数据，保持低频合规抓取）：
- 真实浏览器 UA 池随机轮换 + 完整浏览器请求头（Accept / Sec-Fetch-* / Cookie）；
- 自动按目标域名生成同源 Referer（显式传入优先）；
- 线程本地 httpx 会话保持 Cookie（部分站点首次下发 cookie 后才放行数据接口）；
- 403 / 429 / 5xx 带随机退避重试，避免精确节拍被识别为爬虫。
"""
from __future__ import annotations

import json
import logging
import random
import threading
import time
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# 真实浏览器 UA 池（Chrome/Edge/Firefox 桌面 + Safari 移动），随机轮换降低指纹一致性
UA_POOL = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1",
)
UA = UA_POOL[0]  # 兼容导出（历史固定值；实际请求会从池中随机选取）


class _RetryableStatus(Exception):
    """可重试的 HTTP 状态（403/429/5xx），触发随机退避重试。"""


class TtlCache:
    """线程安全的 TTL 缓存：get_or(key, fetch) 命中过期即重新拉取。"""

    def __init__(self, ttl: float) -> None:
        self.ttl = ttl
        self._lock = threading.Lock()
        self._data: dict[str, tuple[float, Any]] = {}

    def get_or(self, key: str, fetch) -> Any:
        now = time.monotonic()
        with self._lock:
            hit = self._data.get(key)
            if hit and now - hit[0] < self.ttl:
                return hit[1]
        value = fetch()
        with self._lock:
            self._data[key] = (time.monotonic(), value)
        return value


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _referer_for(url: str) -> str:
    """按目标域名生成同源 Referer（部分站点校验来源域名）。"""
    try:
        host = urlparse(url).hostname or ""
    except Exception:  # noqa: BLE001
        host = ""
    return f"https://{host}/" if host else ""


def _headers(
    extra: dict[str, str] | None = None,
    *,
    url: str = "",
    html: bool = False,
) -> dict[str, str]:
    """组装接近真实浏览器的请求头；显式传入的字段（extra）优先。"""
    h = {
        "User-Agent": random.choice(UA_POOL),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    if html:
        h["Accept"] = (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        )
        h["Upgrade-Insecure-Requests"] = "1"
        h["Sec-Fetch-Site"] = "same-origin"
        h["Sec-Fetch-Mode"] = "navigate"
        h["Sec-Fetch-Dest"] = "document"
    else:
        h["Accept"] = "application/json, text/plain, */*"
        h["Sec-Fetch-Site"] = "same-origin"
        h["Sec-Fetch-Mode"] = "cors"
        h["Sec-Fetch-Dest"] = "empty"
    if extra:
        h.update(extra)
    if not h.get("Referer"):
        h["Referer"] = _referer_for(url)
    return h


_client_local = threading.local()


def _http_client(timeout: float):
    """线程本地 httpx 会话：复用连接并保持 Cookie（部分站点需先下发 cookie）。"""
    import httpx

    client = getattr(_client_local, "client", None)
    if client is None:
        client = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=min(5.0, timeout)),
            verify=False,
            follow_redirects=True,
            headers={},
        )
        _client_local.client = client
    return client


def _request(
    url: str,
    *,
    timeout: float,
    extra_headers: dict[str, str] | None,
    html: bool,
    encodings: tuple[str, ...],
) -> tuple[bool, str | None]:
    """统一抓取：httpx 优先 + urllib 回退 + 403/429/5xx 随机退避重试。

    返回 (ok, text)；ok=False 表示最终失败（调用方决定是否回退历史数据）。
    """
    attempts = 3
    for attempt in range(attempts):
        headers = _headers(extra_headers, url=url, html=html)

        # 1) httpx 会话（保持 cookie、连接复用）
        try:
            import httpx

            resp = _http_client(timeout).get(url, headers=headers)
            if resp.status_code in (403, 429) or resp.status_code >= 500:
                raise _RetryableStatus(resp.status_code)
            resp.raise_for_status()
            return True, resp.text
        except _RetryableStatus as exc:
            logger.warning(
                "fetch retryable status url=%s code=%s attempt=%d/%d",
                url, exc, attempt + 1, attempts,
            )
        except Exception:  # noqa: BLE001
            # httpx 失败时本轮内回退 urllib 再试一次
            try:
                return True, _fetch_urllib(url, headers, timeout, encodings)
            except Exception as urllib_exc:  # noqa: BLE001
                logger.warning(
                    "fetch failed url=%s attempt=%d/%d err=%s",
                    url, attempt + 1, attempts, urllib_exc,
                )

        # 2) urllib 直连回退（httpx 不可用时）
        try:
            return True, _fetch_urllib(url, headers, timeout, encodings)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "fetch failed url=%s attempt=%d/%d err=%s",
                url, attempt + 1, attempts, exc,
            )

        if attempt < attempts - 1:
            time.sleep(random.uniform(0.5, 2.0))  # 随机退避，避免精确节拍
    return False, None


def _fetch_urllib(
    url: str,
    headers: dict[str, str],
    timeout: float,
    encodings: tuple[str, ...],
) -> str:
    import urllib.request

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        code = getattr(resp, "status", 200)
        if code in (403, 429) or code >= 500:
            raise _RetryableStatus(code)
        return _decode(resp.read(), encodings)


def _decode(raw: bytes, encodings: Iterable[str]) -> str:
    for enc in encodings:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")


def fetch_text(
    url: str,
    timeout: float = 15.0,
    extra_headers: dict[str, str] | None = None,
    encodings: tuple[str, ...] = ("utf-8", "gbk"),
) -> str | None:
    """拉取网页文本：httpx 优先，urllib 回退，支持编码回退；失败返回 None。"""
    ok, text = _request(
        url, timeout=timeout, extra_headers=extra_headers,
        html=True, encodings=encodings,
    )
    return text if ok else None


def fetch_json(
    url: str,
    timeout: float = 15.0,
    extra_headers: dict[str, str] | None = None,
) -> Any | None:
    """拉取 JSON：httpx 优先，urllib 回退；失败返回 None。"""
    ok, text = _request(
        url, timeout=timeout, extra_headers=extra_headers,
        html=False, encodings=("utf-8",),
    )
    if not ok or not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("fetch json parse failed url=%s err=%s", url, exc)
        return None
