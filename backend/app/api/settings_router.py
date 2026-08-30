"""设置管理路由：LLM 配置 + 知识库路径（设置弹窗「AI 模型 / 知识库」页）。

LLM：
- GET    /api/settings/llm      : 读取当前生效配置（API Key 脱敏回显）
- PUT    /api/settings/llm      : 保存配置（立即生效，api_key 留空表示保留原 Key）
- POST   /api/settings/llm/test : 用当前（或传入）配置测试连通性
- DELETE /api/settings/llm      : 恢复默认（回退环境变量/内置默认）

知识库：
- GET    /api/settings/kb       : 读取知识库路径（生效路径 / 默认路径 / 是否自定义）
- PUT    /api/settings/kb       : 保存知识库路径（立即生效，空串恢复默认）
- DELETE /api/settings/kb       : 恢复默认路径
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import kb_settings, llm_settings

router = APIRouter()


class LlmConfigRequest(BaseModel):
    base_url: Optional[str] = Field(None, description="OpenAI 兼容 base url")
    api_key: Optional[str] = Field(None, description="API Key；空串/缺省表示保留原 Key")
    model: Optional[str] = Field(None, description="模型名")


def _public_cfg(cfg: dict) -> dict:
    """对外返回脱敏配置。"""
    return {
        "base_url": cfg["base_url"],
        "model": cfg["model"],
        "api_key_masked": llm_settings.mask_key(cfg["api_key"]),
        "has_api_key": bool(cfg["api_key"]),
    }


@router.get("/api/settings/llm")
def get_llm_config():
    """读取当前生效的 LLM 配置。"""
    cfg = llm_settings.get_llm_cfg()
    return {"ok": True, "config": _public_cfg(cfg)}


@router.put("/api/settings/llm")
def save_llm_config(req: LlmConfigRequest):
    """保存 LLM 配置并立即生效（无需重启服务）。"""
    cfg = llm_settings.save_llm_cfg(
        base_url=req.base_url,
        api_key=req.api_key,
        model=req.model,
    )
    return {"ok": True, "config": _public_cfg(cfg)}


@router.post("/api/settings/llm/test")
def test_llm_config(req: Optional[LlmConfigRequest] = None):
    """测试 LLM 连通性：传入字段可临时覆盖当前配置进行验证（不影响已保存配置）。"""
    import json
    import urllib.error
    import urllib.request

    cfg = llm_settings.get_llm_cfg()
    if req is not None:
        if req.base_url is not None and req.base_url.strip():
            cfg["base_url"] = req.base_url.strip().rstrip("/")
        if req.api_key is not None and req.api_key.strip():
            cfg["api_key"] = req.api_key.strip()
        if req.model is not None and req.model.strip():
            cfg["model"] = req.model.strip()

    if not cfg.get("api_key"):
        return {"ok": False, "message": "未配置 API Key，请先填写并保存"}

    # 直连远端（绕过本机 HTTPS_PROXY，与 llm_strategy._call_llm 一致），
    # 不吞异常以便准确区分 连接失败/超时/401 鉴权失败 等
    url = f"{cfg['base_url']}/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": "ping，请只回复 pong"}],
        "temperature": 0.0,
        "max_tokens": 8,
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    })
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    started = time.time()
    try:
        with opener.open(request, timeout=15.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        latency_ms = int((time.time() - started) * 1000)
        reason = (e.read().decode("utf-8", "ignore") or e.reason or "")[:120]
        return {"ok": False, "message": f"HTTP {e.code}：{reason}", "latency_ms": latency_ms}
    except Exception as e:  # noqa: BLE001
        latency_ms = int((time.time() - started) * 1000)
        return {"ok": False, "message": f"连接失败：{e}", "latency_ms": latency_ms}

    latency_ms = int((time.time() - started) * 1000)
    try:
        msg = (data.get("choices") or [{}])[0].get("message", {}) or {}
        # 兼容推理模型：content 为空时取 reasoning_content
        reply = (msg.get("content") or msg.get("reasoning_content") or "").strip()
    except Exception:  # noqa: BLE001
        reply = ""
    if not reply:
        return {"ok": False, "message": "连接成功但模型无返回内容", "latency_ms": latency_ms}
    return {"ok": True, "message": "连接成功", "reply": reply[:32], "latency_ms": latency_ms}


@router.delete("/api/settings/llm")
def reset_llm_config():
    """恢复默认配置（清除设置弹窗保存的动态配置，回退环境变量/内置默认）。"""
    cfg = llm_settings.reset_llm_cfg()
    return {"ok": True, "config": _public_cfg(cfg)}


# ------------------------- 知识库路径设置 -------------------------


class KbConfigRequest(BaseModel):
    root_path: Optional[str] = Field(None, description="知识库根目录；空串/缺省表示恢复默认路径")


def _public_kb_cfg(cfg: dict) -> dict:
    return {
        "root_path": cfg["root_path"],
        "default_path": cfg["default_path"],
        "configured": cfg["configured"],
    }


@router.get("/api/settings/kb")
def get_kb_config():
    """读取当前生效的知识库路径。"""
    cfg = kb_settings.get_kb_cfg()
    return {"ok": True, "config": _public_kb_cfg(cfg)}


@router.put("/api/settings/kb")
def save_kb_config(req: KbConfigRequest):
    """保存知识库根目录并立即生效（无需重启；会尝试创建目录以校验可写性）。"""
    try:
        cfg = kb_settings.save_kb_cfg((req.root_path or "").strip())
    except ValueError as e:
        return {"ok": False, "message": str(e)}
    return {"ok": True, "config": _public_kb_cfg(cfg)}


@router.delete("/api/settings/kb")
def reset_kb_config():
    """恢复默认知识库路径。"""
    cfg = kb_settings.reset_kb_cfg()
    return {"ok": True, "config": _public_kb_cfg(cfg)}
