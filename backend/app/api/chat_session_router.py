"""聊天会话路由：历史对话的查看 / 创建 / 继续 / 删除。

供「本析智擎」前端在对话框内查看历史对话并继续对话。
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ..services.chat_store import get_store

router = APIRouter(tags=["chat-sessions"])


class SessionCreate(BaseModel):
    agent: str = "general"
    skills: Optional[List[str]] = None
    title: str = ""


class SessionMessage(BaseModel):
    role: str  # user | assistant
    content: str
    agent: Optional[str] = None   # 可选：随消息更新会话智能体
    skills: Optional[List[str]] = None  # 可选：随消息更新会话技能


@router.get("/api/chat/sessions")
def list_sessions(limit: int = 50):
    """历史会话列表（概要）。"""
    return {"ok": True, "sessions": get_store().list(limit=limit)}


@router.post("/api/chat/sessions")
def create_session(req: SessionCreate):
    """新建会话（首条消息发送时由前端调用）。"""
    s = get_store().create(agent=req.agent, skills=req.skills, title=req.title)
    return {"ok": True, "session": s}


@router.get("/api/chat/sessions/{sid}")
def get_session(sid: str):
    """会话详情（含全部消息），用于载入历史并继续对话。"""
    s = get_store().get(sid)
    if not s:
        return {"ok": False, "error": "session not found"}
    return {"ok": True, "session": s}


@router.post("/api/chat/sessions/{sid}/messages")
def append_message(sid: str, req: SessionMessage):
    """追加一条消息（对话结束后前端回写），可同步更新会话 agent/skills。"""
    if req.role not in ("user", "assistant"):
        return {"ok": False, "error": "invalid role"}
    s = get_store().append(sid, req.role, req.content, agent=req.agent, skills=req.skills)
    if not s:
        return {"ok": False, "error": "session not found"}
    return {"ok": True, "session": s}


@router.delete("/api/chat/sessions/{sid}")
def delete_session(sid: str):
    """删除历史会话。"""
    ok = get_store().delete(sid)
    return {"ok": ok}
