# -*- coding: utf-8 -*-
"""双碳政策动态摘要：官方政策条目 + 行业基线 + 我方台账 → AI 政策摘要正文。

与另外两类报告的分工：
- 履约综合分析的主体是企业（缺口、三档策略、减排路径）；
- 碳交易简报的主体是市场（价格、成交、交易窗口），不谈政策细节；
- 本模块的主体是政策（发文机关、日期、效力、对本行业与本企业的含义），不预测碳价。

关键设计：
1. 政策条目只取官方源（fetch_official_bundle），不混入财联社快讯与行情页；
2. 行业参数（基准值/平衡值/核算单元/覆盖气体）是**代码常量**，不依赖检索，
   避免模型把别的行业的参数写到本行业名下；
3. 条目必须带发布日期与发布机构，日期只精确到月时不得补全为具体日；
4. 窗口内没有新增文件时，底稿显式写「未检索到」，不允许用往年文件充数。
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any

from .compliance_analysis_report import (
    ContentFn,
    ProgressFn,
    _fmt_wan,
    _parse_ai_context,
    _report_header,
    _strip_sources_section,
    report_heading_of,
    synthesize_compliance_analysis_stream,
)
from .market_brief_report import _deadline_info, _enterprise_pack, _f

logger = logging.getLogger(__name__)

# 政策观察窗：政策发布频率远低于行情，60 天常常空窗，默认取 90 天
DEFAULT_WINDOW_DAYS = 90

# 政策口径的行业名称：系统内部 key 仍是 aluminum，正文一律写「铝冶炼」
POLICY_INDUSTRY_LABEL = {
    "power": "火电",
    "steel": "钢铁",
    "cement": "水泥",
    "aluminum": "铝冶炼",
}

# 四行业一致的规则（写入底稿「共同规则」，模型只能引用不得改写）
COMMON_RULES: tuple[str, ...] = (
    "配额发放：预分配 + 核定分配两阶段，预分配比例原则上为上一年度经核查排放量的 50%"
    "（2023、2024 年度方案为 70%）",
    "纳管门槛：年度温室气体排放量 2.6 万吨二氧化碳当量（含）以上的重点排放单位",
    "清缴时限：每年 12 月 31 日前完成上一年度配额清缴",
    "抵销机制：可使用 CCER 抵销配额清缴，抵销比例不超过应清缴配额量的 5%",
    "排放范围：只覆盖化石燃料燃烧、工业过程和含碳产品隐含排放产生的直接排放，"
    "不覆盖因消耗电力、热力导致的间接排放",
    "系数法行业（钢铁、水泥、铝冶炼）：配额盈缺率通过强度系数封顶控制在 ±3% 以内",
    "特殊情形：配额核定前关停、当年度新投产的机组/生产线/工序，按等量分配处理",
)

# 行业基线：数值来自《全国碳排放权交易市场 2025、2026 年度发电行业以及 2026 年度
# 钢铁、水泥、铝冶炼行业配额总量和分配方案》及其配套的平衡值公告。
INDUSTRY_BASELINE: dict[str, dict[str, Any]] = {
    "power": {
        "method": "碳排放强度基准法（发电与供热分别核定）",
        "unit": "发电机组",
        "gas": "二氧化碳（CO₂）",
        "params": (
            "2026 年度燃煤发电基准值：300MW 等级以上常规燃煤机组 0.7894 tCO₂/MWh、"
            "300MW 等级及以下常规燃煤机组 0.7985 tCO₂/MWh、非常规燃煤机组 0.8080 tCO₂/MWh",
            "2026 年度燃气机组发电基准值 0.3288 tCO₂/MWh，与 2025 年度持平",
            "2026 年度供热基准值：燃煤机组 0.1021 tCO₂/GJ、燃气机组 0.0533 tCO₂/GJ",
            "常规燃煤机组调峰修正系数：负荷率低于 50% 时按新公式补偿，50% 及以上取 1"
            "（2023、2024 年度方案的适用区间为低于 65%）",
            "发电企业层面配额履约缺口率上限为 20%",
        ),
        "special": (
            "掺烧生物质（含垃圾、污泥）热量年均占比超过 20% 的机组",
            "混烧自产二次能源热量年均占比超过 10% 的化石燃料燃烧发电机组",
            "仅使用煤层气、焦炉煤气、高炉煤气、转炉煤气等特殊化石燃料的机组",
            "承担应急备用保障功能的机组、燃油机组、整体煤气化联合循环发电机组等",
        ),
        "focus": "煤电节能降碳改造、灵活性改造与深度调峰、绿电绿证、电煤长协",
    },
    "steel": {
        "method": "碳排放强度系数法",
        "unit": "企业法人或联合生产企业整体核定，重点评价工序为炼铁与烧结",
        "gas": "二氧化碳（CO₂）",
        "params": (
            "最近公布的行业平衡值（2025 年度）为 0.95 tCO₂e/t 炼铁工序产品产量，"
            "2026 年度平衡值在年度核查完成后另行公布",
            "配额 = 工序碳排放量 ×（1 + 强度系数），强度偏离度 X 在 ±20% 以内按 0.15X "
            "线性调整，超出部分封顶为 ±3%",
            "强度评价指标 =（炼铁工序 + 烧结工序）排放总量 ÷ 炼铁工序产品产量",
        ),
        "special": (
            "采用富氢碳循环氧气高炉低碳冶金工艺的钢铁长流程企业，按等量分配处理",
        ),
        "focus": "产能置换、超低排放改造、废钢比提升、富氢碳循环氧气高炉",
    },
    "cement": {
        "method": "碳排放强度系数法",
        "unit": "熟料生产线（多条生产线分别计算后汇总）",
        "gas": "二氧化碳（CO₂）",
        "params": (
            "最近公布的行业平衡值（2025 年度）为 0.80 tCO₂e/t 熟料，"
            "2026 年度平衡值在年度核查完成后另行公布",
            "配额 = 熟料产量 × 平衡值 ×（1 + 强度系数），强度偏离度同样按 ±20% 线性、"
            "超出部分封顶 ±3%",
        ),
        "special": (
            "当年度电石渣替代率超过 30% 的水泥熟料生产线（2023、2024 年度方案的门槛为 15%）",
            "当年度仅生产白色硅酸盐水泥熟料的生产线",
            "石膏制硫酸副产硅酸盐水泥熟料的生产线",
        ),
        "focus": "错峰生产、产能置换、替代燃料与替代原料、能效标杆水平",
    },
    "aluminum": {
        "method": "碳排放强度系数法",
        "unit": "铝电解工序",
        "gas": "二氧化碳（CO₂）、四氟化碳（CF₄）、六氟化二碳（C₂F₆）——四行业中唯一覆盖非 CO₂ 气体",
        "params": (
            "最近公布的行业平衡值（2025 年度）为 1.56 tCO₂e/t 铝，"
            "2026 年度平衡值在年度核查完成后另行公布",
            "配额 = 铝产量 × 平衡值 ×（1 + 强度系数），强度偏离度按 ±20% 线性、"
            "超出部分封顶 ±3%",
            "核查需同时核算阳极效应产生的 CF₄ 与 C₂F₆，不能只算燃料燃烧排放",
        ),
        "special": (
            "当年度新投产的铝电解工序，按等量分配处理",
        ),
        "focus": "产能置换、阳极净耗与阳极效应系数、绿电占比、欧盟碳边境调节机制（CBAM）",
    },
}

# 政策文种识别：顺序即优先级（征求意见稿要优先识别，否则会被当成「办法」）
_POLICY_TYPE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("征求意见稿", ("征求意见", "公开征求", "征询意见")),
    ("法规条例", ("条例", "决定", "暂行规定")),
    ("管理办法", ("管理办法", "办法")),
    ("实施方案", ("实施方案", "工作方案", "方案")),
    ("技术指南", ("指南", "技术规范", "规范")),
    ("交易规则", ("规则", "细则")),
    ("通知", ("通知",)),
    ("公告", ("公告",)),
    ("标准", ("标准",)),
)

_UNDATED = "未标注日期"

# 边界声明判定：正文里已有其一就不再追加，避免重复刷屏
# 注意：不要放「以原文为准」——正文里几乎每段都有这句，会导致声明永远不追加
_BOUNDARY_MARKS: tuple[str, ...] = ("不构成", "仅供参考", "免责声明")


# 政策核心词：标题必须命中其一，才算政策类条目。
# 不能直接复用 industry_sources._COMMON_POLICY_KW —— 那是「行业词 OR 碳词」，
# 「建材行业揭榜挂帅项目」会因命中「建材」而被判成政策。
_POLICY_CORE_KW: tuple[str, ...] = (
    "碳", "配额", "排放", "CCER", "自愿减排", "履约", "清缴", "核算", "核查",
    "方法学", "温室气体", "节能", "降碳", "双碳", "产能置换", "超低排放",
    "错峰", "能效", "碳足迹", "交易", "绿电", "绿证",
)

# 国家级发文机关：只有这些平台发的文件才进「国家级」主表。
# 按平台判定而不是按标题里的省市名：地方工信厅的产能置换公示标题常常只有企业名，
# 而部委转发的文件也可能带省市字样，标题判不准。
_NATIONAL_ORGAN_KW: tuple[str, ...] = (
    "生态环境部", "工业和信息化部", "工信部", "国家能源局", "国家发展改革委",
    "国家发改委", "国务院", "中共中央", "财政部", "商务部", "市场监管总局",
    "国家市场监督管理总局", "国家统计局", "住房和城乡建设部", "交通运输部",
    "中国人民银行", "国家应对气候变化",
)


def _is_policy_like(item: dict[str, Any]) -> bool:
    """标题命中政策核心词、且文种是正式文件，才算政策条目。

    只看标题：正文里常混站点导航与版权声明，「建材」这类行业词也出现在
    非政策标题里，用正文会把「揭榜挂帅项目」判成政策。
    """
    title = str(item.get("title") or "")
    if not any(k in title for k in _POLICY_CORE_KW):
        return False
    return _policy_type(title) != "其他文件"


def _is_local(item: dict[str, Any]) -> bool:
    """非国家级发文机关（省市厅局、行业协会、行业媒体）一律归入地方与行业文件。"""
    plat = str(item.get("platform") or "")
    return not any(k in plat for k in _NATIONAL_ORGAN_KW)



# ---------- 条目处理 ----------


def _cut(text: Any, n: int) -> str:
    s = str(text or "").strip().replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def _policy_type(title: str) -> str:
    t = str(title or "")
    for label, kws in _POLICY_TYPE_RULES:
        if any(k in t for k in kws):
            return label
    return "其他文件"


def _effect_status(title: str) -> str:
    """只做「标题里能看出」的判定，看不出来的一律写「以原文为准」。"""
    t = str(title or "")
    # 「关于公开征求《X》意见的函」里并没有连续出现「征求意见」，
    # 单靠关键词会漏判，这里用正则兜住「征求……意见」的常见写法
    if "征求意见" in t or "公开征求" in t or re.search(r"征求[^。；]{0,40}意见", t):
        return "征求意见（未生效）"
    if "废止" in t:
        return "涉及废止"
    if "试行" in t:
        return "试行"
    return "以原文为准"


def _parse_pub(value: Any) -> tuple[date | None, bool]:
    """解析发布日期，返回 (日期, 是否精确到日)。

    数据源给的日期有三种精度：YYYY-MM-DD（精确）、YYYY-MM（当月）、YYYY（当年）。
    精度不足时取该区间第一天，并在正文里保留「仅到月」的标注，不补全为具体日。
    """
    s = str(value or "").strip()
    if not s or s == _UNDATED:
        return None, False
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), True
        except ValueError:
            return None, False
    m = re.match(r"^(\d{4})-(\d{2})$", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), 1), False
        except ValueError:
            return None, False
    m = re.match(r"^(\d{4})$", s)
    if m:
        try:
            return date(int(m.group(1)), 1, 1), False
        except ValueError:
            return None, False
    return None, False


def _date_text(value: Any) -> str:
    """发布日期展示口径：精确到日给日，只到月给月，都没有写未标注。"""
    s = str(value or "").strip()
    d, exact = _parse_pub(s)
    if d is None:
        return _UNDATED
    if exact:
        return d.isoformat()
    if re.match(r"^\d{4}-\d{2}$", s):
        return f"{s}（仅到月）"
    if re.match(r"^\d{4}$", s):
        return f"{s} 年（仅到年）"
    return d.isoformat()


def _split_items(
    items: list[dict[str, Any]], window_days: int, today: date | None = None
) -> dict[str, list[dict[str, Any]]]:
    """按窗口切分成「窗口内 / 日期待核验 / 更早存量」三组。"""
    today = today or date.today()
    start = today - timedelta(days=max(1, int(window_days)))
    in_window: list[dict[str, Any]] = []
    undated: list[dict[str, Any]] = []
    older: list[dict[str, Any]] = []

    for it in items:
        d, _exact = _parse_pub(it.get("published_at"))
        if d is None:
            undated.append(it)
        elif d >= start:
            in_window.append(dict(it, _pub_date=d))
        else:
            older.append(dict(it, _pub_date=d))

    in_window.sort(key=lambda x: x.get("_pub_date"), reverse=True)
    older.sort(key=lambda x: x.get("_pub_date"), reverse=True)
    return {"window": in_window, "undated": undated, "older": older}


# ---------- 底稿 ----------


async def build_policy_factsheet(
    db: Any,
    user_id: str,
    *,
    enterprise_id: str = "",
    compliance_year: int = 0,
    on_progress: ProgressFn | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> dict[str, Any]:
    """组装政策底稿：政策条目 → 行业基线 → 共同规则 → 我方台账 → 政策日历。"""

    def prog(p: int, msg: str) -> None:
        if on_progress:
            on_progress(p, msg)

    year = int(compliance_year or datetime.now().year)

    prog(12, "正在读取企业台账与所属行业…")
    ent_pack: dict[str, Any] = {}
    if enterprise_id:
        try:
            ent_pack = _enterprise_pack(db, user_id, enterprise_id, year)
        except Exception as exc:  # noqa: BLE001 —— 台账异常降级为纯政策版
            logger.warning("policy digest enterprise pack failed: %s", exc)
            ent_pack = {}

    industry_key = str((ent_pack.get("enterprise") or {}).get("industry") or "").strip().lower()
    from .industry_sources import resolve_industry

    if industry_key not in INDUSTRY_BASELINE:
        # 台账里没有行业（或行业不在四行业内）时按历史默认处理，并在底稿里说明
        industry_key = resolve_industry(industry_key, "")
    industry_label = POLICY_INDUSTRY_LABEL.get(industry_key, industry_key or "—")

    prog(28, f"正在检索近 {window_days} 天{industry_label}行业官方政策…")
    from .industry_sources import fetch_official_bundle

    bundle: dict[str, Any] = {}
    try:
        bundle = await fetch_official_bundle(
            industry=industry_key, industry_label=industry_label, official_max=12
        )
    except Exception as exc:  # noqa: BLE001 —— 抓取失败不应中断整份摘要
        logger.warning("policy digest official fetch failed: %s", exc)
        bundle = {}

    raw_items = [it for it in (bundle.get("official") or []) if isinstance(it, dict)]
    items = [it for it in raw_items if _is_policy_like(it)]
    dropped = len(raw_items) - len(items)
    if dropped:
        logger.info("policy digest: filtered %d non-policy items", dropped)

    prog(52, "正在按发布窗口与文种归类政策条目…")
    buckets = _split_items(items, window_days)
    window_items = [it for it in buckets["window"] if not _is_local(it)]
    local_items = [it for it in buckets["window"] if _is_local(it)]
    undated = buckets["undated"][:5]
    # 存量背景里不再保留地方试点文件：全国口径的报告里放「上海市配额方案」只会误导
    older = [it for it in buckets["older"] if not _is_local(it)][:6]

    prog(64, "正在核对清缴节点与台账口径…")
    deadline = _deadline_info(str(ent_pack.get("clearance_md") or "12-31")) if ent_pack else {}

    prog(70, "政策底稿已就绪…")

    factsheet_md, sources_md, numbered = _render_factsheet(
        year=year,
        industry_key=industry_key,
        industry_label=industry_label,
        window_items=window_items,
        local_items=local_items,
        undated=undated,
        older=older,
        ent_pack=ent_pack,
        deadline=deadline,
        window_days=window_days,
        src_errors=list(bundle.get("errors") or []),
        fetched_at=str(bundle.get("fetched_at") or ""),
    )

    return {
        "industry": industry_key,
        "industry_label": industry_label,
        "items_total": len(items),
        "window_items": window_items,
        "local_items": local_items,
        "undated": undated,
        "older": older,
        "enterprise": ent_pack.get("enterprise"),
        "accounting": ent_pack.get("accounting") or {},
        "deadline": deadline,
        "sources_md": sources_md,
        "sources_items": numbered,
        "factsheet_md": factsheet_md,
        "counts": {
            "window": len(window_items),
            "local": len(local_items),
            "undated": len(undated),
            "older": len(older),
        },
    }


def _render_factsheet(
    *,
    year: int,
    industry_key: str,
    industry_label: str,
    window_items: list[dict[str, Any]],
    local_items: list[dict[str, Any]],
    undated: list[dict[str, Any]],
    older: list[dict[str, Any]],
    ent_pack: dict[str, Any],
    deadline: dict[str, Any],
    window_days: int,
    src_errors: list[str],
    fetched_at: str,
) -> tuple[str, str, list[dict[str, Any]]]:
    """渲染政策底稿。用 ``"".join(parts)`` 拼接，逐行自带换行，
    避免 ``"\\n".join`` 在 Markdown 表格行之间插入空行导致表格断裂。"""
    from .policy_research import _sources_md

    p: list[str] = []
    baseline = INDUSTRY_BASELINE.get(industry_key) or {}
    today = date.today()

    # 统一编号：窗口内 → 日期待核验 → 更早存量，与文末来源列表序号一致。
    # 分组标记必须写进副本里，用对象身份/相等性回查会失败（拷贝后不再是同一对象）
    numbered: list[dict[str, Any]] = []
    for grp, group in (
        ("window", window_items),
        ("local", local_items),
        ("undated", undated),
        ("older", older),
    ):
        for it in group:
            url = str(it.get("url") or "").strip()
            if not url:
                continue
            numbered.append(dict(it, _n=len(numbered) + 1, _grp=grp))

    win_numbered = [it for it in numbered if it.get("_grp") == "window"]
    local_numbered = [it for it in numbered if it.get("_grp") == "local"]
    undated_numbered = [it for it in numbered if it.get("_grp") == "undated"]
    older_numbered = [it for it in numbered if it.get("_grp") == "older"]

    # 一、政策条目
    p.append(f"## 政策条目（近 {window_days} 天，{today.isoformat()} 起算）\n\n")
    if src_errors:
        p.append("- 抓取异常：" + "；".join(src_errors) + "\n\n")
    if fetched_at:
        p.append(f"- 数据抓取时间：{fetched_at}\n\n")

    if win_numbered:
        p.append(f"本期共检索到 {len(win_numbered)} 条国家级政策类条目：\n\n")
        p.append("| 编号 | 发布日期 | 发布机构 | 文种 | 效力 | 标题 |\n")
        p.append("|---|---|---|---|---|---|\n")
        for it in win_numbered:
            p.append(
                f"| [{it['_n']}] | {_date_text(it.get('published_at'))} | "
                f"{_cut(it.get('platform') or '—', 18)} | {_policy_type(it.get('title') or '')} | "
                f"{_effect_status(it.get('title') or '')} | {_cut(it.get('title'), 60)} |\n"
            )
    else:
        p.append(
            "**本期未检索到新增政策文件**（近 %d 天官方源无命中）。"
            "报告须直接写明这一点，不得用往年文件充数。\n" % window_days
        )

    if local_numbered:
        p.append(
            "\n### 地方与行业文件（非国家级，仅作参照；"
            "不得写入「配额与分配」等国家级章节）\n\n"
        )
        for it in local_numbered:
            p.append(
                f"- [{it['_n']}] {_date_text(it.get('published_at'))}｜"
                f"{_cut(it.get('platform') or '—', 18)}｜{_cut(it.get('title'), 70)}"
                f"（{_policy_type(it.get('title') or '')}）\n"
            )

    if undated_numbered:
        p.append("\n### 日期待核验条目（无法确定发布日，未参与时效判断）\n\n")
        for it in undated_numbered:
            p.append(
                f"- [{it['_n']}] {_cut(it.get('platform') or '—', 18)}｜"
                f"{_cut(it.get('title'), 70)}（{_policy_type(it.get('title') or '')}）\n"
            )

    if older_numbered:
        p.append("\n### 更早的存量文件（仅供背景，**不得**作为本期新增写入正文）\n\n")
        for it in older_numbered:
            p.append(
                f"- [{it['_n']}] {_date_text(it.get('published_at'))}｜"
                f"{_cut(it.get('platform') or '—', 18)}｜{_cut(it.get('title'), 70)}\n"
            )

    # 二、行业基线
    p.append(f"\n## 行业基线（{industry_label}，系统内置，禁止改写数值）\n\n")
    if baseline:
        p.append(f"- 分配方法：{baseline.get('method')}\n")
        p.append(f"- 核算单元：{baseline.get('unit')}\n")
        p.append(f"- 覆盖温室气体：{baseline.get('gas')}\n")
        p.append("- 关键参数：\n")
        for line in baseline.get("params") or ():
            p.append(f"  - {line}\n")
        p.append("- 特殊情形（按等量分配处理）：\n")
        for line in baseline.get("special") or ():
            p.append(f"  - {line}\n")
        p.append(f"- 本行业政策抓手：{baseline.get('focus')}\n")
    else:
        p.append("本次未匹配到行业基线数据。\n")

    # 三、共同规则
    p.append("\n## 共同规则（四行业一致，引用时不得改写）\n\n")
    for line in COMMON_RULES:
        p.append(f"- {line}\n")

    # 四、我方台账
    ent = ent_pack.get("enterprise") or {}
    acc = ent_pack.get("accounting") or {}
    if ent:
        gap = _f(acc.get("compliance_gap")) or 0.0
        p.append(f"\n## 我方台账（{ent.get('name') or '—'}，{industry_label}）\n\n")
        p.append("| 指标 | 数值 |\n|---|---:|\n")
        p.append(f"| 核查排放（万吨） | {_fmt_wan(acc.get('verified_emission'))} |\n")
        p.append(f"| 可用 CEA（万吨） | {_fmt_wan(acc.get('free_cea_quota'))} |\n")
        p.append(f"| CCER 抵销上限（万吨） | {_fmt_wan(acc.get('ccer_cap'))} |\n")
        p.append(
            f"| 履约缺口（已扣 CCER，万吨） | {_fmt_wan(acc.get('compliance_gap'))}"
            f"{'（盈余）' if gap < 0 else ''} |\n"
        )
        budget = ent.get("annual_budget_cap")
        if budget is not None:
            p.append(f"| 年度预算上限（万元） | {_f(budget) or 0:.2f} |\n")
        if deadline:
            p.append(f"| 清缴截止 | {deadline.get('deadline')}（剩余 {deadline.get('days_left')} 天） |\n")
    else:
        p.append("\n## 我方台账\n\n本次未关联企业台账，报告省略「对我方的影响与待办」一章。\n")

    # 五、政策日历
    p.append("\n## 政策日历与时间节点\n\n")
    if deadline:
        p.append(
            f"- 配额清缴截止：{deadline.get('deadline')}，剩余 {deadline.get('days_left')} 天\n"
        )
    p.append(f"- 报告年度：{year} 年度履约\n")
    consult = [
        it for it in win_numbered
        if _effect_status(it.get("title") or "") == "征求意见（未生效）"
    ]
    if consult:
        p.append("- 征求意见中的文件（尚未生效，需跟踪正式稿）：\n")
        for it in consult:
            p.append(f"  - [{it['_n']}] {_cut(it.get('title'), 60)}\n")
    else:
        p.append("- 本期无处于征求意见阶段的文件\n")

    factsheet = "".join(p).strip() + "\n"
    sources_md = _sources_md(numbered, limit=30, start=1)
    return factsheet, sources_md, numbered


# ---------- 提示词 ----------


def policy_digest_system_prompt(*, subject: str, year: int, industry_label: str) -> str:
    """政策摘要专用系统提示词。

    与履约报告的关键差异：不写减排路径、不做三档策略对比、不预测碳价；
    每条政策必须带日期与发布机构，且必须落到本行业的具体条款。
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    heading = report_heading_of("policy_digest")
    return (
        f"你是双碳政策研究员，正在为「{subject}」撰写 {year} 年{heading}。\n"
        f"服务对象：{industry_label}行业控排企业的碳资产与合规岗。\n"
        f"生成时间：{now}\n"
        "定位：只回答三件事——本期出了什么文件、对我们这个行业意味着什么、下一步要做什么。\n"
        "硬约束：\n"
        "1. 只写用户消息「政策条目」表中出现的文件，禁止补充表外文件，"
        "禁止编造文号、发文机关、条款编号或生效日期；表中没有的写「本期未检索到」。\n"
        "2. 每条政策必须带「发布日期 + 发布机构」。表中日期标注「仅到月」时写「YYYY 年 MM 月」，"
        "不得补全为具体某日；标注「未标注日期」的照写「未标注日期」，不得推测。\n"
        "3. 不得把「征求意见稿」写成已生效；效力列写「以原文为准」的，"
        "正文只能写「以原文为准」，不得自行判定是否生效。\n"
        "4. 「行业专项」必须落到本行业的具体条款（分配方法、核算单元、关键参数、特殊情形），"
        "禁止只写「政策持续加码」「要求趋严」这类空话，也禁止把其他行业的参数写到本行业名下。\n"
        "5. 配额参数（基准值、平衡值、盈缺上限、预分配比例、抵销比例）只能引用"
        "「行业基线」与「共同规则」两节，禁止自行计算、推导或改写数值。\n"
        "6. 不预测碳价、不给买卖时点建议（那是碳交易简报的职责）；"
        "确需谈价格影响时只写方向与传导路径，不写目标价。\n"
        "7. 全文简体中文；除 CEA、CCER、CBAM、CO₂、CF₄、C₂F₆ 等专有名词外不出现英文单词。\n"
        "8. 严禁元话语与过程性表述：不得出现「用户要求」「系统提示」「硬约束」「底稿」"
        "「政策条目表」「以下是根据」等字样，也不要解释本章写作目的，直接给正文。\n"
        "9. 必须包含以下二级标题，顺序固定，不得增删或改名：\n"
        f"{_report_header(subject, year, 'policy_digest')}\n\n"
        "## 本期要点\n"
        "## 配额与分配\n"
        "## 核算、核查与数据质量\n"
        "## 交易、履约与抵销\n"
        "## 行业专项\n"
        "## 对我方的影响与待办\n"
        "## 政策日历与待观察\n"
        "## 信息来源\n"
        "底稿未提供企业台账时，省略「## 对我方的影响与待办」，并在「本期要点」说明未关联台账。\n"
        "10. 「本期要点」3–5 条，每条一句话，格式为「文件或事项 + 对本行业的含义」，不含空泛评价；"
        "本期确实没有新增文件时，第一条直接写「本期未检索到新增国家级政策文件」。\n"
        "11. 「配额与分配」「核算、核查与数据质量」「交易、履约与抵销」三章，"
        "本期无对应新文件时写明「本期无新增」，再引用「共同规则」里的现行口径作背景，"
        "不得把背景写成新发布。\n"
        "12. 「政策日历与待观察」只写底稿能推出的节点（清缴截止日、征求意见中的文件、"
        "条文明确写出的实施时间）；没有就写「本期无新增时间节点」。\n"
        "13. 「对我方的影响与待办」要落到台账数字（缺口、预算、清缴剩余天数），"
        "给出「谁、在什么时间、做什么」，3–5 条，可执行。\n"
        "14. 篇幅 1800–2500 字；每段不超过 4 行；条目用列表或表格，不要长段落。\n"
        "15. 「地方与行业文件」一节的条目只能作为参照：正文提及时必须写明「地方」或「试点」，"
        "不得写成本期国家级政策，也不得据此改写全国口径的配额参数。\n"
        "16. 正文提及具体文件时，在该句句末标注其编号（如 [2]）；"
        "但同一段落、同一张表格内不重复标注——表格在标题行或首次出现的单元格标一次即可，"
        "逐句逐格都挂编号会让正文不可读。\n"
        "17. 「信息来源」放在全文最后，原样使用用户消息中带 http(s) 链接的编号列表，"
        "禁止改写为「底稿第×条」或省略网址；无来源时写「本次无外部可核验链接来源」。"
        "文末附一句「本摘要仅作政策跟踪，不构成合规或投资承诺」。\n"
    )


