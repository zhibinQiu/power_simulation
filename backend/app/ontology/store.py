"""本体存储：JSON 文件持久化 + 线程安全 CRUD + 语义图导出。

文件：backend/data/ontology.json
首次加载时写入种子本体（seed.py），之后用户编辑持久化于文件。
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import Concept, Relation, Rule
from .seed import SEED_CONCEPTS, SEED_RELATIONS, SEED_RULES

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
ONTOLOGY_FILE = DATA_DIR / "ontology.json"

_NAME_TO_ID = {}


class OntologyStore:
    """线程安全的本体存储（单例）。"""

    def __init__(self, file_path: Optional[Path] = None) -> None:
        self._file = file_path or ONTOLOGY_FILE
        self._lock = threading.RLock()
        self._concepts: Dict[str, Concept] = {}
        self._relations: Dict[str, Relation] = {}
        self._rules: Dict[str, Rule] = {}
        self._load_or_seed()

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------
    def _load_or_seed(self) -> None:
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            if self._file.exists():
                data = json.loads(self._file.read_text("utf-8"))
                self._concepts = {
                    c["id"]: Concept.from_dict(c) for c in data.get("concepts", [])
                }
                self._relations = {
                    r["id"]: Relation.from_dict(r) for r in data.get("relations", [])
                }
                self._rules = {
                    r["id"]: Rule.from_dict(r) for r in data.get("rules", [])
                }
                if not self._concepts:
                    self._seed()
                self._resolve_relation_names()
                logger.info("ontology loaded: %d concepts, %d relations, %d rules",
                            len(self._concepts), len(self._relations), len(self._rules))
            else:
                self._seed()
        except Exception as e:  # noqa: BLE001
            logger.warning("load ontology failed(%s), re-seed", e)
            self._seed()

    def _seed(self) -> None:
        self._concepts = {}
        self._relations = {}
        self._rules = {}
        for c in SEED_CONCEPTS:
            c = dict(c, builtin=True)
            con = Concept.from_dict(c)
            self._concepts[con.id] = con
        for r in SEED_RELATIONS:
            rel = Relation.from_dict(dict(r, builtin=True))
            self._relations[rel.id] = rel
        for r in SEED_RULES:
            rule = Rule.from_dict(dict(r, builtin=True))
            self._rules[rule.id] = rule
        self._resolve_relation_names()
        self.save()

    def _resolve_relation_names(self) -> None:
        """把关系里的 source/target 由概念名解析为概念 id（存储用 id）。"""
        name2id = {c.name: c.id for c in self._concepts.values()}
        name2id.update({a: c.id for c in self._concepts.values() for a in c.aliases})
        for rel in self._relations.values():
            if rel.source not in name2id and rel.source in self._concepts:
                continue
            if rel.source in name2id and rel.source not in self._concepts:
                rel.source = name2id[rel.source]
            if rel.target in name2id and rel.target not in self._concepts:
                rel.target = name2id[rel.target]
        # 全局名字索引（概念名 + 别名 → id）
        _NAME_TO_ID.clear()
        _NAME_TO_ID.update(name2id)

    def save(self) -> None:
        with self._lock:
            payload = {
                "concepts": [c.to_dict() for c in self._concepts.values()],
                "relations": [r.to_dict() for r in self._relations.values()],
                "rules": [r.to_dict() for r in self._rules.values()],
                "updated_at": time.time(),
            }
            tmp = self._file.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
            os.replace(tmp, self._file)

    def reset(self) -> None:
        """恢复种子本体（保留用户非内置数据可选丢弃）。"""
        with self._lock:
            self._seed()

    # ------------------------------------------------------------------
    # Concepts
    # ------------------------------------------------------------------
    def list_concepts(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [c.to_dict() for c in self._concepts.values()]

    def get_concept(self, cid: str) -> Optional[Concept]:
        with self._lock:
            return self._concepts.get(cid)

    def get_concept_by_name(self, name: str) -> Optional[Concept]:
        with self._lock:
            for c in self._concepts.values():
                if c.name == name or name in c.aliases:
                    return c
            return None

    def add_concept(self, data: Dict[str, Any]) -> Concept:
        with self._lock:
            con = Concept.from_dict(dict(data, builtin=False))
            if not con.name.strip():
                raise ValueError("概念名不能为空")
            for c in self._concepts.values():
                if c.name == con.name:
                    raise ValueError(f"概念「{con.name}」已存在")
            self._concepts[con.id] = con
            self.save()
            return con

    def update_concept(self, cid: str, data: Dict[str, Any]) -> Optional[Concept]:
        with self._lock:
            con = self._concepts.get(cid)
            if not con:
                return None
            new_data = {**con.to_dict(), **{k: v for k, v in data.items() if k not in ("id", "created_at")}}
            new_data["updated_at"] = time.time()
            updated = Concept.from_dict(new_data)
            updated.builtin = con.builtin
            self._concepts[cid] = updated
            self.save()
            return updated

    def delete_concept(self, cid: str) -> bool:
        with self._lock:
            con = self._concepts.get(cid)
            if not con:
                return False
            if con.builtin:
                raise ValueError("内置概念不可删除，可编辑")
            # 级联删除相关关系
            self._relations = {
                rid: r for rid, r in self._relations.items()
                if r.source != cid and r.target != cid
            }
            del self._concepts[cid]
            self.save()
            return True

    # ------------------------------------------------------------------
    # Relations
    # ------------------------------------------------------------------
    def list_relations(self) -> List[Dict[str, Any]]:
        with self._lock:
            out = []
            for r in self._relations.values():
                d = r.to_dict()
                d["source_name"] = self._concepts.get(r.source, Concept()).name or r.source
                d["target_name"] = self._concepts.get(r.target, Concept()).name or r.target
                out.append(d)
            return out

    def add_relation(self, data: Dict[str, Any]) -> Relation:
        with self._lock:
            rel = Relation.from_dict(dict(data, builtin=False))
            if rel.source not in self._concepts or rel.target not in self._concepts:
                raise ValueError("关系端点必须是已存在的概念 id")
            self._relations[rel.id] = rel
            self.save()
            return rel

    def update_relation(self, rid: str, data: Dict[str, Any]) -> Optional[Relation]:
        with self._lock:
            rel = self._relations.get(rid)
            if not rel:
                return None
            new_data = {**rel.to_dict(), **{k: v for k, v in data.items() if k not in ("id", "created_at")}}
            new_data["updated_at"] = time.time()
            updated = Relation.from_dict(new_data)
            if updated.source not in self._concepts or updated.target not in self._concepts:
                raise ValueError("关系端点必须是已存在的概念 id")
            updated.builtin = rel.builtin
            self._relations[rid] = updated
            self.save()
            return updated

    def delete_relation(self, rid: str) -> bool:
        with self._lock:
            if rid not in self._relations:
                return False
            del self._relations[rid]
            self.save()
            return True

    # ------------------------------------------------------------------
    # Rules
    # ------------------------------------------------------------------
    def list_rules(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [r.to_dict() for r in self._rules.values()]

    def add_rule(self, data: Dict[str, Any]) -> Rule:
        with self._lock:
            rule = Rule.from_dict(dict(data, builtin=False))
            if not rule.name.strip():
                raise ValueError("规则名不能为空")
            self._rules[rule.id] = rule
            self.save()
            return rule

    def update_rule(self, rid: str, data: Dict[str, Any]) -> Optional[Rule]:
        with self._lock:
            rule = self._rules.get(rid)
            if not rule:
                return None
            new_data = {**rule.to_dict(), **{k: v for k, v in data.items() if k not in ("id", "created_at")}}
            new_data["updated_at"] = time.time()
            updated = Rule.from_dict(new_data)
            updated.builtin = rule.builtin
            self._rules[rid] = updated
            self.save()
            return updated

    def delete_rule(self, rid: str) -> bool:
        with self._lock:
            if rid not in self._rules:
                return False
            del self._rules[rid]
            self.save()
            return True

    # ------------------------------------------------------------------
    # 语义图（可视化）
    # ------------------------------------------------------------------
    def get_graph(self) -> Dict[str, Any]:
        """返回完整语义图 nodes/edges（可视化用）。"""
        with self._lock:
            nodes = [
                {"id": c.id, "name": c.name, "category": c.category,
                 "description": c.description}
                for c in self._concepts.values()
            ]
            edges = [
                {"source": r.source, "target": r.target, "type": r.type,
                 "id": r.id, "description": r.description}
                for r in self._relations.values()
            ]
            return {"nodes": nodes, "edges": edges}

    def dump(self) -> Dict[str, Any]:
        return {
            "concepts": self.list_concepts(),
            "relations": self.list_relations(),
            "rules": self.list_rules(),
        }


_store: Optional[OntologyStore] = None
_store_lock = threading.Lock()


def get_store() -> OntologyStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = OntologyStore()
    return _store


def reset_ontology() -> OntologyStore:
    """重置为种子本体并返回 store。"""
    global _store
    store = get_store()
    store.reset()
    return store
