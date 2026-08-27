"""报告「分析段落」生成策略（策略模式 + 简单工厂）。

业务可替换点：报告的「执行摘要 / 基线洞察 / 策略评估 / 优化建议」四段分析文本由谁生成。

- TemplateReportEngine：确定性模板文案（离线可用、零成本、数字精确）；
- LlmReportEngine：     大模型撰写（质量高，依赖外部 LLM，超时/失败返回 None）；
- AutoReportEngine：    组合策略（先 LLM，失败自动回退模板），用于默认「auto」模式。

新增一种分析引擎：继承 ReportEngine 并实现 build_analysis()，
再在 create_report_engine() 注册一行即可，业务调用方（report.py / API 层）无需改动。
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional

# ---------------------------------------------------------------------------
# 数值工具（渲染与模板共用）
# ---------------------------------------------------------------------------


def _fmt(v, digits=1) -> str:
    """格式化数值：空值显示 '-', 否则保留 digits 位小数并加千分位。"""
    if v is None:
        return "-"
    try:
        return f"{float(v):,.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def _pct(part, whole) -> str:
    """百分比字符串（分母为 0 或空返回 '-'）。"""
    if not whole:
        return "-"
    try:
        return f"{float(part) / float(whole) * 100:.1f}%"
    except (TypeError, ValueError, ZeroDivisionError):
        return "-"


# ---------------------------------------------------------------------------
# 策略接口
# ---------------------------------------------------------------------------


class ReportEngine(ABC):
    """报告分析段落生成策略的抽象基类。"""

    #: 策略标识：'template' / 'llm' / 'auto'
    name: str = ""

    @abstractmethod
    def build_analysis(
        self,
        ctx: Dict[str, Any],
        depth: str = "standard",
        progress_cb: Optional[Callable[[int, str], None]] = None,
    ) -> Optional[Dict[str, str]]:
        """基于仿真上下文 ctx 生成 4 段分析文本（summary/baseline_insight/strategy_eval/suggestions）。

        返回 None 表示本策略无法生成（如 LLM 全部失败），由上层决定回退。
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# 模板策略（确定性兜底文案）
# ---------------------------------------------------------------------------


class TemplateReportEngine(ReportEngine):
    """确定性文案：无 LLM Key / 调用失败 / 明确指定时使用，保证离线可用。"""

    name = "template"

    def build_analysis(self, ctx, depth="standard", progress_cb=None) -> Dict[str, str]:
        return _fallback_analysis(ctx)


# ---------------------------------------------------------------------------
# LLM 策略（分段调用大模型撰写）
# ---------------------------------------------------------------------------

_LLM_SYSTEM = (
    "你是钢铁行业节能减碳领域的资深数据分析专家，负责为「工业能碳智控平台」的仿真结果撰写分析报告。"
    "你只根据给定的仿真数据撰写分析，绝不编造任何数字，也不要计算具体数值（数值全部由系统计算）。"
    "所有单位按上下文说明理解（CO2 为 tCO2/h、强度为 kgCO2/t、能耗为 GJ/h、单位能耗为 kgce/t）。"
    "输出简体中文，专业、精炼、结构清晰。"
    "严禁在正文中复述、解释或总结收到的任务要求，不得出现「用户要求」「请撰写」「只输出该段」「字数要求」"
    "「系统提示」等元话语，也不要输出思考过程或草稿，直接给出分析正文。"
    "使用规范的 Markdown 排版：合理分段（每段不超过 4~5 行）、段间空一行、善用列表与短列表，避免超长段落。"
)

# 分析深度 → 每段字数要求与单次 LLM 输出上限
_DEPTH_SPEC: Dict[str, Dict[str, Any]] = {
    "brief":    {"chars": "每段 80~150 字", "max_tokens": 600},
    "standard": {"chars": "每段 150~300 字", "max_tokens": 900},
    "deep":     {"chars": "每段 300~500 字", "max_tokens": 1600},
}