POLICY_USER_INSTRUCTION = (
    "输出 Markdown 正文（可含「信息来源」占位，系统会替换为真实链接），"
    "无需任何说明性前缀。政策归属与行业含义优先，不要写成新闻综述。"
)

POLICY_FALLBACK_HINT = "请先核对底稿中的政策条目日期、发布机构与行业基线参数，再判断对本企业的影响。"


# ---------- 兜底 ----------


def _ensure_policy_notice(text: str, pack: dict[str, Any]) -> str:
    """窗口内确实没有新增文件时，确保正文明确写出这一点。

    模型偶有把「存量文件」当成「本期新增」的倾向，这里做一次确定性校正：
    只在窗口与待核验都为空时触发，不覆盖已有表述。
    """
    body = text or ""
    counts = pack.get("counts") or {}
    if counts.get("window") or counts.get("undated"):
        return body
    if "未检索到" in body:
        return body
    lines = body.split("\n", 1)
    # notice 自带结尾空行；剩余部分的首部换行要剥掉，否则会出现三个连续空行
    rest = (lines[1] if len(lines) > 1 else "").lstrip("\n")
    notice = (
        f"> 本期（近 {DEFAULT_WINDOW_DAYS} 天）未检索到新增政策文件，"
        "以下内容依据行业基线与现行共同规则整理。\n\n"
    )
    return (lines[0] + "\n\n" + notice + rest).strip() + "\n"


