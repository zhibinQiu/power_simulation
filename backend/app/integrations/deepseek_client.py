# -*- coding: utf-8 -*-
"""DeepSeek 客户端（simulation 项目的适配垫片）。

接口与 pdf_trans 的 app.integrations.deepseek_client 对齐，底层委托
app.llm_strategy.chat_completion（同步 urllib 调用 OpenAI 兼容接口）。
未配置 LLM_API_KEY 时 is_configured() 返回 False，算法模块会自动走内置兜底逻辑。
"""
from __future__ import annotations

import os
from typing import Any, AsyncIterator, Dict, List, Optional

from app.domain.strategy.llm_strategy import chat_completion as _chat_completion_sync


def is_configured() -> bool:
    """是否配置了 LLM API Key。

    取值口径必须与 llm_strategy._llm_cfg 一致（动态配置 > 环境变量 > 默认值），
    否则「config/llm_cfg.json 或设置页里填了 key、但进程环境变量没写」时会被误判为
    未配置，报告直接落到兜底文本。JsonCfgStore.get() 本身不写回 os.environ，
    只有 save() 才写，所以这里不能只看环境变量。
    """
    try:
        from app.settings.llm_settings import get_llm_cfg

        return bool(str(get_llm_cfg().get("api_key") or "").strip())
    except Exception:  # noqa: BLE001 —— 配置读取异常时回退环境变量，不阻断调用
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
        # 长文场景（履约综合分析等八章报告）需要远大于 4K 的输出预算，
        # deepseek-reasoner 单次输出上限 64K，这里取 16K 兼顾完整性与等待时长。
        max_tokens = max(max_tokens, 16384)
    text = _chat_completion_sync(messages, timeout=timeout, max_tokens=max_tokens)
    if not text:
        yield {"kind": "error", "text": "语言模型调用失败或无返回"}
        return
    yield {"kind": "content", "text": text}
