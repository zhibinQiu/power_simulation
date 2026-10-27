# -*- coding: utf-8 -*-
"""四大控排行业定点数据源（火电 / 钢铁 / 水泥 / 电解铝）。

用途：为「履约综合分析」的「政策与合规要点」「社媒观点与市场情绪」两章提供
可核验的真实来源，替代不可用的 SearXNG / 官网回退垫片。

行业键与 defaults.INDUSTRY_LABELS 一致：power / steel / cement / aluminum。

来源清单（2026-10-27 逐站 HTTP 实测：能拿到日期化文章链接 + 正文才算可用）
------------------------------------------------------------------------
共用官方源（四行业都取）
  - 生态环境部   www.mee.gov.cn/ywgz/ydqhbh/wsqtkz/    静态 HTML
  - 上海环交所   /xwzx/tzgg/ · /xwzx/zcdt/ · /tpfjy/fg/gjzc/
行业专有源
  火电 power    国家能源局 www.nea.gov.cn（首页静态列表）
                中国电力报 www.cpnn.com.cn
  钢铁 steel    工信部原材料司 miit.gov.cn/jgsj/ycls/
  水泥 cement   中国建筑材料联合会 www.cbmf.org/sy/gg/
                中国水泥网 www.ccement.com/news/list/{announce,replacement,5001}.html
                工信部原材料司
  电解铝 aluminum 工信部原材料司
情绪/价格侧（社媒章补充）
  火电/钢铁     中国煤炭市场网 www.cctd.com.cn（电煤、焦煤长协、煤价）
  水泥          中国水泥网水泥频道（价格动态、错峰生产）
  电解铝        中国有色金属报 www.cnmn.com.cn（沪铝价格评论、行业动态）
  四行业        财联社滚动电报（签名接口）

已实测不可用、不要再加的源
  - 中国钢铁工业协会：门户 SPA，getIndexArticleList 恒返回 {"code":301}
  - 中国水泥协会 chinacements.com：502
  - 数字水泥网 dcement.com：948 字节 JS 壳
  - 中国有色金属工业协会 chinania.org.cn：3.4KB 空壳；alu.smm.cn SSL 断连
  - 中电联 cec.org.cn：SPA（detail/index.html?3-xxx）
  - 国家发改委 / 北京绿色交易所 / 中国环境报：栏目页 JS 渲染
  - 东方财富股吧：接口对未登录请求返回 re:[]
  - 财联社检索接口：GET 405 / POST 404 / errno 50101

设计约束
  - 只做「取回条目」，不做摘要；摘要统一由 policy_research._llm_digest_md 生成，
    item 契约与 SearXNG 路径一致：
    {"title", "url", "content", "platform", "published_at", "source"}
  - 单源失败只记 errors，不抛异常；抓不到就返回空列表，不做无关条目兜底。
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import urllib.parse
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
_TIMEOUT = 20.0

INDUSTRY_LABELS = {
    "power": "火电",
    "steel": "钢铁",
    "cement": "水泥",
    "aluminum": "电解铝",
}

# 政策类标题必须命中其中之一，否则视为噪声（栏目页里混有大量无关条目）
_COMMON_POLICY_KW = (
    "碳", "配额", "排放", "CCER", "自愿减排", "履约", "清缴", "交易",
    "方法学", "核算", "核查", "节能", "降碳", "双碳", "碳足迹",
)

# 行业差异化关键词：policy 用于官方源过滤，social 用于情绪/快讯过滤，
# strong/medium 只用于排序（配额总量、分配方案这类文件优先级最高）。
_INDUSTRY_KW: dict[str, dict[str, tuple[str, ...]]] = {
    "power": {
        "policy": ("电力", "火电", "煤电", "发电", "电价", "绿证", "绿电", "并网", "机组", "能源"),
        "social": (
            "碳市场", "碳交易", "碳价", "碳配额", "碳履约", "履约期", "清缴", "结转",
            "配额", "CCER", "自愿减排", "碳排放", "碳达峰", "碳中和", "碳关税", "CBAM",
            "火电", "煤电", "电价", "电煤", "动力煤", "煤价", "长协", "绿证", "绿电", "机组",
        ),
        "strong": ("火电", "煤电", "发电行业", "配额总量", "分配方案", "清缴", "结转"),
        "medium": ("碳市场", "CCER", "自愿减排", "核查", "核算", "配额", "电价", "绿证"),
    },
    "steel": {
        "policy": ("钢铁", "钢", "产能置换", "焦化", "超低排放", "高炉", "电炉"),
        "social": (
            "碳市场", "碳交易", "碳价", "碳配额", "碳履约", "履约期", "清缴", "结转",
            "配额", "CCER", "自愿减排", "碳排放", "碳达峰", "碳中和", "碳关税", "CBAM",
            "钢铁", "钢材", "钢价", "粗钢", "高炉", "电炉", "限产", "焦炭", "焦煤",
        ),
        "strong": ("钢铁", "配额总量", "分配方案", "清缴", "结转", "产能置换"),
        "medium": ("碳市场", "CCER", "自愿减排", "核查", "核算", "配额", "超低排放"),
    },
    "cement": {
        "policy": ("水泥", "熟料", "建材", "产能置换", "错峰", "超低排放", "粉磨"),
        "social": (
            "碳市场", "碳交易", "碳价", "碳配额", "碳履约", "履约期", "清缴", "结转",
            "配额", "CCER", "自愿减排", "碳排放", "碳达峰", "碳中和", "碳关税", "CBAM",
            "水泥", "熟料", "水泥价格", "错峰", "停窑", "产能置换", "建材",
        ),
        "strong": ("水泥", "熟料", "配额总量", "分配方案", "清缴", "结转", "错峰"),
        "medium": ("碳市场", "CCER", "自愿减排", "核查", "核算", "配额", "产能置换"),
    },
    "aluminum": {
        "policy": ("铝", "电解铝", "氧化铝", "有色", "产能置换", "电解", "预焙阳极"),
        "social": (
            "碳市场", "碳交易", "碳价", "碳配额", "碳履约", "履约期", "清缴", "结转",
            "配额", "CCER", "自愿减排", "碳排放", "碳达峰", "碳中和", "碳关税", "CBAM",
            "电解铝", "氧化铝", "铝价", "沪铝", "铝锭", "有色", "预焙阳极",
        ),
        "strong": ("电解铝", "铝冶炼", "配额总量", "分配方案", "清缴", "结转"),
        "medium": ("碳市场", "CCER", "自愿减排", "核查", "核算", "配额", "氧化铝"),
    },
}

# 标题级噪声：上市公司公告流水、财报、人事等，与政策/情绪无关
_DENY_KW = (
    "股东会", "股东大会", "董事会决议", "监事会", "季度报告", "半年度报告",
    "年度报告", "财务资料", "法律意见书", "业绩预告", "回购", "减持", "增持",
    "人事变动", "聘任", "辞职", "调研", "投资者关系", "趣事", "之趣",
)

# 行业新闻站（非政务站）额外的噪声：党建、文体、表彰类，不属于市场观点
_SOCIAL_DENY_KW = _DENY_KW + (
    "党建", "党委", "理论学习", "中心组", "文艺", "竞赛", "技能大赛", "表彰",
    "荣获", "事迹", "侧记", "速览", "成绩单", "读书", "走访", "慰问", "招聘",
    "工会", "团委", "主题教育", "党史", "趣事", "之趣", "杂谈", "随笔",
)

# 行业锚点词：行业专有源必须命中其一，否则视为跨行业串味
# （例：铝冶炼取工信部原材料司时，必须排除「钢铁行业产能置换」这类条目）
_INDUSTRY_ANCHOR: dict[str, tuple[str, ...]] = {
    # 火电把「煤」纳入锚点：电煤/动力煤价格是火电成本侧的核心情绪来源
    "power": ("电力", "火电", "煤电", "发电", "机组", "电价", "电煤", "煤价", "动力煤", "长协", "煤炭"),
    "steel": ("钢",),
    "cement": ("水泥", "熟料", "建材"),
    "aluminum": ("铝", "有色"),
}

# 情绪类硬词：行业新闻站标题必须命中其一，否则只是企业动态/会议报道
_SENTIMENT_HARD_KW: dict[str, tuple[str, ...]] = {
    "power": (
        "价格", "煤价", "电价", "长协", "库存", "产量", "供需", "日耗", "电厂",
        "碳", "配额", "排放", "交易", "绿证", "机组", "利润", "成本", "开工",
    ),
    "steel": (
        "价格", "钢价", "库存", "产量", "限产", "成本", "利润", "碳", "配额",
        "排放", "交易", "开工", "检修", "长协", "需求", "出口",
    ),
    "cement": (
        "价格", "涨价", "跌价", "产能", "错峰", "停窑", "限产", "库存", "销量",
        "碳", "配额", "排放", "超低", "置换", "成本", "利润", "开工", "供需",
    ),
    "aluminum": (
        "价格", "铝价", "沪铝", "库存", "产量", "产能", "成本", "利润", "碳",
        "配额", "排放", "交易", "开工", "氧化铝", "铝土矿", "升贴水",
    ),
}

# 正文噪声段（版权声明、免责声明等），抓正文时剔除
_BODY_NOISE = ("版权所有", "免责声明", "未经", "许可", "不得转载", "ICP备", "公网安备", "联系我们")


def resolve_industry(industry: str = "", label: str = "") -> str:
    """把行业键或中文名归一成 industry key；未知时回退 steel（历史默认）。"""
    key = str(industry or "").strip().lower()
    if key in INDUSTRY_LABELS:
        return key
    text = str(label or industry or "").strip()
    for k, zh in INDUSTRY_LABELS.items():
        if zh and zh in text:
            return k
    if "铝" in text:
        return "aluminum"
    if "电" in text:
        return "power"
    if "水泥" in text or "建材" in text:
        return "cement"
    if "钢" in text:
        return "steel"
    return "steel"


def industry_label_of(industry: str) -> str:
    return INDUSTRY_LABELS.get(str(industry or ""), "控排企业")


# --------------------------------------------------------------------------
# 源定义
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class PageSource:
    """一个静态列表页数据源。"""

    platform: str            # 报告「信息来源」里显示的平台名
    url: str                 # 列表页地址
    source: str              # 内部来源码（mee/cneeex/nea/cpnn/miit/cbmf/ccement/cnmn/cctd）
    url_pattern: str = ""    # 只保留 href 匹配该正则的链接（滤掉导航/栏目入口）
    deny_kw: tuple[str, ...] = ()
    social: bool = False     # True = 情绪/行情侧来源（额外套行业硬词过滤）


_CNEEEX_PAGES = (
    PageSource("环交所通知公告", "https://www.cneeex.com/xwzx/tzgg/", "cneeex",
               url_pattern=r"/c/\d{4}-\d{2}-\d{2}/"),
    PageSource("环交所政策动态", "https://www.cneeex.com/xwzx/zcdt/", "cneeex",
               url_pattern=r"/c/\d{4}-\d{2}-\d{2}/"),
    PageSource("环交所国家政策", "https://www.cneeex.com/tpfjy/fg/gjzc/", "cneeex",
               url_pattern=r"/c/\d{4}-\d{2}-\d{2}/"),
)

# 四行业共用官方源
_COMMON_OFFICIAL = (
    PageSource("生态环境部", "https://www.mee.gov.cn/ywgz/ydqhbh/wsqtkz/", "mee"),
    *_CNEEEX_PAGES,
)

_MIIT = PageSource(
    "工信部原材料司", "https://www.miit.gov.cn/jgsj/ycls/index.html", "miit",
    url_pattern=r"/art/20\d{2}/art_[0-9a-f]+\.html",
    deny_kw=_DENY_KW,
)

# 行业专有官方源
_INDUSTRY_OFFICIAL_EXTRA: dict[str, tuple[PageSource, ...]] = {
    "power": (
        PageSource(
            "国家能源局", "https://www.nea.gov.cn/", "nea",
            url_pattern=r"20\d{6}/[0-9a-f]{16,}/c\.html",
        ),
        PageSource(
            "中国电力报", "https://www.cpnn.com.cn/", "cpnn",
            url_pattern=r"t20\d{6}_\d+\.html",
        ),
    ),
    "steel": (_MIIT,),
    "cement": (
        PageSource(
            "建材联合会", "https://www.cbmf.org/sy/gg/", "cbmf",
            url_pattern=r"/c/20\d{2}/\d{2}/\d{2}/\d+\.shtml",
        ),
        PageSource(
            "中国水泥网·公告", "https://www.ccement.com/news/list/announce.html", "ccement",
            url_pattern=r"/news/content/\d+", deny_kw=_DENY_KW,
        ),
        PageSource(
            "中国水泥网·产能置换", "https://www.ccement.com/news/list/replacement.html", "ccement",
            url_pattern=r"/news/content/\d+", deny_kw=_DENY_KW,
        ),
        _MIIT,
    ),
    "aluminum": (_MIIT,),
}

# 情绪/价格侧行业源（与财联社一起构成「社媒观点与市场情绪」章）
_INDUSTRY_SENTIMENT_EXTRA: dict[str, tuple[PageSource, ...]] = {
    "power": (
        PageSource(
            "中国煤炭市场网", "https://www.cctd.com.cn/", "cctd",
            url_pattern=r"show-\d+-\d+-1\.html", deny_kw=_SOCIAL_DENY_KW, social=True,
        ),
    ),
    "steel": (
        PageSource(
            "中国煤炭市场网", "https://www.cctd.com.cn/", "cctd",
            url_pattern=r"show-\d+-\d+-1\.html", deny_kw=_SOCIAL_DENY_KW, social=True,
        ),
    ),
    "cement": (
        PageSource(
            "中国水泥网", "https://www.ccement.com/news/list/5001.html", "ccement",
            url_pattern=r"/news/content/\d+", deny_kw=_SOCIAL_DENY_KW, social=True,
        ),
    ),
    "aluminum": (
        PageSource(
            "中国有色金属报", "https://www.cnmn.com.cn/", "cnmn",
            url_pattern=r"ShowNews1\.aspx\?id=\d+", deny_kw=_SOCIAL_DENY_KW, social=True,
        ),
    ),
}


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------
def _today_prefix() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d")


def _clean(text: str) -> str:
    t = re.sub(r"<[^>]+>", "", text or "")
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"')
    t = t.replace("&lt;", "<").replace("&gt;", ">").replace("&#32;", " ")
    t = t.replace("&emsp;", " ").replace("&mdash;", "—")
    return re.sub(r"\s+", " ", t).strip()


def _match_kw(text: str, kws: tuple[str, ...]) -> bool:
    return any(k in text for k in kws)


_DATE_RE = re.compile(r"(?<!\d)(t?20\d{6})(?!\d)|/(20\d{2})[-/](\d{2})[-/](\d{2})/")


def _valid_date(text: str) -> str:
    """校验并规范化 YYYY-MM-DD；非法返回空串（数字型 id 常被误判成日期）。"""
    from datetime import datetime

    try:
        return datetime.strptime(text, "%Y-%m-%d").strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return ""


def _date_from_href(href: str) -> str:
    """从链接里推发布日期；推不出就返回空串（排序时靠后）。"""
    m = _DATE_RE.search(href or "")
    if m:
        if m.group(1):
            raw = m.group(1).lstrip("t")
            date = _valid_date(f"{raw[:4]}-{raw[4:6]}-{raw[6:]}")
        else:
            date = _valid_date(f"{m.group(2)}-{m.group(3)}-{m.group(4)}")
        if date:
            return date
    # 只有年份的链接（如工信部 /art/2026/art_xxx.html）：给个年级日期，
    # 至少能把 2014 年的历史公示排到后面去
    m_year = re.search(r"/(20\d{2})/", href or "")
    return m_year.group(1) if m_year else ""


def _relevance(it: dict[str, Any], strong: tuple[str, ...], medium: tuple[str, ...]) -> int:
    text = f"{it.get('title') or ''} {it.get('content') or ''}"
    return sum(2 for k in strong if k in text) + sum(1 for k in medium if k in text)


async def _fetch_html(url: str, *, referer: str = "") -> str:
    import httpx

    headers = {"User-Agent": _UA, "Accept-Language": "zh-CN,zh;q=0.9"}
    if referer:
        headers["Referer"] = referer
    async with httpx.AsyncClient(
        timeout=_TIMEOUT, follow_redirects=True, headers=headers
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


# --------------------------------------------------------------------------
# 列表页解析
# --------------------------------------------------------------------------
_ANCHOR_RE = re.compile(r'<a\s+[^>]*href="([^"]+)"[^>]*>([^<]{6,140})</a>', re.I)


def parse_page_anchors(
    html: str,
    base_url: str,
    *,
    src: PageSource,
    kws: tuple[str, ...],
    must_kw: tuple[str, ...] = (),
    require_any: tuple[str, ...] = (),
    limit: int = 12,
) -> list[dict[str, Any]]:
    """解析列表页 <a>，按关键词/正则过滤，产出标准 item。

    三层过滤（顺序即成本从低到高）：
    1. url_pattern —— 滤掉导航/栏目入口，只留真实文章页；
    2. must_kw     —— 行业锚点，防止跨行业串味（如铝行业源里混入钢铁文件）；
    3. kws / require_any —— 主题词，保证与碳市场或行情相关。
    """
    items: list[dict[str, Any]] = []
    seen: set[str] = set()      # 标题去重
    seen_url: set[str] = set()  # URL 去重：同篇文章常有完整标题与截断标题两个入口
    for href, raw_title in _ANCHOR_RE.findall(html or ""):
        title = _clean(raw_title)
        if not title or len(title) < 8 or title in seen:
            continue
        href = href.strip()
        if not href or href.startswith(("javascript", "#", "mailto")):
            continue
        if src.url_pattern and not re.search(src.url_pattern, href):
            continue
        if src.deny_kw and _match_kw(title, src.deny_kw):
            continue
        if must_kw and not _match_kw(title, must_kw):
            continue
        if not _match_kw(title, kws):
            continue
        if require_any and not _match_kw(title, require_any):
            continue
        url = urljoin(base_url, href)
        if not url.startswith("http") or url in seen_url:
            continue
        seen.add(title)
        seen_url.add(url)
        items.append(
            {
                "title": title,
                "url": url,
                "content": "",
                "platform": src.platform,
                "published_at": _date_from_href(href),
                "source": src.source,
            }
        )
        if len(items) >= limit:
            break
    return items


async def fetch_page_source(
    src: PageSource,
    *,
    kws: tuple[str, ...],
    must_kw: tuple[str, ...] = (),
    require_any: tuple[str, ...] = (),
    limit: int = 12,
) -> list[dict[str, Any]]:
    html = await _fetch_html(src.url)
    items = parse_page_anchors(
        html, src.url, src=src, kws=kws, must_kw=must_kw,
        require_any=require_any, limit=limit,
    )
    logger.info("industry sources: %s items=%d", src.platform, len(items))
    return items


# --------------------------------------------------------------------------
# 正文补全
# --------------------------------------------------------------------------
_META_DESC_RE = (
    re.compile(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']{40,})["\']', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']{40,})["\'][^>]+name=["\']description["\']', re.I),
    re.compile(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']{40,})["\']', re.I),
)


def _meta_description(html: str) -> str:
    """取 <meta description>：有些站点（如中国煤炭市场网）正文不放在 <p> 里，
    但 meta 描述就是首段摘要，作为正文兜底比整页去标签可靠。"""
    for pat in _META_DESC_RE:
        m = pat.search(html or "")
        if m:
            text = _clean(m.group(1))
            if len(text) >= 40:
                return text
    return ""


async def _fetch_article_text(url: str, limit: int = 1200) -> str:
    """抓文章页正文（段落级）。

    摘要模型要求「内容级归纳」，只有标题会被判定无依据而输出「本次未获取到」，
    因此条目必须补正文。抽取顺序：
    1. <p> 段落（并剔除版权/免责声明等噪声段）；
    2. 段落不足时用 <meta description>（不少政企站的正文不进 <p>）；
    3. 仍不足才整页去标签兜底。
    """
    html = await _fetch_html(url)
    stripped = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    paras = re.findall(r"(?is)<p[^>]*>(.*?)</p>", stripped)
    cleaned = [_clean(p) for p in paras]
    cleaned = [t for t in cleaned if len(t) >= 15 and not _match_kw(t, _BODY_NOISE)]
    text = " ".join(cleaned)

    if len(text) < 200:
        meta = _meta_description(html)
        if len(meta) > len(text):
            text = (meta + " " + text).strip()
    if len(text) < 120:
        text = _clean(stripped)
    return text[:limit]


async def enrich_articles(
    items: list[dict[str, Any]], *, limit: int = 6, per_limit: int = 1200
) -> list[dict[str, Any]]:
    """并发抓条目正文回填 content；失败的单条忽略，不影响整体。"""
    targets = [
        it for it in items
        if str(it.get("url") or "").startswith("http")
        and len(str(it.get("content") or "")) < 200
    ][:limit]
    if not targets:
        return items
    sem = asyncio.Semaphore(6)

    async def _one(it: dict[str, Any]) -> None:
        async with sem:
            try:
                text = await _fetch_article_text(str(it["url"]), per_limit)
            except Exception as exc:  # noqa: BLE001
                logger.debug("industry sources: article fetch failed %s: %s", it.get("url"), exc)
                return
            if text and len(text) > 60:
                it["content"] = text

    await asyncio.gather(*(_one(it) for it in targets))
    filled = sum(1 for it in targets if str(it.get("content") or "").strip())
    logger.info("industry sources: 正文抓取 %d/%d", filled, len(targets))
    return items


# 兼容旧调用名
enrich_official_articles = enrich_articles


# --------------------------------------------------------------------------
# 社媒：财联社电报（签名接口，按行业关键词过滤）
# --------------------------------------------------------------------------
_CLS_API = "https://www.cls.cn/v1/roll/get_roll_list"


def _cls_sign(params: dict[str, str]) -> str:
    """财联社 web 端签名：md5(sha1(sorted_query_string))。"""
    q = urllib.parse.urlencode(sorted(params.items()))
    return hashlib.md5(hashlib.sha1(q.encode()).hexdigest().encode()).hexdigest()


def _fmt_ctime(value: Any) -> str:
    """财联社的 ctime 是 Unix 秒级时间戳，转成本地可读时间。"""
    from datetime import datetime

    try:
        ts = int(str(value).strip())
    except (TypeError, ValueError):
        return str(value or "")[:19]
    if ts <= 0:
        return ""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


async def fetch_cls(
    limit: int = 15,
    *,
    social_kw: tuple[str, ...] = (),
    max_pages: int = 8,
) -> list[dict[str, Any]]:
    """从财联社滚动电报里筛出本行业相关快讯。

    财联社没有可用的检索接口（非登录态 GET 405 / POST 404），只能读滚动列表，
    因此需要深翻页：实测 240 条里通常只有个位数命中，翻 1-2 页几乎必然为空。
    抓不到就返回空列表 —— 不做「无关快讯兜底」。
    """
    import httpx

    kws = social_kw or _INDUSTRY_KW["steel"]["social"]
    out: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    last_time = ""
    total_scanned = 0
    async with httpx.AsyncClient(
        timeout=_TIMEOUT, follow_redirects=True,
        headers={"User-Agent": _UA, "Referer": "https://www.cls.cn/telegraph"},
    ) as client:
        for _ in range(max(1, max_pages)):
            params = {
                "app": "CailianpressWeb", "os": "web", "sv": "8.4.6",
                "rn": "30", "last_time": last_time,
            }
            if last_time:
                # 不带 refresh_type 时接口会 inclusive 地重复返回同一页，翻不动
                params["refresh_type"] = "1"
            params["sign"] = _cls_sign(params)
            try:
                resp = await client.get(_CLS_API, params=params)
                payload = resp.json()
            except Exception as exc:  # noqa: BLE001
                logger.warning("industry sources: cls page failed: %s", exc)
                break
            data = (payload or {}).get("data") or {}
            roll = data.get("roll_data") or data.get("rollData") or []
            if not roll:
                break
            for row in roll:
                total_scanned += 1
                cid = str(row.get("id") or row.get("ctime") or "")
                if cid and cid in seen_ids:
                    continue
                text = _clean(str(row.get("title") or "")) or _clean(str(row.get("content") or ""))
                body = _clean(str(row.get("content") or row.get("brief") or ""))
                if not text or not _match_kw(f"{text} {body}", kws):
                    continue
                if cid:
                    seen_ids.add(cid)
                out.append(
                    {
                        "title": text[:90],
                        "url": f"https://www.cls.cn/detail/{cid}" if cid else "https://www.cls.cn/telegraph",
                        "content": body[:600],
                        "platform": "财联社",
                        "published_at": _fmt_ctime(row.get("ctime")),
                        "source": "cls",
                    }
                )
                if len(out) >= limit:
                    logger.info(
                        "industry sources: cls items=%d scanned=%d", len(out), total_scanned
                    )
                    return out
            last_time = str(roll[-1].get("ctime") or "")
            if not last_time:
                break
    logger.info(
        "industry sources: cls items=%d scanned=%d（无行业相关快讯时不兜底）",
        len(out), total_scanned,
    )
    return out


# --------------------------------------------------------------------------
# 组合入口
# --------------------------------------------------------------------------
def _interleave(rows: list[dict[str, Any]], cap: int) -> list[dict[str, Any]]:
    """按来源轮流取样，保证各来源都有代表，避免单一源吃满配额。"""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for it in rows:
        buckets.setdefault(str(it.get("source") or "other"), []).append(it)
    out_rows: list[dict[str, Any]] = []
    depth = 0
    while len(out_rows) < cap and any(len(v) > depth for v in buckets.values()):
        for v in buckets.values():
            if depth < len(v):
                out_rows.append(v[depth])
                if len(out_rows) >= cap:
                    break
        depth += 1
    return out_rows


def _drop_cross_industry(
    items: list[dict[str, Any]], *, key: str, anchor: tuple[str, ...]
) -> list[dict[str, Any]]:
    """共用源（生态环境部/环交所）里剔除只对别的行业生效的文件。

    典型情况：环交所政策栏目会同时挂「发电行业配额分配方案」和
    「钢铁、水泥、铝冶炼行业配额总量和分配方案」。对非火电行业来说，
    前者是无关文件，但它又不含行业锚点词，靠关键词过滤拦不住。
    """
    if key == "power":
        return items
    out: list[dict[str, Any]] = []
    for it in items:
        title = str(it.get("title") or "")
        if ("发电行业" in title or "发电设施" in title) and not _match_kw(title, anchor):
            continue
        out.append(it)
    return out


async def fetch_industry_bundle(
    *,
    industry: str = "",
    industry_label: str = "",
    official_max: int = 8,
    social_max: int = 10,
) -> dict[str, Any]:
    """并行取回本行业官方源 + 情绪源，返回统一契约。"""
    key = resolve_industry(industry, industry_label)
    label = industry_label_of(key)
    kws = _INDUSTRY_KW.get(key) or _INDUSTRY_KW["steel"]
    errors: list[str] = []

    official_sources = _COMMON_OFFICIAL + _INDUSTRY_OFFICIAL_EXTRA.get(key, ())
    sentiment_sources = _INDUSTRY_SENTIMENT_EXTRA.get(key, ())

    official: list[dict[str, Any]] = []
    social: list[dict[str, Any]] = []

    anchor = _INDUSTRY_ANCHOR.get(key, ())
    hard_kw = _SENTIMENT_HARD_KW.get(key, ())

    # 官方列表页并发抓取。共用源（生态环境部/环交所）不加行业锚点，
    # 因为配额方案、方法学这类文件本身就跨行业适用；行业专有源必须带锚点。
    official_tasks = []
    for src in official_sources:
        is_extra = src not in _COMMON_OFFICIAL
        official_tasks.append(
            fetch_page_source(
                src,
                kws=_COMMON_POLICY_KW + kws["policy"],
                must_kw=anchor if is_extra else (),
                limit=official_max,
            )
        )
    for src, res in zip(official_sources, await asyncio.gather(*official_tasks, return_exceptions=True)):
        if isinstance(res, Exception):
            errors.append(f"{src.platform}：{type(res).__name__}")
            continue
        official.extend(res or [])

    # 情绪侧：财联社 + 行业情绪页（行业页要求同时命中行业锚点与行情硬词）
    s_tasks = [fetch_cls(limit=social_max, social_kw=kws["social"])]
    s_tasks += [
        fetch_page_source(
            src, kws=kws["social"], must_kw=anchor, require_any=hard_kw, limit=social_max
        )
        for src in sentiment_sources
    ]
    s_results = await asyncio.gather(*s_tasks, return_exceptions=True)
    for idx, res in enumerate(s_results):
        name = "财联社" if idx == 0 else sentiment_sources[idx - 1].platform
        if isinstance(res, Exception):
            errors.append(f"{name}：{type(res).__name__}")
            continue
        social.extend(res or [])

    # 官方优先：配额总量/分配方案/清缴等强相关词加权；
    # 同权重内按发布日期倒序（两次稳定排序实现，空日期自然排到末尾）
    official = _drop_cross_industry(official, key=key, anchor=anchor)
    official.sort(key=lambda x: str(x.get("published_at") or ""), reverse=True)
    official.sort(key=lambda x: -_relevance(x, kws["strong"], kws["medium"]))
    social.sort(key=lambda x: str(x.get("published_at") or ""), reverse=True)

    official_final = _interleave(official, official_max)
    social_final = _interleave(social, social_max)

    # 补正文（官方与情绪页都需要，否则摘要模型会判定无依据）
    await enrich_articles(official_final, limit=6)
    await enrich_articles(social_final, limit=6)

    return {
        "ok": bool(official_final or social_final),
        "industry": key,
        "industry_label": label,
        "official": official_final,
        "social": social_final,
        "errors": errors,
        "fetched_at": _today_prefix(),
    }


# 旧接口兼容（钢铁专用调用点）
async def fetch_steel_bundle(*, official_max: int = 8, social_max: int = 10) -> dict[str, Any]:
    return await fetch_industry_bundle(
        industry="steel", official_max=official_max, social_max=social_max
    )