def _tidy_citations(text: str) -> str:
    """收敛过密的编号标注。

    提示词要求「同一段落、同一表格内不重复标注」，但模型经常逐句逐格都挂编号
    （一张表每行都以 [2] 结尾），正文会被读成一串数字。这里做确定性收敛：
    ① 同一行内同一编号只保留第一个；
    ② 整张表所有数据行都挂着完全相同的编号时，只保留首行那一处。
    """
    lines = (text or "").split("\n")

    def _dedupe_line(line: str) -> str:
        seen: set[str] = set()

        def repl(m: re.Match[str]) -> str:
            n = m.group(1)
            if n in seen:
                return ""
            seen.add(n)
            return m.group(0)

        return re.sub(r"\[(\d{1,2})\]", repl, line)

    deduped = [_dedupe_line(ln) for ln in lines]

    out: list[str] = []
    i = 0
    total = len(deduped)
    while i < total:
        if not deduped[i].lstrip().startswith("|"):
            out.append(deduped[i])
            i += 1
            continue
        j = i
        while j < total and deduped[j].lstrip().startswith("|"):
            j += 1
        block = deduped[i:j]
        data = block[2:] if len(block) > 2 else []
        sets = [set(re.findall(r"\[(\d{1,2})\]", row)) for row in data]
        if len(data) >= 2 and sets and all(s == sets[0] and s for s in sets):
            for k in range(1, len(data)):
                for n in sets[0]:
                    data[k] = data[k].replace(f"[{n}]", "")
            block = block[:2] + data
        out.extend(block)
        i = j
    return "\n".join(out)