class LlmReportEngine(ReportEngine):
    """大模型撰写分析段落：分段独立调用，单段失败用模板补位，全部失败返回 None。

    chat_fn 通过构造注入（依赖倒置），便于测试时替换为桩实现。
    """

    name = "llm"

    def __init__(self, chat_fn: Optional[Callable] = None) -> None:
        self._chat = chat_fn or self._default_chat

    @staticmethod
    def _default_chat(messages, timeout=90.0, max_tokens=None):
        from ...llm_strategy import chat_completion  # 懒加载，避免包级循环依赖

        return chat_completion(messages, timeout=timeout, max_tokens=max_tokens)

    def build_analysis(self, ctx, depth="standard", progress_cb=None) -> Optional[Dict[str, str]]:
        spec = _DEPTH_SPEC.get(depth, _DEPTH_SPEC["standard"])
        has_strategy = bool(ctx["strategy"])

        def _p(pct: int, stage: str) -> None:
            if progress_cb:
                progress_cb(pct, stage)

        strategy_inst = (
            ("评估策略「%s」的实施效果：核心指标变化、主要节能与减排来源工序、"
             "强度与能耗改善程度，并评估策略合理性。" % ctx["strategy_name"])
            if has_strategy else
            "本次未应用策略，请基于基线数据说明当前无策略对照、建议应用策略后对比，并简述可尝试的策略方向。"
        )
        sections = [
            ("summary", "执行摘要",
             "一句话概述整体能耗与排放水平与最关键发现，可给出综合能耗、总排放与强度水平结论。", 8, 25),
            ("baseline_insight", "基线数据分析洞察",
             "解读排放结构（直接/间接占比）、主要排放工序与贡献、能耗结构（外购电力与燃料占比）与主要能耗工序、"
             "强度与能耗效率、能流与碳流向特征，指出主要节能与减排机会点。", 28, 45),
            ("strategy_eval", "策略效果评估", strategy_inst, 48, 65),
            ("suggestions", "结论与优化建议",
             "给出 3~5 条具体、可落地的后续节能减碳建议（可结合工序类型、碳流向、能流与能耗结构等），"
             "使用短列表，并说明预期关注点。", 68, 82),
        ]
        fallback = _fallback_analysis(ctx)
        out: Dict[str, str] = {}
        for key, title, instruction, p0, p1 in sections:
            _p(p0, f"llm_{key}")
            try:
                text = _llm_section(self._chat, ctx, key, title, instruction, spec)
            except Exception:  # noqa: BLE001
                text = None
            out[key] = text or fallback.get(key, "")
            _p(p1, f"llm_{key}")
        if not any(v for v in out.values()):
            return None
        return out


def _llm_section(chat_fn: Callable, ctx: Dict[str, Any], key: str, title: str,
                 instruction: str, spec: Dict[str, Any]) -> Optional[str]:
    """单段独立调用大模型；成功返回正文文本，失败返回 None。"""
    prompt = (
        "以下是数字孪生平台的一次仿真结果（JSON）：\n"
        f"```json\n{json.dumps(ctx, ensure_ascii=False, indent=1)}\n```\n\n"
        f"任务：撰写「{title}」章节正文（{spec['chars']}，简体中文，Markdown 正文，可含短列表）。\n"
        f"{instruction}\n"
        "直接输出该章节正文，不要输出标题、序号或 JSON，也不要重复数据表格，不要复述任务要求。"
    )
    messages = [
        {"role": "system", "content": _LLM_SYSTEM},
        {"role": "user", "content": prompt},
    ]
    try:
        raw = chat_fn(messages, timeout=90.0, max_tokens=spec["max_tokens"])
    except Exception:  # noqa: BLE001
        return None
    if not raw:
        return None
    text = raw.strip()
    # 去掉可能残留的 Markdown 围栏与标题行
    text = re.sub(r"^```(?:markdown)?\s*", "", text, flags=re.M)
    text = re.sub(r"\s*```\s*$", "", text).strip()
    text = re.sub(r"^#+\s+.*\n", "", text).strip()
    return text or None


