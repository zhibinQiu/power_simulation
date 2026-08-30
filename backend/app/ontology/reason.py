"""本体推理器：问题补全 + 本体推理 + 语义上下文。

处理流程（智能体收到用户问题时）：
1. complete_question: 基于对话上下文把问题补充完整（LLM 补全 + 指代消解兜底）
2. reason: 在语义层上推理——匹配概念/关系/规则，判断能否直接回答
   - 命中 can_answer 规则 → direct_answer（可直接回答）
   - 否则产出 evidence（语义上下文），注入 LLM 辅助理解与回答
3. semantic_text: 文本化推理结果供 LLM 使用
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from .models import ReasonResult
from .store import OntologyStore

logger = logging.getLogger(__name__)

# 指代词（问题补全兜底）
_PRONOUNS = ["它", "这", "这个", "该", "上述", "刚才", "上面", "上边", "其", "它们", "这些", "那", "那个", "那种"]
# 概念名/别名中不含停用词时有效长度
_MAX_HIT_CONCEPTS = 8
_MAX_HIT_RULES = 5


class OntologyReasoner:
    """本体推理器：接收 store 完成匹配与推理。"""

    def __init__(self, store: Optional[OntologyStore] = None) -> None:
        self.store = store

    # ------------------------------------------------------------------
    # 1. 问题补全
    # ------------------------------------------------------------------
    def complete_question(
        self,
        question: str,
        history: Optional[List[Dict[str, Any]]] = None,
        llm_complete=None,
    ) -> str:
        """把用户问题基于历史上下文补全为自包含问题。

        llm_complete: 可选回调(question, history_text) -> str，用 LLM 补全；
        无回调或补全失败时用规则（拼接上文主题）兜底。
        """
        q = (question or "").strip()
        if not q:
            return q
        hist = [m for m in (history or []) if m.get("role") in ("user", "assistant")]
        if not hist:
            return q
        # LLM 补全优先
        if llm_complete is not None:
            try:
                out = llm_complete(q, hist)
                if out and out.strip():
                    return out.strip()
            except Exception as e:  # noqa: BLE001
                logger.warning("LLM question-completion failed: %s", e)
        # 规则兜底：问题含指代词/很短的延续问 → 以上文主题补全
        has_pronoun = any(p in q for p in _PRONOUNS)
        prev_user = ""
        for m in reversed(hist):
            if m.get("role") == "user":
                prev_user = (m.get("content") or "").strip()
                break
        if (has_pronoun or len(q) <= 12) and prev_user and prev_user != q:
            # 追问句式（含指代或以疑问/承接词开头）→ 以上文主题拼接
            if has_pronoun or re.match(r"^(那|那么|这|如果|假如|具体|详细|到底|怎么|如何|为什么)", q):
                topic = prev_user.rstrip("？?。.！! ")
                return f"{topic}：{q}"
        return q

    # ------------------------------------------------------------------
    # 2. 本体推理
    # ------------------------------------------------------------------
    def reason(self, question: str) -> ReasonResult:
        store = self.store or self._default_store()
        q = (question or "").strip().lower()
        result = ReasonResult(question=(question or "").strip())

        concepts = store.list_concepts()
        # 2.1 概念匹配（名称/别名/关键词出现在问题中）
        for c in concepts:
            hit = self._hit(question, c)
            if hit:
                result.matched_concepts.append(c)
        result.matched_concepts = result.matched_concepts[:_MAX_HIT_CONCEPTS]
        hit_ids = {c["id"] for c in result.matched_concepts}

        # 2.2 关系匹配（命中概念之间的直接关系 + 一跳到命中概念的关系）
        for r in store.list_relations():
            if r["source"] in hit_ids or r["target"] in hit_ids:
                result.matched_relations.append(r)
        # 按命中概念的数量排序（两个端点都命中优先）
        result.matched_relations.sort(
            key=lambda r: (r["source"] in hit_ids and r["target"] in hit_ids), reverse=True
        )

        # 2.3 规则匹配（关键词命中 or 规则文本与问题概念重叠）
        for rule in store.list_rules():
            rq = rule.get("keywords") or []
            if any(str(k).lower() in q for k in rq):
                result.matched_rules.append(rule)
                continue
            # 规则描述/问题模式与命中概念相关
            rule_text = (rule.get("if_question") or "") + (rule.get("description") or "")
            if hit_ids and any(c.get("name", "").lower() in rule_text.lower() for c in result.matched_concepts):
                result.matched_rules.append(rule)
        result.matched_rules = result.matched_rules[:_MAX_HIT_RULES]

        # 2.4 直接回答判断：命中 can_answer 规则
        answerable = [r for r in result.matched_rules if r.get("can_answer")]
        if answerable:
            result.can_answer = True
            tpl = answerable[0].get("answer_template") or answerable[0].get("conclusion") or ""
            result.direct_answer = tpl
            result.evidence = result.semantic_text(6000)
        else:
            result.evidence = result.semantic_text(6000)
        return result

    @staticmethod
    def _hit(question: str, concept: Dict[str, Any]) -> bool:
        """判断问题文本是否命中概念（名称/别名/关键词，子串匹配）。"""
        q = (question or "").lower()
        cands = [concept.get("name", "")] + list(concept.get("aliases") or []) + list(concept.get("keywords") or [])
        for kw in cands:
            kw = str(kw or "").strip().lower()
            if len(kw) >= 2 and kw in q:
                return True
        return False

    # ------------------------------------------------------------------
    # 3. 语义上下文
    # ------------------------------------------------------------------
    def semantic_context(self, question: str, reason_result: Optional[ReasonResult] = None) -> str:
        result = reason_result or self.reason(question)
        return result.semantic_text(6000)

    def _default_store(self) -> OntologyStore:
        from .store import get_store
        return get_store()


_default_reasoner: Optional[OntologyReasoner] = None


def get_reasoner() -> OntologyReasoner:
    global _default_reasoner
    if _default_reasoner is None:
        _default_reasoner = OntologyReasoner()
    return _default_reasoner