def _ensure_boundary_note(text: str) -> str:
    """补一句边界声明。政策摘要容易被当成合规依据，这句不能交给模型自由决定。"""
    body = text or ""
    if any(k in body for k in _BOUNDARY_MARKS):
        return body
    note = (
        "> 本摘要依据公开可核验来源整理，条款与效力以原文为准，"
        "不构成投资建议或合规承诺。\n\n"
    )
    idx = body.find("## 信息来源")
    if idx < 0:
        return body.rstrip() + "\n\n" + note.strip() + "\n"
    return body[:idx].rstrip() + "\n\n" + note + body[idx:]


def _prune_unused_sources(text: str, numbered: list[dict[str, Any]]) -> str:
    """文末只保留正文真正引用过的来源。

    共享的 `_apply_sources_footer` 会把底稿里所有带链接条目都列进文末，
    政策摘要最讲的正是「可核验」，列出未引用来源会削弱这一点：
    读者按 [5] 去正文找，找不到对应表述。

    编号沿用底稿编号（正文里的 [n] 不变），因此可能出现不连续的编号，
    这比「编号与正文错位」安全得多。
    """
    body = _strip_sources_section(text or "")
    used = {int(m) for m in re.findall(r"\[(\d{1,2})\]", body)}
    if not used:
        return text or ""
    kept = [it for it in numbered if int(it.get("_n") or 0) in used]
    if not kept or len(kept) == len(numbered):
        return text or ""

    lines = ["## 信息来源", ""]
    for it in kept:
        url = str(it.get("url") or "").strip()
        if not url:
            continue
        n = int(it.get("_n") or 0)
        plat = str(it.get("platform") or "其他")
        title = str(it.get("title") or url).replace("[", "(").replace("]", ")")
        if len(title) > 72:
            title = title[:71] + "…"
        lines.append(f"[{n}] [{plat}] [{title}]({url})")
        lines.append(f"    {url}")
    if len(lines) <= 2:
        return text or ""
    return body.rstrip() + "\n\n" + "\n".join(lines) + "\n"


