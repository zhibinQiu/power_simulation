"""共享网络工具：UA、TTL 缓存、带编码回退的文本/JSON 拉取。

供 carbon_market（行情）与 market_news（快讯）等外部抓取模块复用，
消除各模块重复的 httpx/urllib 双路径与 TTL 缓存实现。
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Iterable

logger = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


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


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    h = {"User-Agent": UA}
    if extra:
        h.update(extra)
    return h


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
    headers = _headers(extra_headers)
    try:
        import httpx

        with httpx.Client(
            timeout=httpx.Timeout(timeout, connect=min(5.0, timeout)),
            verify=False,
            follow_redirects=True,
            headers=headers,
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception:  # noqa: BLE001
        pass
    try:
        import urllib.request

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return _decode(resp.read(), encodings)
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch text failed url=%s err=%s", url, exc)
        return None


def fetch_json(
    url: str,
    timeout: float = 15.0,
    extra_headers: dict[str, str] | None = None,
) -> Any | None:
    """拉取 JSON：httpx 优先，urllib 回退；失败返回 None。"""
    headers = _headers(extra_headers)
    try:
        import httpx

        with httpx.Client(
            timeout=httpx.Timeout(timeout, connect=min(5.0, timeout)),
            verify=False,
            follow_redirects=True,
            headers=headers,
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.json()
    except Exception:  # noqa: BLE001
        pass
    try:
        import urllib.request

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch json failed url=%s err=%s", url, exc)
        return None
