"""聊天会话存储：历史对话的创建 / 列表 / 读取 / 追加 / 删除。

持久化到 backend/data/sessions.json（与智能体/技能/本体同目录），线程安全。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional
from ..core.config import DATA_DIR
from ..core.storage import read_json_file, write_json_atomic

_DATA_DIR = DATA_DIR


class ChatStore:
    """本地文件版会话存储。"""

    def __init__(self, path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._path = path or os.path.join(_DATA_DIR, "sessions.json")
        self._data: Dict[str, Any] = {"sessions": []}
        self._load()

    # ------------------------- 内部 -------------------------
    def _load(self) -> None:
        loaded = read_json_file(self._path, {})
        self._data = loaded if isinstance(loaded, dict) else {"sessions": []}
        self._data.setdefault("sessions", [])

    def _save(self) -> None:
        write_json_atomic(self._path, self._data)

    @staticmethod
    def _now() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")

    # ------------------------- 会话 CRUD -------------------------
    def create(self, agent: str = "general", skills: Optional[List[str]] = None,
               title: str = "") -> Dict[str, Any]:
        """新建会话并插入列表头部。"""
        with self._lock:
            now = self._now()
            session = {
                "id": uuid.uuid4().hex[:12],
                "title": (title or "新对话")[:40],
                "agent": agent or "general",
                "skills": skills or [],
                "created_at": now,
                "updated_at": now,
                "messages": [],
            }
            self._data["sessions"].insert(0, session)
            self._save()
            return session

    def list(self, limit: int = 50) -> List[Dict[str, Any]]:
        """返回会话概要（不含消息体），按创建时间倒序。"""
        with self._lock:
            out = []
            for s in self._data["sessions"][:limit]:
                out.append({
                    "id": s.get("id", ""),
                    "title": s.get("title", "新对话"),
                    "agent": s.get("agent", "general"),
                    "skills": s.get("skills", []),
                    "created_at": s.get("created_at", ""),
                    "updated_at": s.get("updated_at", ""),
                    "message_count": len(s.get("messages", [])),
                })
            return out

    def get(self, sid: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for s in self._data["sessions"]:
                if s.get("id") == sid:
                    return s
            return None

    def append(self, sid: str, role: str, content: str,
               agent: Optional[str] = None,
               skills: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """追加一条消息。首条用户消息自动生成标题；可选更新会话 agent/skills。"""
        with self._lock:
            s = self.get(sid)
            if not s:
                return None
            s.setdefault("messages", []).append({"role": role, "content": content})
            if role == "user" and len(s["messages"]) == 1:
                title = " ".join(content.split())
                s["title"] = title[:24] or "新对话"
            if agent:
                s["agent"] = agent
            if skills is not None:
                s["skills"] = list(skills)
            s["updated_at"] = self._now()
            self._save()
            return s

    def delete(self, sid: str) -> bool:
        with self._lock:
            for i, s in enumerate(self._data["sessions"]):
                if s.get("id") == sid:
                    self._data["sessions"].pop(i)
                    self._save()
                    return True
            return False


# 全局单例（进程内共享，线程安全）
_store: Optional[ChatStore] = None


def get_store() -> ChatStore:
    global _store
    if _store is None:
        _store = ChatStore()
    return _store
