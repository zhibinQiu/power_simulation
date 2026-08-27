# -*- coding: utf-8 -*-
"""搜索结果适配工具（simulation 项目的适配垫片）。

接口与 pdf_trans 的 app.tools.adapters 对齐。simulation 项目不联网抓取正文，
_enrich_items_with_full_text 原样返回，由算法模块按自身规则过滤。
"""
from __future__ import annotations

from typing import Any, Iterable, List


async def _enrich_items_with_full_text(
    items: Iterable[dict[str, Any]],
    count: int,
    *,
    loop_state: Any = None,
) -> List[dict[str, Any]]:
    """为条目补充 full_text（垫片：不联网抓取，回填已有字段）。"""
    out = list(items)[:count]
    for it in out:
        it.setdefault(
            "full_text",
            it.get("body") or it.get("content") or it.get("title") or "",
        )
    return out
