"""碳市场政策/资讯 Deep-research：多查询检索 → 面向企业类型的双碳摘要（非网页原文）。"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# 平台识别：域名片段 → 中文标签
_PLATFORM_RULES: tuple[tuple[str, str], ...] = (
    ("weibo.com", "微博"),
    ("weibo.cn", "微博"),
    ("tieba.baidu.com", "贴吧"),
    ("xiaohongshu.com", "小红书"),
    ("xhslink.com", "小红书"),
    ("mp.weixin.qq.com", "公众号"),
    ("weixin.qq.com", "公众号"),
    ("zhihu.com", "知乎"),
    ("douyin.com", "抖音"),
    ("toutiao.com", "头条"),
    ("cls.cn", "财联社"),
    ("eastmoney.com", "东方财富"),
    ("gov.cn", "政务官网"),
    ("mee.gov.cn", "生态环境部"),
    ("cneeex.com", "环交所"),
    ("ccer.com.cn", "自愿减排"),
    ("cenews.com.cn", "中国环境报"),
)

_SOCIAL_PLATFORMS = frozenset({"微博", "贴吧", "小红书", "公众号", "知乎", "抖音", "头条"})

_TOPIC_KW = (
    "碳",
    "CEA",
    "CCER",
    "履约",
    "配额",
    "排放",
    "双碳",
    "减排",
    "碳市场",
    "碳交易",
    "碳中和",
    "碳达峰",
    "结转",
)


def _detect_platform(url: str, title: str = "", query: str = "") -> str:
    host = ""
    try:
        host = (urlparse(url).netloc or "").lower()
    except Exception:
        host = ""
    blob = f"{host} {title} {query}".lower()
    for needle, label in _PLATFORM_RULES:
        if needle in host or needle in blob:
            return label
    q = query or ""
    for name in ("微博", "贴吧", "小红书", "公众号", "知乎", "抖音"):
        if name in q:
            return name
    return "其他"


def _build_official_queries(*, industry_label: str, year: int) -> list[str]:
    y = int(year)
    ind = (industry_label or "控排企业").strip()
    return [
        f"{y}年全国碳市场履约政策 最新",
        f"全国碳排放权交易市场 CEA 配额结转 {y}",
        f"CCER 自愿减排交易 最新动态 {y}",
        f"{ind}行业 节能降碳 碳市场履约 政策",
        f"生态环境部 全国碳市场 配额分配 {y}",
        "上海环境能源交易所 全国碳市场 行情 新闻",
    ]


def _build_social_queries(*, industry_label: str, year: int) -> list[str]:
    """社媒/社区观点查询（避免过度依赖 site:，提高命中率）。"""
    y = int(year)
    ind = (industry_label or "控排").strip()
    return [
        f"微博 碳交易 全国碳市场 观点 {y}",
        f"碳交易 履约 吐槽 OR 解读 微博 {y}",
        "贴吧 碳交易 碳市场 讨论",
        "小红书 碳中和 碳交易 双碳 科普",
        f"微信公众号 全国碳市场 履约 配额结转 {y}",
        f"公众号 {ind} 碳市场 履约 建议",
        "知乎 全国碳市场 履约 配额 怎么看",
        f"碳交易 市场情绪 看涨 OR 看跌 {y}",
        f"{ind} 碳配额 价格 讨论 {y}",
        f"全国碳市场 惜售 OR 抛售 OR 履约季 {y}",
        f"CCER 抵扣 市场观点 {y}",
    ]


def _build_queries(*, industry_label: str, year: int) -> list[str]:
    return _build_official_queries(
        industry_label=industry_label, year=year
    ) + _build_social_queries(industry_label=industry_label, year=year)


def _is_topic_relevant(item: dict[str, Any]) -> bool:
    text = f"{item.get('title', '')}{item.get('content', '')}{item.get('query', '')}"
    return any(k in text for k in _TOPIC_KW)


def _is_social_item(item: dict[str, Any], social_q_set: set[str]) -> bool:
    if item.get("platform") in _SOCIAL_PLATFORMS:
        return True
    q = str(item.get("query") or "")
    return q in social_q_set


def _split_buckets(
    items: list[dict[str, Any]], social_q_set: set[str]
) -> tuple[list[dict], list[dict]]:
    social: list[dict] = []
    official: list[dict] = []
    for it in items:
        if _is_social_item(it, social_q_set):
            social.append(it)
        else:
            official.append(it)
    return official, social


def _clip(text: str, n: int) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"


def _normalize_cmp(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip().lower())


def _is_substantive_item(item: dict[str, Any]) -> bool:
    """正文须明显多于标题，且非标题复读；否则视为无信息量。"""
    title = str(item.get("title") or "").strip()
    body = _item_body(item, limit=2000)
    # 中文正文按字符计；低于约两句则视为无信息量
    if len(body) < 60:
        return False
    nt, nb = _normalize_cmp(title), _normalize_cmp(body)
    if not nb:
        return False
    if nt and (nb == nt or (nb.startswith(nt) and len(nb) < len(nt) + 36)):
        return False
    # 标题占正文绝大部分 → 仍是标题级
    if nt and len(nt) >= 12 and nt in nb and len(nb) <= int(len(nt) * 1.35) + 20:
        return False
    # 常见低信息落地页
    url = (item.get("url") or "").lower()
    if any(x in url for x in ("bilibili.com/video", "douyin.com", "tiktok.com")) and len(
        body
    ) < 160:
        return False
    return True


def _filter_substantive(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [it for it in items if _is_substantive_item(it)]


async def _llm_filter_informative(
    items: list[dict[str, Any]],
    *,
    industry_label: str,
    compliance_year: int,
    bucket: str,
) -> list[dict[str, Any]]:
    """用 LLM 剔除标题党/无实质观点的条目；失败则退回规则过滤结果。"""
    from app.integrations.deepseek_client import chat_completion_message_async, is_configured

    ruled = _filter_substantive(items)
    if not ruled:
        return []
    if len(ruled) <= 1 or not is_configured():
        return ruled

    lines = []
    for i, it in enumerate(ruled, 1):
        lines.append(
            f"{i}. [{it.get('platform') or '其他'}] {_clip(str(it.get('title') or ''), 70)}\n"
            f"   {_item_body(it, limit=320)}"
        )
    system = (
        "你是双碳信息质检员。判断哪些条目对控排企业履约/碳市场有实质信息量。"
        "无实质（仅标题复读、视频封面文案、广告引流、与双碳无关）的不要。"
        "只输出 JSON 数组，元素为保留条目的序号（从 1 开始），例如 [1,3]。"
        "若全无价值，输出 []。"
    )
    user = (
        f"企业类型：{industry_label}；履约年：{compliance_year}；类别：{bucket}\n\n"
        + "\n".join(lines)
    )
    try:
        choice = await chat_completion_message_async(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            timeout=60.0,
        )
    except Exception as exc:
        logger.warning("carbon informative filter LLM failed: %s", exc)
        return ruled
    if not choice:
        return ruled
    raw = str(((choice.get("message") or {}).get("content") or "")).strip()
    m = re.search(r"\[[\d,\s]*\]", raw)
    if not m:
        return ruled
    try:
        idxs = [int(x) for x in re.findall(r"\d+", m.group(0))]
    except Exception:
        return ruled
    picked = [ruled[i - 1] for i in idxs if 1 <= i <= len(ruled)]
    return picked or []


def _item_body(item: dict[str, Any], *, limit: int = 1000) -> str:
    """优先全文，其次搜索摘要；保证摘要模型看到内容级材料。"""
    full = str(item.get("full_text") or "").strip()
    snip = str(item.get("content") or item.get("snippet") or "").strip()
    body = full if len(full) >= max(80, len(snip)) else snip
    return _clip(body, limit)


def _evidence_block(items: list[dict[str, Any]], *, limit: int = 8) -> str:
    """给摘要模型用的内容级证据（标题 + 正文要点摘录）。"""
    lines: list[str] = []
    for i, it in enumerate(items[:limit], 1):
        plat = it.get("platform") or "其他"
        title = _clip(str(it.get("title") or "无标题"), 80)
        body = _item_body(it, limit=1000)
        url = (it.get("url") or "").strip()
        lines.append(f"{i}. [{plat}] {title}")
        if body:
            lines.append(f"   正文要点：{body}")
        else:
            lines.append("   正文要点：（未能抓取正文，仅有标题）")
        if url:
            lines.append(f"   链接：{url}")
    return "\n".join(lines) if lines else "（无）"


def _sources_md(items: list[dict[str, Any]], *, limit: int = 12, start: int = 1) -> str:
    """编号来源列表（含可点击链接，供报告末尾展示）。"""
    lines: list[str] = []
    n = start - 1
    for it in items:
        url = (it.get("url") or "").strip()
        if not url:
            continue
        n += 1
        if n - start + 1 > limit:
            break
        plat = it.get("platform") or "其他"
        title = _clip(str(it.get("title") or url), 72)
        # 标题可点开；同时保留纯 URL 便于复制
        lines.append(f"[{n}] [{plat}] [{title}]({url})")
        lines.append(f"    {url}")
    return "\n".join(lines)


def _opinion_hints_md(social_items: list[dict[str, Any]]) -> str:
    """无 LLM 时的规则线索（基于正文/摘要，供测试与兜底）。"""
    if not social_items:
        return "（本次社媒检索未命中可引用条目）"
    bullish = ("看涨", "上涨", "走强", "利好", "高位", "惜售", "买配额")
    bearish = ("看跌", "下跌", "走弱", "利空", "低迷", "抛售", "过剩")
    policy = ("政策", "结转", "履约", "配额", "生态环境部", "分配", "办法", "通知")
    lines = ["观点线索："]
    for it in social_items[:8]:
        blob = f"{it.get('title', '')} {_item_body(it, limit=400)}"
        tags: list[str] = []
        if any(k in blob for k in bullish):
            tags.append("偏多/看涨")
        if any(k in blob for k in bearish):
            tags.append("偏空/看跌")
        if any(k in blob for k in policy):
            tags.append("政策相关")
        tag_s = "、".join(tags) if tags else "一般讨论"
        plat = it.get("platform") or "社媒"
        title = _clip(str(it.get("title") or "无标题"), 60)
        body = _item_body(it, limit=180)
        lines.append(f"- [{plat}] {title}（{tag_s}）")
        if body:
            lines.append(f"  {body}")
    return "\n".join(lines)


def _rule_digest_md(
    *,
    industry_label: str,
    official: list[dict[str, Any]],
    social: list[dict[str, Any]],
) -> str:
    """LLM 不可用时的内容级结构化摘要（仍不粘贴整页原文）。"""
    parts = [
        f"### 官方与行业政策要点摘要（面向「{industry_label}」控排企业）\n",
    ]
    if official:
        parts.append("要点：")
        for it in official[:6]:
            body = _item_body(it, limit=280)
            parts.append(
                f"- [{it.get('platform') or '其他'}] "
                f"{_clip(str(it.get('title') or ''), 70)}"
            )
            if body:
                parts.append(f"  {body}")
        parts.append("")
    else:
        parts.append("本次未获取到。\n")

    parts.append(f"\n### 社媒与市场情绪摘要（面向「{industry_label}」+ 双碳）\n")
    if social:
        parts.append(_opinion_hints_md(social))
        parts.append("\n\n> 社媒观点、非官方结论；与官方冲突时以可核验来源为准。\n")
    else:
        parts.append("本次未获取到。\n")
    return "\n".join(parts).strip()


async def _llm_digest_md(
    *,
    industry_label: str,
    compliance_year: int,
    official: list[dict[str, Any]],
    social: list[dict[str, Any]],
) -> str | None:
    """将正文级证据提炼为面向企业类型的双碳摘要，禁止只列标题或粘贴网页原文。"""
    from app.integrations.deepseek_client import chat_completion_message_async, is_configured

    if not is_configured():
        return None
    if not official and not social:
        return None

    system = (
        "你是全国碳市场履约研究助理。任务：根据检索到的「正文要点」证据，"
        f"为「{industry_label}」类控排企业撰写 {compliance_year} 年双碳/履约相关摘要。\n"
        "硬约束：\n"
        "1. 只输出 Markdown，必须含且仅含两节标题：\n"
        f"### 官方与行业政策要点摘要（面向「{industry_label}」控排企业）\n"
        f"### 社媒与市场情绪摘要（面向「{industry_label}」+ 双碳）\n"
        "2. 必须基于「正文要点」做内容级归纳（政策口径、时间节点、结转/履约要求、"
        "行业影响、市场情绪与分歧），禁止只复述标题，也禁止大段粘贴原文。\n"
        "3. 每节用 3–6 条要点；只保留与目标企业类型、双碳、碳市场履约、配额/CCER/结转、"
        "节能降碳相关的信息；无关内容丢弃。\n"
        "4. 社媒节须归纳情绪倾向与政策解读口径，并标注「社媒观点、非官方结论」；"
        "若社媒证据为空或正文无法支撑，该节正文只写「本次未获取到」。\n"
        "5. 官方节若无正文级依据，写「本次未获取到」。禁止编造条文编号、日期、价格。\n"
        "6. 全文简体中文；除 CEA、CCER 外少用英文。\n"
    )
    user = (
        f"企业类型：{industry_label}\n履约年：{compliance_year}\n\n"
        "## 官方/行业正文证据\n"
        f"{_evidence_block(official, limit=8)}\n\n"
        "## 社媒/市场观点正文证据\n"
        f"{_evidence_block(social, limit=8)}\n\n"
        "请按硬约束输出两节「内容级」摘要。"
    )
    try:
        choice = await chat_completion_message_async(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.25,
            timeout=120.0,
        )
    except Exception as exc:
        logger.warning("carbon policy digest LLM failed: %s", exc)
        return None
    if not choice:
        return None
    msg = (choice.get("message") or {}) if isinstance(choice, dict) else {}
    text = str(msg.get("content") or "").strip()
    if not text or "官方与行业政策要点摘要" not in text:
        return None
    return text


async def research_carbon_market_news(
    db,
    *,
    industry_label: str,
    compliance_year: int,
    max_items: int = 16,
    read_full: int = 10,
    social_max: int = 8,
    official_max: int = 8,
) -> dict[str, Any]:
    """Deep-research：抓取正文后生成面向企业类型的双碳内容级摘要。"""
    from app.services.searxng_service import (
        SearxngNotConfiguredError,
        SearxngSearchError,
        is_enabled,
        search_web,
    )

    queried_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    queries = _build_queries(industry_label=industry_label, year=compliance_year)
    social_qs = _build_social_queries(industry_label=industry_label, year=compliance_year)
    social_q_set = set(social_qs)

    if not is_enabled(db):
        from app.services import carbon_service as carbon

        kw = f"全国碳市场 履约 {industry_label} 碳排放权交易"
        try:
            fallback = await carbon.fetch_carbon_policy(keyword=kw, timeout=16.0)
        except Exception as exc:
            logger.warning("carbon policy fallback failed: %s", exc)
            return {
                "ok": False,
                "mode": "fallback_failed",
                "queried_at": queried_at,
                "queries": queries,
                "sources": [],
                "social_sources": [],
                "summary_md": (
                    f"### 官方与行业政策要点摘要（面向「{industry_label}」控排企业）\n\n"
                    f"联网检索未配置，且官网抓取失败（{type(exc).__name__}）。\n\n"
                    f"### 社媒与市场情绪摘要（面向「{industry_label}」+ 双碳）\n\n"
                    "本次未获取到。"
                ),
                "error": "no_searxng_and_fallback_failed",
            }
        fb_md = str(fallback.get("summary_md") or "").strip()
        # 回退结果仍做一次「面向行业」的摘要包装，避免把整页 HTML 叙事塞进报告
        digest = await _llm_digest_md(
            industry_label=industry_label,
            compliance_year=compliance_year,
            official=[
                {
                    "platform": "政务官网",
                    "title": "官网/行业站回退摘要",
                    "content": _clip(fb_md, 800),
                    "url": "",
                }
            ]
            if fb_md
            else [],
            social=[],
        )
        if not digest:
            digest = (
                f"### 官方与行业政策要点摘要（面向「{industry_label}」控排企业）\n\n"
                + (_clip(fb_md, 600) if fb_md else "本次未获取到。")
                + f"\n\n### 社媒与市场情绪摘要（面向「{industry_label}」+ 双碳）\n\n"
                "本次未获取到。\n\n"
                "> 说明：当前未配置联网搜索，社媒观点不可用；官方段来自官网回退线索。\n"
            )
        note = ""
        return {
            "ok": bool(fallback.get("ok")),
            "mode": "official_fallback",
            "queried_at": queried_at,
            "queries": queries,
            "sources": fallback.get("sources") or [],
            "social_sources": [],
            "summary_md": (note + digest).strip(),
            "error": fallback.get("error"),
        }

    loop = asyncio.get_running_loop()
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    failed_queries: list[str] = []

    async def _one(q: str) -> None:
        try:
            items, _ = await loop.run_in_executor(
                None, lambda qq=q: search_web(qq, page_size=6, db=db)
            )
        except (SearxngNotConfiguredError, SearxngSearchError) as exc:
            failed_queries.append(f"{q}（{exc}）")
            return
        except Exception as exc:
            failed_queries.append(f"{q}（{type(exc).__name__}）")
            logger.warning("carbon deep-research query failed q=%r: %s", q, exc)
            return
        for it in items or []:
            url = str((it or {}).get("url") or "").strip()
            if not url or url in seen:
                continue
            if re.search(r"(login|passport|account)\.", urlparse(url).netloc or ""):
                continue
            seen.add(url)
            title = (it.get("title") or "").strip()
            content = (it.get("content") or it.get("snippet") or "").strip()
            merged.append(
                {
                    "title": title,
                    "url": url,
                    "content": content,
                    "engine": it.get("engine"),
                    "query": q,
                    "platform": _detect_platform(url, title, q),
                }
            )

    await asyncio.gather(*[_one(q) for q in queries])

    filtered = [it for it in merged if _is_topic_relevant(it)] or merged
    official_all, social_all = _split_buckets(filtered, social_q_set)

    social_top = social_all[: max(0, int(social_max))]
    official_top = official_all[: max(0, int(official_max))]
    combined = official_top + social_top
    if len(combined) < max_items:
        rest = [it for it in filtered if it not in combined]
        combined.extend(rest[: max_items - len(combined)])
    top = combined[: max(1, int(max_items))] if combined else []

    if read_full > 0 and top:
        try:
            from app.tools.adapters import _enrich_items_with_full_text

            # 官方与社媒都尽量读正文，避免摘要只停在标题级
            show_official_pre, show_social_pre = _split_buckets(top, social_q_set)
            official_budget = max(1, int(read_full * 0.6))
            social_budget = max(1, int(read_full) - official_budget)
            prefer = (
                show_official_pre[:official_budget] + show_social_pre[:social_budget]
            )
            # 配额未用满时用其余条目补齐
            if len(prefer) < read_full:
                rest = [it for it in top if it not in prefer]
                prefer.extend(rest[: read_full - len(prefer)])
            await _enrich_items_with_full_text(prefer, len(prefer))
            for it in prefer:
                full = str(it.get("full_text") or "").strip()
                if full:
                    # 保留足够正文供内容级摘要；报告侧仍只写归纳不贴原文
                    it["content"] = _clip(full, 1500)
        except Exception as exc:
            logger.warning("carbon deep-research read_full failed: %s", exc)

    show_official, show_social = _split_buckets(top, social_q_set)
    show_official = await _llm_filter_informative(
        show_official,
        industry_label=industry_label,
        compliance_year=compliance_year,
        bucket="官方/行业",
    )
    show_social = await _llm_filter_informative(
        show_social,
        industry_label=industry_label,
        compliance_year=compliance_year,
        bucket="社媒/观点",
    )
    # 来源列表也只保留有信息量条目
    top = show_official + show_social

    if not top:
        summary_md = (
            f"### 官方与行业政策要点摘要（面向「{industry_label}」控排企业）\n\n"
            "本次未获取到（检索命中多为标题党或无正文，已过滤）。\n\n"
            f"### 社媒与市场情绪摘要（面向「{industry_label}」+ 双碳）\n\n"
            "本次未获取到。"
        )
        return {
            "ok": False,
            "mode": "deep_research",
            "queried_at": queried_at,
            "queries": queries,
            "sources": [],
            "social_sources": [],
            "summary_md": summary_md,
            "error": "no_informative_results",
        }

    digest = await _llm_digest_md(
        industry_label=industry_label,
        compliance_year=compliance_year,
        official=show_official,
        social=show_social,
    )
    if not digest:
        digest = _rule_digest_md(
            industry_label=industry_label,
            official=show_official,
            social=show_social,
        )

    meta = ""
    summary_md = (meta + digest).strip()

    sources: list[dict[str, Any]] = []
    social_sources: list[dict[str, Any]] = []
    for it in top:
        url = it.get("url")
        if not url:
            continue
        row = {
            "title": it.get("title") or url,
            "url": url,
            "platform": it.get("platform"),
        }
        sources.append(row)
        if _is_social_item(it, social_q_set):
            social_sources.append(row)
    return {
        "ok": True,
        "mode": "deep_research",
        "queried_at": queried_at,
        "queries": queries,
        "sources": sources,
        "social_sources": social_sources,
        "summary_md": summary_md,
        "error": None,
    }
