"""分行业节能降碳与履约协同建议（报告底稿用，非实时政策原文）。"""

from __future__ import annotations

from typing import Any

# 行业特征 → 可落地的节能降碳与履约协同方向（中文）
_INDUSTRY_PLAYBOOK: dict[str, dict[str, Any]] = {
    "power": {
        "traits": [
            "燃料结构与发电量强相关，化石燃料燃烧是 Scope1 主因",
            "负荷与检修计划影响年度排放曲线，履约年中后半段波动常见",
            "灵活调峰与节能改造可同步降低履约缺口与燃料成本",
        ],
        "abatement": [
            "锅炉/汽轮机通流改造、冷端优化，降低供电煤耗；改造前后用标准煤耗差估算年减排量并纳入履约缺口情景",
            "掺烧生物质或污泥等减碳燃料（合规前提下），压低核查排放强度，同步评估燃料供应与热值波动",
            "优化启停与负荷分配，减少低负荷高煤耗运行时段；将调峰计划与配额月度台账联动",
            "厂用电节能（风机水泵变频、照明与辅机系统）降低自耗电，间接改善综合能耗指标",
            "烟气余热深度利用与空预器密封改造，作为短周期、可核验的降碳抓手",
            "灵活性改造（最小出力下调、爬坡能力）为后续风光协同与碳强度下降预留空间",
        ],
        "market": [
            "缺口企业：结合碳价低位窗口分批购入 CEA，避免年末扎堆高价采购",
            "盈余企业：关注结转上限，超额部分宜在结转日前卖出或扩大净卖出",
            "评估 CCER 抵扣空间（上限比例内），优先消耗自有可抵扣存量",
        ],
        "mid_long": [
            "制定煤电机组节能降碳改造与灵活性改造路线图，与履约年度滚动衔接",
            "跟踪容量电价、能耗双控与碳市场联动政策，避免多头约束冲突",
            "建立月度排放—配额台账，将技改投运时点纳入下一履约年配额规划",
        ],
    },
    "steel": {
        "traits": [
            "烧结、炼铁、炼钢工序排放集中，原料结构与产能利用率影响显著",
            "废钢比、氢基还原等工艺路线决定中长期碳强度轨迹",
            "产量波动大时，配额盈余/缺口切换快，需要动态库存策略",
        ],
        "abatement": [
            "提高废钢比、优化高炉炉料结构，降低吨钢碳排放",
            "烧结烟气循环、余热余能回收，压降燃料与动力消耗",
            "电炉短流程占比提升（电力结构清洁化前提下减排更明显）",
            "工序节能诊断（风机、加热炉、连铸冷却）形成可量化技改清单",
        ],
        "market": [
            "按产量计划滚动测算履约缺口，旺产季提前锁定 CEA/CCER 成本",
            "技改投运前后分别做「改造前/后」配额情景，避免一次性囤积失效风险",
            "结转规则约束下，避免把超额配额当作无成本库存长期持有",
        ],
        "mid_long": [
            "对接超低排放与极致能效工程，把碳强度下降写入资本开支优先级",
            "探索绿电直购/绿证与产品碳足迹披露，服务下游低碳采购需求",
            "关注氢冶金、CCUS 示范进展，预留中长期技术路线切换窗口",
        ],
    },
    "cement": {
        "traits": [
            "熟料煅烧过程排放占比高，替代燃料与替代原料是关键抓手",
            "产能错峰与窑运转率直接影响年度排放与配额余缺",
            "单位熟料热耗、电耗指标与双碳、能耗双控高度耦合",
        ],
        "abatement": [
            "提高替代燃料比例（RDF、生物质等），降低化石燃料依赖",
            "矿化原料/固废替代，降低石灰石煅烧过程排放强度",
            "篦冷机、预热器系统优化与余热发电效率提升",
            "粉磨系统节能与熟料系数优化，降低综合电耗",
        ],
        "market": [
            "错峰生产与履约清缴节奏对齐，避免停窑期后突击补购配额",
            "替代燃料项目核证减排若可形成 CCER，需单独评估方法学与时效",
            "盈余配额优先服务结转上限内留存，超额尽早处置",
        ],
        "mid_long": [
            "制定「热耗—电耗—替代燃料」三年降碳路径，与配额缺口情景联动",
            "跟踪水泥行业纳入更严格强度基准或配额收紧的政策信号",
            "产品侧推进低碳水泥认证与碳足迹，提升绿色溢价能力",
        ],
    },
    "aluminum": {
        "traits": [
            "电解过程电力间接排放敏感；若履约口径以 Scope1 为主，仍需关注阳极消耗等直接排放",
            "槽况稳定性、电流效率与阳极质量影响能耗与排放强度",
            "绿电占比提升对产品碳足迹与国际供应链合规（如碳边境调节）意义重大",
        ],
        "abatement": [
            "提升电流效率、降低效应系数，稳定槽况以减少异常排放与电耗",
            "阳极质量与残极管理优化，降低阳极净耗",
            "整流所与铸造工序节能，辅以余热利用",
            "在可行时提高可再生电力消纳比例，服务低碳铝品牌",
        ],
        "market": [
            "结合产量与检修计划测算 CEA 余缺，避免扩产年缺口放大时被动高价采购",
            "若持有可抵扣 CCER，优先在合规上限内使用，降低外购 CEA 现金支出",
            "关注结转日与净卖出规则，防止超额配额失效",
        ],
        "mid_long": [
            "将绿电长期协议、节能技改与履约预算纳入同一决策框架",
            "建立产品碳足迹与出口市场合规台账，预留供应链披露能力",
            "跟踪电解槽大型化、惰性阳极等技术成熟度，评估中长期减排投资",
        ],
    },
}


