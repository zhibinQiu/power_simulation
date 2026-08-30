"""AI 管理路由：智能体管理 / 技能管理 / 本体管理。

- /api/agents：GET 列表、POST 新增、PUT 更新、DELETE 删除
- /api/skills：GET 列表（?all=1 含禁用）、POST /{name}/toggle 启停
- /api/ontology：本体（语义层）的概念/关系/规则 CRUD + 语义图 + 重置

仅管理能力，业务执行仍在 simulation_router（/api/chat* 多智能体）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter()


# ------------------------- 智能体管理 -------------------------

@router.get("/api/agents")
def list_agents():
    """返回全部智能体（内置 + 自定义），供选择与后台管理。"""
    from ..agents.registry import list_agents as _list
    return {"agents": _list()}


class AgentUpsertRequest(BaseModel):
    name: str = Field("", description="智能体名称")
    emoji: str = Field("🤖", description="展示图标")
    description: str = Field("", description="一句话介绍")
    system_prompt: str = Field("", description="系统提示词")
    default_skills: List[str] = Field(default_factory=list, description="默认启用技能")
    available_skills: Optional[List[str]] = Field(
        None, description="可用技能白名单；null 表示不限")
    id: Optional[str] = Field(None, description="新增时的可选自定义 id")


@router.post("/api/agents")
def create_agent(req: AgentUpsertRequest):
    """新增自定义智能体。"""
    from ..agents.registry import add_agent
    try:
        return {"ok": True, "agent": add_agent(req.model_dump())}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/api/agents/{agent_id}")
def update_agent(agent_id: str, req: AgentUpsertRequest):
    """更新智能体（内置智能体也可调整提示词与技能白名单；仅更新显式传入的字段）。"""
    from ..agents.registry import update_agent as _update
    try:
        agent = _update(agent_id, req.model_dump(exclude_unset=True))
        if not agent:
            raise HTTPException(status_code=404, detail="智能体不存在")
        return {"ok": True, "agent": agent}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/agents/{agent_id}")
def delete_agent(agent_id: str):
    """删除自定义智能体（内置不可删除）。"""
    from ..agents.registry import delete_agent as _delete
    try:
        if not _delete(agent_id):
            raise HTTPException(status_code=404, detail="智能体不存在")
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------- 技能管理 -------------------------

@router.get("/api/skills")
def list_skills(all: bool = Query(False, description="true 时返回全部（含禁用），供管理界面")):
    """技能列表：默认仅启用；管理界面传 ?all=1 获取含禁用项。"""
    from ..skills.registry import list_skills as _list
    return {"skills": _list(enabled_only=not all)}


@router.post("/api/skills/{name}/toggle")
def toggle_skill(name: str, enabled: bool = Body(..., embed=True)):
    """启用/停用技能（状态持久化到 backend/data/skills.json）。"""
    from ..skills.registry import set_skill_enabled
    skill = set_skill_enabled(name, enabled)
    if not skill:
        raise HTTPException(status_code=404, detail=f"技能 {name} 不存在")
    return {"ok": True, "skill": skill}


# ------------------------- 本体管理（语义层） -------------------------

@router.get("/api/ontology")
def get_ontology():
    """返回完整本体（概念/关系/规则）。"""
    from ..ontology.store import get_store
    return get_store().dump()


@router.get("/api/ontology/graph")
def get_ontology_graph():
    """返回语义图（可视化 nodes/edges）。"""
    from ..ontology.store import get_store
    return get_store().get_graph()


@router.post("/api/ontology/reset")
def reset_ontology():
    """重置为内置种子本体（用户自定义数据将被清除）。"""
    from ..ontology.store import reset_ontology as _reset
    _reset()
    return {"ok": True}


# --- concepts ---

@router.post("/api/ontology/concepts")
def add_concept(body: Dict[str, Any] = Body(...)):
    from ..ontology.store import get_store
    try:
        con = get_store().add_concept(body)
        return {"ok": True, "concept": con.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/api/ontology/concepts/{cid}")
def update_concept(cid: str, body: Dict[str, Any] = Body(...)):
    from ..ontology.store import get_store
    try:
        con = get_store().update_concept(cid, body)
        if not con:
            raise HTTPException(status_code=404, detail="概念不存在")
        return {"ok": True, "concept": con.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/ontology/concepts/{cid}")
def delete_concept(cid: str):
    from ..ontology.store import get_store
    try:
        if not get_store().delete_concept(cid):
            raise HTTPException(status_code=404, detail="概念不存在")
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- relations ---

@router.post("/api/ontology/relations")
def add_relation(body: Dict[str, Any] = Body(...)):
    from ..ontology.store import get_store
    try:
        rel = get_store().add_relation(body)
        return {"ok": True, "relation": rel.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/api/ontology/relations/{rid}")
def update_relation(rid: str, body: Dict[str, Any] = Body(...)):
    from ..ontology.store import get_store
    try:
        rel = get_store().update_relation(rid, body)
        if not rel:
            raise HTTPException(status_code=404, detail="关系不存在")
        return {"ok": True, "relation": rel.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/ontology/relations/{rid}")
def delete_relation(rid: str):
    from ..ontology.store import get_store
    if not get_store().delete_relation(rid):
        raise HTTPException(status_code=404, detail="关系不存在")
    return {"ok": True}


# --- rules ---

@router.post("/api/ontology/rules")
def add_rule(body: Dict[str, Any] = Body(...)):
    from ..ontology.store import get_store
    try:
        rule = get_store().add_rule(body)
        return {"ok": True, "rule": rule.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/api/ontology/rules/{rid}")
def update_rule(rid: str, body: Dict[str, Any] = Body(...)):
    from ..ontology.store import get_store
    try:
        rule = get_store().update_rule(rid, body)
        if not rule:
            raise HTTPException(status_code=404, detail="规则不存在")
        return {"ok": True, "rule": rule.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/ontology/rules/{rid}")
def delete_rule(rid: str):
    from ..ontology.store import get_store
    if not get_store().delete_rule(rid):
        raise HTTPException(status_code=404, detail="规则不存在")
    return {"ok": True}
