"""本体（Ontology）模块：领域语义层。

设计目标：
- 为智能体提供领域概念、关系、规则三层语义知识，帮助其：
  1. 理解分析问题（问题补全 + 概念/关系/规则命中 → 语义上下文）
  2. 回答问题（命中可回答规则时直接给出结论，否则作为 LLM 推理依据）
- 支持可视化与手动编辑（概念/关系/规则的 CRUD，语义图导出）。
- 存储：backend/data/ontology.json（线程安全 JSON 持久化）。
"""
from .store import get_store, reset_ontology
from .reason import OntologyReasoner

__all__ = ["get_store", "reset_ontology", "OntologyReasoner"]