def industry_strategy_md(
    industry: str,
    *,
    compliance_gap: float = 0.0,
    carry_excess: float = 0.0,
) -> str:
    """生成行业特征 + 节能降碳 + 市场协同建议 Markdown。"""
    key = str(industry or "").strip().lower()
    book = _INDUSTRY_PLAYBOOK.get(key)
    if not book:
        book = {
            "traits": ["控排企业排放与产量/能耗强相关，需建立台账化履约管理"],
            "abatement": [
                "梳理主要排放源与能耗设备清单，优先实施高性价比节能改造",
                "建立月度排放监测与配额台账，将技改效果纳入下一履约年测算",
            ],
            "market": [
                "按缺口/盈余分别制定采购或出售节奏，并结合结转规则管理库存",
            ],
            "mid_long": [
                "制定与双碳目标对齐的节能降碳三年规划，并设置可核验指标",
            ],
        }

    lines = ["### 企业行业特征", ""]
    for t in book["traits"]:
        lines.append(f"- {t}")

    lines.extend(["", "### 节能降碳抓手（工艺与能效，可落地）", ""])
    for i, t in enumerate(book["abatement"], 1):
        lines.append(f"{i}. {t}")

    lines.extend(["", "### 与碳市场履约的协同", ""])
    for t in book["market"]:
        lines.append(f"- {t}")

    gap = float(compliance_gap or 0)
    if gap > 1e-9:
        lines.append(
            f"- **当前测算为履约缺口约 {gap:g} 万吨**：节能降碳项目应优先评估"
            "「投运时点能否压降本履约年核查排放」，并同步准备 CEA/CCER 采购预算。"
        )
    elif gap < -1e-9:
        lines.append(
            f"- **当前测算为配额盈余约 {abs(gap):g} 万吨**：技改降碳与卖出/结转策略应联动，"
            "避免一边继续囤积一边浪费结转额度。"
        )

    excess = float(carry_excess or 0)
    if excess > 1e-9:
        lines.append(
            f"- **结转超额约 {excess:g} 万吨**：超额部分不能当作长期库存；"
            "应在结转日前卖出变现，或通过净卖出扩大可结转上限。"
        )

    lines.extend(["", "### 中长期发展建议", ""])
    for t in book["mid_long"]:
        lines.append(f"- {t}")

    return "\n".join(lines)


def _abatement_queries(*, industry_label: str, year: int) -> list[str]:
    y = int(year)
    ind = (industry_label or "控排企业").strip()
    return [
        f"{ind}行业 节能降碳 技术路径 {y}",
        f"{ind} 超低排放 改造 案例",
        f"{ind} 碳减排 最佳实践 OR 示范项目 {y}",
        f"{ind} 能效提升 余热回收 燃料替代",
        f"{ind} 双碳 技改 投资 效果",
        f"全国碳市场 {ind} 履约 减排措施",
    ]


