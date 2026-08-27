# -*- coding: utf-8 -*-
"""双碳政策检索服务（simulation 项目的适配垫片）。

接口与 pdf_trans 的 app.services.carbon_service 对齐，仅实现
fetch_carbon_policy 的兜底语义：simulation 项目未接入发改委政策抓取，
直接返回 ok=False 的结构化结果，供算法模块回退到内置规则/模板。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def normalize_policy_keyword(keyword: str) -> str:
    return (keyword or "").strip()


async def fetch_carbon_policy(
    *,
    keyword: str = "",
    url: str = "",
    timeout: float = 16.0,
    pages: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    """政策检索（垫片：无外部服务，返回未命中兜底结构）。"""
    queried_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    kw = normalize_policy_keyword(keyword)
    return {
        "ok": False,
        "query_type": "policy",
        "keyword": kw,
        "queried_at": queried_at,
        "sources": [],
        "failed_urls": [],
        "summary_md": "（当前环境未接入发改委政策检索，无可用政策结果）",
        "error": "not_configured",
        "total_hits": 0,
    }
