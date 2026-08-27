# -*- coding: utf-8 -*-
"""DeepSeek 客户端（simulation 项目的适配垫片）。

接口与 pdf_trans 的 app.integrations.deepseek_client 对齐，底层委托
app.llm_strategy.chat_completion（同步 urllib 调用 OpenAI 兼容接口）。
未配置 LLM_API_KEY 时 is_configured() 返回 False，算法模块会自动走内置兜底逻辑。
"""
from __future__ import annotations

import os
from typing import Any, AsyncIterator, Dict, List, Optional

from ..llm_strategy import chat_completion as _chat_completion_sync


def is_configured() -> bool:
    """是否配置了 LLM API Key（环境变量或 config/.env）。"""
    return bool(os.getenv("LLM_API_KEY", "").strip())


def _choice(message: str) -> Dict[str, Any]:
    return {
        "index": 0,
        "message": {"role": "assistant", "content": message},
        "finish_reason": "stop",
    }


def chat_completion_sync(
    messages: List[dict],
    *,
    temperature: float = 0.3,
    timeout: float = 120.0,
    max_tokens: int = 2048,
) -> Optional[Dict[str, Any]]:
    """同步补全（垫片：非流式），返回 OpenAI choices[0] 结构；失败返回 None。"""
    text = _chat_completion_sync(messages, timeout=timeout, max_tokens=max_tokens)
    if not text:
        return None
    return _choice(text)


async def chat_completion_message_async(
    *,
    messages: List[dict],
    temperature: float = 0.3,
    timeout: float = 120.0,
    max_tokens: int = 2048,
) -> Optional[Dict[str, Any]]:
    """异步补全消息（垫片：内部同步实现）。

    返回 OpenAI choices[0] 结构 {"message": {"content": ...}}；未配置/失败返回 None。
    """
    return chat_completion_sync(
        messages, temperature=temperature, timeout=timeout, max_tokens=max_tokens
    )


async def chat_completion_stream_parts(
    *,
    messages: List[dict],
    temperature: float = 0.35,
    timeout: float = 360.0,
    max_tokens: int = 2048,
    unlimited_output: bool = False,
    **kwargs: Any,
) -> AsyncIterator[Dict[str, Any]]:
    """流式补全（垫片：一次性返回全部文本）。

    part 结构：{"kind": "content"|"error", "text": str}
    """
    if not is_configured():
        yield {"kind": "error", "text": "语言模型未配置"}
        return
    if unlimited_output:
        max_tokens = max(max_tokens, 4096)
    text = _chat_completion_sync(messages, timeout=timeout, max_tokens=max_tokens)
    if not text:
        yield {"kind": "error", "text": "语言模型调用失败或无返回"}
        return
    yield {"kind": "content", "text": text}