# ---------- 入口 ----------

async def run_policy_digest_report(
    db: Any,
    report: Any,
    *,
    ctx: dict[str, Any] | None = None,
    on_progress: ProgressFn,
    on_content: ContentFn,
) -> str:
    """政策摘要完整流水线：台账 → 官方政策 → 政策底稿 → 流式撰写。"""
    ctx = ctx if isinstance(ctx, dict) else _parse_ai_context(getattr(report, "ai_context", "") or "")
    year = int(ctx.get("compliance_year") or getattr(report, "target_year", 0) or datetime.now().year)
    enterprise_id = str(ctx.get("enterprise_id") or "").strip()
    if not enterprise_id:
        raise ValueError("政策摘要需要先选择控排企业（用于确定所属行业与台账口径）")

    pack = await build_policy_factsheet(
        db,
        report.user_id,
        enterprise_id=enterprise_id,
        compliance_year=year,
        on_progress=on_progress,
    )

    on_progress(74, "政策底稿已就绪，正在撰写政策摘要正文…")
    on_content(f"{_report_header(report.subject, year, 'policy_digest')}\n\n" + pack["factsheet_md"])

    text = await synthesize_compliance_analysis_stream(
        subject=report.subject,
        compliance_year=year,
        factsheet_md=pack["factsheet_md"],
        sources_md=str(pack.get("sources_md") or ""),
        report_type="policy_digest",
        on_progress=on_progress,
        on_content=on_content,
        system_prompt=policy_digest_system_prompt(
            subject=report.subject, year=year, industry_label=pack["industry_label"]
        ),
        user_instruction=POLICY_USER_INSTRUCTION,
        fallback_hint=POLICY_FALLBACK_HINT,
        fallback_conclusion="本期要点",
        fallback_data_heading="政策与行业基线数据",
    )

    fixed = _ensure_policy_notice(text, pack)
    # 文末来源只保留正文引用过的条目（政策摘要的可核验性依赖于此）
    fixed = _prune_unused_sources(fixed, pack.get("sources_items") or [])
    fixed = _tidy_citations(fixed)
    fixed = _ensure_boundary_note(fixed)
    if fixed != text and on_content:
        on_content(fixed)
    return fixed
