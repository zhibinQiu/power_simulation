"""市场快讯服务：爬取中国煤炭交易网（ctctc.cn）「市场快讯」栏目并做 TTL 缓存。

数据源：https://www.ctctc.cn/main/news/flashnewlist.jspx?nodeid=323&kw=&tag=&pageNumber=1

栏目为服务端渲染的静态 HTML，每条快讯结构如下（.list-sckx > ul > li）：
    <li>
      <div class="list-data">2026-08-19&nbsp;17:46</div>
      <div class="list-desc"><p>正文…</p></div>
      <div class="fenltab-cont">
        <a href="javascript:searchTag('炼焦煤');" class="fenltab">炼焦煤</a>
        <span class="liulan"><i></i><span id="info_views490287">163</span></span>
        <a id="490287" href="#" class="ckxq-btn">查看详情</a>
      </div>
    </li>

详情链接为 JS 弹窗（href="#"），因此仅提取时间 / 正文 / 标签 / 浏览量。
抓取失败时返回 ok=False + 空列表，由前端优雅降级（隐藏滚动条），不阻塞主流程。
"""
from __future__ import annotations

import logging
import re
from html import unescape
from typing import Any

from .netutil import TtlCache, fetch_text, now_iso

logger = logging.getLogger(__name__)

FLASH_LIST_URL = (
    "https://www.ctctc.cn/main/news/flashnewlist.jspx?nodeid=323&kw=&tag=&pageNumber={page}"
)
SOURCE_NAME = "中国煤炭交易网 · 市场快讯"
CACHE_TTL = 60.0  # 秒


def _strip_tags(html: str) -> str:
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html or "")
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def parse_flash_news(html: str) -> list[dict[str, Any]]:
    """解析快讯列表页，返回按页面顺序排列的快讯数组。"""
    if not html:
        return []
    # 限定在快讯容器内，避免误匹配页面底部导航等其他 <li>
    ul = re.search(
        r'<div\s+class="list-cont[^"]*list-sckx[^"]*"[^>]*>.*?<ul[^>]*>(.*?)</ul>',
        html,
        re.S,
    )
    body = ul.group(1) if ul else html
    items: list[dict[str, Any]] = []
    for m in re.finditer(r"<li[^>]*>\s*(.*?)\s*</li>", body, re.S):
        li = m.group(1)
        if "list-data" not in li:
            continue
        mt = re.search(r'<div\s+class="list-data"[^>]*>(.*?)</div>', li, re.S)
        md = re.search(r'<div\s+class="list-desc"[^>]*>(.*?)</div>', li, re.S)
        if not mt and not md:
            continue
        time_str = _strip_tags(mt.group(1)) if mt else ""
        content = _strip_tags(md.group(1)) if md else ""
        if not content:
            continue
        tags = [t.strip() for t in re.findall(r'class="fenltab"[^>]*>([^<]*)</a>', li)]
        m_views = re.search(r'id="info_views\d+"[^>]*>([^<]*)</span>', li)
        m_id = re.search(r'<a\s+id="(\d+)"[^>]*class="ckxq-btn"', li)
        items.append(
            {
                "id": m_id.group(1) if m_id else "",
                "time": time_str.replace("&nbsp;", " ").replace("\u00a0", " ").strip(),
                "tags": [t for t in tags if t],
                "content": content,
                "views": int(re.sub(r"\D", "", m_views.group(1))) if m_views else 0,
            }
        )
    return items


_cache = TtlCache(CACHE_TTL)


def fetch_news(page: int = 1) -> dict[str, Any]:
    """拉取市场快讯（带 TTL 缓存）；失败返回 ok=False 与空列表。"""
    page = max(1, int(page or 1))
    url = FLASH_LIST_URL.format(page=page)

    def _fetch() -> dict[str, Any]:
        html = fetch_text(url, timeout=15.0)
        items = parse_flash_news(html) if html else []
        return {
            "ok": bool(items),
            "source": url,
            "source_name": SOURCE_NAME,
            "queried_at": now_iso(),
            "items": items,
        }

    return _cache.get_or(f"news:page:{page}", _fetch)