def _fallback_analysis(ctx: Dict[str, Any]) -> Dict[str, str]:
    """确定性兜底文案：无 LLM Key / 调用失败时使用。"""
    b_ctx = ctx["baseline"]
    s_ctx = ctx["strategy"]
    has_strategy = bool(s_ctx)
    b = b_ctx["totals"] if b_ctx else {}
    top = ""
    if b_ctx:
        rows = sorted(b_ctx["units"], key=lambda u: u["co2_total"] or 0, reverse=True)
        if rows:
            first = rows[0]
            top = (f"排放最大的工序为 **{first['name']}**（{_fmt(first['co2_total'])} tCO₂/h，"
                   f"占全厂 {_pct(first['co2_total'], b.get('co2_total'))}），是减排优先关注对象。")
    summary = (
        f"基线情景下全厂总排放为 **{_fmt(b.get('co2_total'))} tCO₂/h**，"
        f"吨钢碳排放强度 **{_fmt(b.get('intensity'))} kgCO₂/t**。{top}"
    )
    energy_note = ""
    if b_ctx:
        t = b_ctx["totals"]
        e_top = sorted(b_ctx["units"], key=lambda u: u["energy_total"] or 0, reverse=True)
        if e_top and e_top[0].get("energy_total"):
            energy_note = (
                f"综合能耗为 **{_fmt(t.get('energy_total'))} GJ/h**，其中燃料能耗占 "
                f"{_pct(t.get('fuel_energy'), t.get('energy_total'))}、外购电力折标占 "
                f"{_pct((t.get('elec') or 0) * 3.6, t.get('energy_total'))}；"
                f"能耗最大的工序为 **{e_top[0]['name']}**（{_fmt(e_top[0].get('energy_total'))} GJ/h）。"
            )
    baseline_insight = (
        f"直接排放占全厂 {_pct(b.get('co2_direct'), b.get('co2_total'))}、间接排放占 "
        f"{_pct(b.get('co2_indirect'), b.get('co2_total'))}；碳利用率 "
        f"{b.get('carbon_utilization') * 100 if b.get('carbon_utilization') else 0:.2f}%。{energy_note}"
        f"{top}建议后续围绕主要排放与能耗工序推进余热回收、燃料替代与能效优化。"
    )
    if has_strategy:
        s = s_ctx["totals"]
        red = (b.get("co2_total", 0) - s.get("co2_total", 0))
        strategy_eval = (
            f"策略「{ctx['strategy_name']}」应用后全厂减排 **{_fmt(red)} tCO₂/h**"
            f"（减排率 {_pct(red, b.get('co2_total'))}），吨钢强度由 {_fmt(b.get('intensity'))} 降至 "
            f"{_fmt(s.get('intensity'))} kgCO₂/t。整体效果显著，建议结合工序级贡献进一步微调参数。"
        )
    else:
        strategy_eval = "本次未应用策略，暂无前后对照；建议输入策略文本并执行仿真后再导出对比报告。"
    suggestions = (
        "- 优先对排放占比最大的工序开展节能改造与工艺优化；\n"
        "- 提高煤气/余热回收利用率，降低综合能耗与单位产品能耗；\n"
        "- 结合碳捕集与利用技术提升碳利用率；\n"
        "- 定期运行策略仿真，量化各类减排措施的边际效果后择优实施。"
    )
    return {
        "summary": summary,
        "baseline_insight": baseline_insight,
        "strategy_eval": strategy_eval,
        "suggestions": suggestions,
    }


# ---------------------------------------------------------------------------
# 组合策略（LLM 优先 + 模板兜底）
# ---------------------------------------------------------------------------


class AutoReportEngine(ReportEngine):
    """组合策略：先 LLM，LLM 无法生成时自动回退模板文案。

    used_engine 记录本次实际生效的子策略名（'llm' / 'template'），供上层标注。
    """

    name = "auto"

    def __init__(self, llm: Optional[LlmReportEngine] = None,
                 template: Optional[TemplateReportEngine] = None) -> None:
        self._llm = llm or LlmReportEngine()
        self._template = template or TemplateReportEngine()
        self.used_engine: str = "llm"

    def build_analysis(self, ctx, depth="standard", progress_cb=None) -> Dict[str, str]:
        result = self._llm.build_analysis(ctx, depth=depth, progress_cb=progress_cb)
        if result is None:
            self.used_engine = "template"
            if progress_cb:
                progress_cb(40, "template")
            return self._template.build_analysis(ctx, depth=depth)
        self.used_engine = "llm"
        return result


# ---------------------------------------------------------------------------
# 工厂：按模式创建引擎（新增引擎在此注册一行即可）
# ---------------------------------------------------------------------------

_ENGINE_TEMPLATE = "template"
_ENGINE_LLM = "llm"
_ENGINE_AUTO = "auto"


def create_report_engine(mode: str = "auto", chat_fn: Optional[Callable] = None) -> ReportEngine:
    """根据 mode 创建报告分析引擎：'template' / 'llm' / 其他（含 'auto'）为组合策略。"""
    mode = (mode or "auto").lower()
    if mode == _ENGINE_TEMPLATE:
        return TemplateReportEngine()
    if mode == _ENGINE_LLM:
        return LlmReportEngine(chat_fn=chat_fn)
    return AutoReportEngine(LlmReportEngine(chat_fn=chat_fn), TemplateReportEngine())
