"""本体数据模型：概念 / 关系 / 规则。"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@dataclass
class Concept:
    """领域概念：工序 / 设备 / 物料 / 指标 / 能源 / 排放物等。"""
    id: str = ""
    name: str = ""                    # 概念名（如 高炉）
    description: str = ""             # 语义描述
    category: str = "other"           # 工序/设备/物料/指标/能源/排放/其他
    aliases: List[str] = field(default_factory=list)      # 别名（如 炼铁炉）
    keywords: List[str] = field(default_factory=list)     # 触发匹配关键词（如 焦比）
    properties: Dict[str, Any] = field(default_factory=dict)  # 属性（unit/formula/默认值…）
    builtin: bool = False             # 内置概念不可删除
    created_at: float = 0.0
    updated_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.id:
            self.id = _new_id("con")
        if not self.created_at:
            self.created_at = time.time()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "category": self.category, "aliases": self.aliases,
            "keywords": self.keywords, "properties": self.properties,
            "builtin": self.builtin, "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Concept":
        d = dict(d or {})
        return Concept(
            id=d.get("id") or "", name=d.get("name") or "",
            description=d.get("description") or "",
            category=d.get("category") or "other",
            aliases=list(d.get("aliases") or []),
            keywords=list(d.get("keywords") or []),
            properties=dict(d.get("properties") or {}),
            builtin=bool(d.get("builtin")),
            created_at=float(d.get("created_at") or 0),
            updated_at=float(d.get("updated_at") or 0),
        )


@dataclass
class Relation:
    """概念间语义关系：属于 / 包含 / 排放 / 消耗 / 产出 / 影响 / 等价于…"""
    id: str = ""
    source: str = ""                  # 源概念 id
    target: str = ""                  # 目标概念 id
    type: str = "相关"                 # 关系类型
    description: str = ""
    builtin: bool = False
    created_at: float = 0.0
    updated_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.id:
            self.id = _new_id("rel")
        if not self.created_at:
            self.created_at = time.time()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "source": self.source, "target": self.target,
            "type": self.type, "description": self.description,
            "builtin": self.builtin, "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Relation":
        d = dict(d or {})
        return Relation(
            id=d.get("id") or "", source=d.get("source") or "",
            target=d.get("target") or "", type=d.get("type") or "相关",
            description=d.get("description") or "",
            builtin=bool(d.get("builtin")),
            created_at=float(d.get("created_at") or 0),
            updated_at=float(d.get("updated_at") or 0),
        )


@dataclass
class Rule:
    """领域规则 / 知识规则：用于本体推理（直接回答或提供有效信息）。"""
    id: str = ""
    name: str = ""
    description: str = ""             # 规则说明
    keywords: List[str] = field(default_factory=list)  # 触发问题的关键词
    if_question: str = ""             # 适用问题模式（文本说明，供 LLM 参考）
    conclusion: str = ""              # 结论 / 回答模板（可含 {变量} 占位）
    answer_template: str = ""         # 直接回答的完整模板（can_answer=True 时使用）
    can_answer: bool = False          # 是否可基于本体直接回答
    source: str = "manual"            # seed / manual
    builtin: bool = False
    created_at: float = 0.0
    updated_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.id:
            self.id = _new_id("rule")
        if not self.created_at:
            self.created_at = time.time()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "keywords": self.keywords, "if_question": self.if_question,
            "conclusion": self.conclusion, "answer_template": self.answer_template,
            "can_answer": self.can_answer, "source": self.source,
            "builtin": self.builtin, "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Rule":
        d = dict(d or {})
        return Rule(
            id=d.get("id") or "", name=d.get("name") or "",
            description=d.get("description") or "",
            keywords=list(d.get("keywords") or []),
            if_question=d.get("if_question") or "",
            conclusion=d.get("conclusion") or "",
            answer_template=d.get("answer_template") or "",
            can_answer=bool(d.get("can_answer")),
            source=d.get("source") or "manual",
            builtin=bool(d.get("builtin")),
            created_at=float(d.get("created_at") or 0),
            updated_at=float(d.get("updated_at") or 0),
        )


@dataclass
class ReasonResult:
    """本体推理结果：命中概念 / 关系 / 规则 + 可能的直接回答。"""
    question: str = ""
    matched_concepts: List[Dict[str, Any]] = field(default_factory=list)
    matched_relations: List[Dict[str, Any]] = field(default_factory=list)
    matched_rules: List[Dict[str, Any]] = field(default_factory=list)
    direct_answer: Optional[str] = None     # 基于规则可直接回答的结论
    evidence: str = ""                       # 推理依据（文本化，供 LLM 参考）
    can_answer: bool = False                 # 是否可直接回答

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "matched_concepts": self.matched_concepts,
            "matched_relations": self.matched_relations,
            "matched_rules": self.matched_rules,
            "direct_answer": self.direct_answer,
            "evidence": self.evidence,
            "can_answer": self.can_answer,
        }

    def semantic_text(self, limit: int = 3200) -> str:
        """把推理结果文本化为语义上下文（注入智能体 LLM）。"""
        parts = [f"【本体命中】问题: {self.question}"]
        if self.matched_concepts:
            names = []
            for c in self.matched_concepts:
                desc = c.get("description") or ""
                names.append(f"{c['name']}({desc})" if desc else c["name"])
            parts.append("相关概念: " + "；".join(names))
        if self.matched_relations:
            rels = []
            for r in self.matched_relations:
                rels.append(f"{r.get('source_name','?')}{r.get('type','')}{r.get('target_name','?')}"
                            + (f"({r.get('description','')})" if r.get("description") else ""))
            parts.append("相关关系: " + "；".join(rels))
        if self.matched_rules:
            for r in self.matched_rules:
                parts.append(f"规则[{r.get('name','')}]: {r.get('description') or r.get('conclusion') or ''}")
        text = "\n".join(parts)
        return text[:limit]

    def to_graph(self) -> Dict[str, Any]:
        """返回可视化所需的 nodes/edges（仅命中子图）。"""
        concepts = {c["id"]: c for c in self.matched_concepts}
        nodes = [{"id": c["id"], "name": c["name"], "category": c.get("category", "")}
                 for c in concepts.values()]
        edges = []
        for r in self.matched_relations:
            if r.get("source") in concepts and r.get("target") in concepts:
                edges.append({"source": r["source"], "target": r["target"],
                              "type": r.get("type", "")})
        return {"nodes": nodes, "edges": edges}