async def research_industry_abatement(
    db,
    *,
    industry: str,
    industry_label: str,
    compliance_year: int,
    compliance_gap: float = 0.0,
    carry_excess: float = 0.0,
    max_items: int = 10,
    read_full: int = 6,
) -> dict[str, Any]:
    """联网检索行业最新减碳实践/方法，生成详细建议 + 来源列表。"""
    import asyncio
    import logging

    from app.services.carbon_compliance.policy_research import (
        _clip,
        _evidence_block,
        _filter_substantive,
        _is_topic_relevant,
        _item_body,
    )

    logger = logging.getLogger(__name__)
    base_md = industry_strategy_md(
        industry,
        compliance_gap=compliance_gap,
        carry_excess=carry_excess,
    )
    queries = _abatement_queries(
        industry_label=industry_label, year=compliance_year
    )

    from app.services.searxng_service import (
        SearxngNotConfiguredError,
        SearxngSearchError,
        is_enabled,
        search_web,
    )

    if not is_enabled(db):
        return {
            "ok": False,
            "summary_md": base_md,
            "sources": [],
            "error": "searxng_disabled",
        }

    loop = asyncio.get_running_loop()
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    async def _one(q: str) -> None:
        try:
            items, _ = await loop.run_in_executor(
                None, lambda qq=q: search_web(qq, page_size=5, db=db)
            )
        except (SearxngNotConfiguredError, SearxngSearchError, Exception) as exc:
            logger.debug("industry abatement query failed q=%r: %s", q, exc)
            return
        for it in items or []:
            url = str((it or {}).get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            title = (it.get("title") or "").strip()
            content = (it.get("content") or it.get("snippet") or "").strip()
            merged.append(
                {
                    "title": title,
                    "url": url,
                    "content": content,
                    "query": q,
                    "platform": "行业资讯",
                }
            )

    await asyncio.gather(*[_one(q) for q in queries])
    filtered = [it for it in merged if _is_topic_relevant(it)] or merged
    top = filtered[: max(1, int(max_items))] if filtered else []

    if top and read_full > 0:
        try:
            from app.tools.adapters import _enrich_items_with_full_text

            prefer = top[:read_full]
            await _enrich_items_with_full_text(prefer, len(prefer))
            for it in prefer:
                full = str(it.get("full_text") or "").strip()
                if full:
                    it["content"] = _clip(full, 1500)
        except Exception as exc:
            logger.warning("industry abatement read_full failed: %s", exc)

    top = _filter_substantive(top)
    online_md = ""
    if top:
        from app.integrations.deepseek_client import (
            chat_completion_message_async,
            is_configured,
        )

        if is_configured():
            system = (
                f"你是「{industry_label}」行业节能降碳顾问。"
                "根据正文证据，写面向控排企业的可执行减碳策略（内容级，勿只列标题）。\n"
                "硬约束：\n"
                "1. 输出 Markdown，标题固定为：### 最新实践与方法参考（联网）\n"
                "2. 给出 5–8 条具体措施：技术/管理动作、适用条件、预期减排或能效方向、"
                "与履约年配额缺口/结转的协同要点；勿粘贴网页原文。\n"
                "3. 禁止编造项目名称、投资额、减排百分比；证据不足则少写，勿凑数。\n"
                "4. 全文简体中文；除 CEA、CCER 外少用英文。\n"
            )
            user = (
                f"行业：{industry_label}；履约年：{compliance_year}；"
                f"履约缺口(万吨)：{compliance_gap:g}\n\n"
                f"{_evidence_block(top, limit=8)}\n\n"
                "请输出「最新实践与方法参考」一节。"
            )
            try:
                choice = await chat_completion_message_async(
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=0.3,
                    timeout=120.0,
                )
                msg = (choice or {}).get("message") or {}
                online_md = str(msg.get("content") or "").strip()
            except Exception as exc:
                logger.warning("industry abatement LLM failed: %s", exc)

        if not online_md:
            lines = ["### 最新实践与方法参考（联网）", ""]
            for it in top[:6]:
                body = _item_body(it, limit=220)
                if not body:
                    continue
                lines.append(f"- {_clip(str(it.get('title') or ''), 60)}：{body}")
            online_md = "\n".join(lines) if len(lines) > 2 else ""

    summary = base_md
    if online_md:
        summary = base_md + "\n\n" + online_md

    sources = [
        {
            "title": it.get("title") or it.get("url"),
            "url": it.get("url"),
            "platform": it.get("platform") or "行业资讯",
        }
        for it in top
        if it.get("url")
    ]
    return {
        "ok": bool(top),
        "summary_md": summary,
        "sources": sources,
        "error": None if top else "empty_or_low_info",
    }
