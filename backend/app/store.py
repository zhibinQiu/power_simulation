"""策略库（内存存储）。

生产环境可替换为数据库；此处用进程内 dict + 文件持久化，便于演示与重启保留。
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from .models import Strategy

_DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "strategies.json")


class StrategyStore:
    def __init__(self):
        self._data: Dict[str, Strategy] = {}
        self._load()

    def _load(self):
        try:
            if os.path.exists(_DATA_FILE):
                with open(_DATA_FILE, "r", encoding="utf-8") as f:
                    for item in json.load(f):
                        s = Strategy(**item)
                        self._data[s.id] = s
        except Exception:
            self._data = {}

    def _save(self):
        try:
            with open(_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump([s.model_dump() for s in self._data.values()], f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def list(self) -> List[Strategy]:
        return list(self._data.values())

    def get(self, sid: str) -> Optional[Strategy]:
        return self._data.get(sid)

    def add(self, s: Strategy) -> Strategy:
        self._data[s.id] = s
        self._save()
        return s

    def create(self, name: str, description: str, raw_text: str, ops) -> Strategy:
        s = Strategy(
            id=uuid.uuid4().hex[:10],
            name=name, description=description, raw_text=raw_text,
            ops=ops, applied=False, created_at=datetime.now().isoformat(timespec="seconds"),
        )
        return self.add(s)

    def set_applied(self, sid: str, applied: bool) -> Optional[Strategy]:
        s = self._data.get(sid)
        if s:
            s.applied = applied
            self._save()
        return s

    def update(self, sid: str, name: Optional[str] = None, description: Optional[str] = None,
               raw_text: Optional[str] = None, ops: Optional[list] = None) -> Optional[Strategy]:
        """更新策略的名称/描述/原文/操作。None 字段保持原值。"""
        s = self._data.get(sid)
        if not s:
            return None
        if name is not None:
            s.name = name
        if description is not None:
            s.description = description
        if raw_text is not None:
            s.raw_text = raw_text
        if ops is not None:
            s.ops = ops
        self._save()
        return s

    def delete(self, sid: str) -> bool:
        if sid in self._data:
            del self._data[sid]
            self._save()
            return True
        return False


store = StrategyStore()
