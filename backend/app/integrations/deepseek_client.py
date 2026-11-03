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
from app.domain.strategy.llm_strategy import chat_completion_detail as _chat_completion_detail

# 长文报告（履约综合分析等八章报告）的输出预算。deepseek-reasoner 的思维链与正文
# 共用 max_tokens：实测八章正文约 6k tokens、思维链 7k—12k，旧值 16384 只剩 3k 余量，
# 思维链稍长正文就在「企业与履约形势研判」处被硬截断，故抬到 32768。
LONG_FORM_MAX_TOKENS = 32768
# 短问答（政策条目质检、行业实践撰写）也别再用 2048：光是思维链就能吃掉 1900+，
# 正文只剩一两百字符，JSON 判定会直接解析失败而静默降级。
SHORT_FORM_MAX_TOKENS = 4096


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
    max_tokens: int = SHORT_FORM_MAX_TOKENS,
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
    max_tokens: int = SHORT_FORM_MAX_TOKENS,
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
    max_tokens: int = SHORT_FORM_MAX_TOKENS,
    unlimited_output: bool = False,
    **kwargs: Any,
) -> AsyncIterator[Dict[str, Any]]:
    """流式补全（垫片：一次性返回全部文本）。

    part 结构：{"kind": "content"|"error"|"truncated", "text": str}
    truncated 表示模型把输出预算用完了、正文没写完（HTTP 仍是 200）。
    """
    if not is_configured():
        yield {"kind": "error", "text": "语言模型未配置"}
        return
    if unlimited_output:
        # 长文场景（履约综合分析等八章报告）需要远大于 4K 的输出预算
        max_tokens = max(max_tokens, LONG_FORM_MAX_TOKENS)
    text, finish = _chat_completion_detail(messages, timeout=timeout, max_tokens=max_tokens)
    if not text:
        yield {"kind": "error", "text": "语言模型调用失败或无返回"}
        return
    yield {"kind": "content", "text": text}
    if finish == "length":
        # 正文在半章处被截断：必须显式告诉调用方，否则半篇报告会被当成完整报告存下来
        yield {"kind": "truncated", "text": f"模型输出达到 max_tokens={max_tokens} 上限，正文未写完"}
