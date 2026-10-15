"""HTTP 出口（core/http）：外部 API 调用的唯一低层封装。

此前 urllib 调用散落在 cloud_agent / github_deploy / llm_strategy / settings_router
四处，各自重复实现两件事：

- 「绕过本机 HTTPS_PROXY」：开发机常设 HTTPS_PROXY=127.0.0.1:xxxx，
  urllib 会把外部请求交给本地代理而失败，必须显式 `ProxyHandler({})`；
  这段 hack 连同解释注释被复制了 4 份；
- 「POST JSON → 解析响应」：构造 Request、encode、json.loads、异常分类，
  每处写法都略有不同（有的吞异常、有的记 body）。

本模块收敛这两件事。调用方仍可按需处理异常，因此**不吞异常**
（settings_router 需要区分 HTTPError 与其它错误来给出不同提示）。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


def no_proxy_opener() -> urllib.request.OpenerDirector:
    """绕过本机代理的 opener（外部 API 直连用）。

    本机若设了 HTTPS_PROXY（如 127.0.0.1:53483），urllib 默认会把请求交给它，
    访问 api.deepseek.com 这类外部地址会失败 —— 显式传空 ProxyHandler 即直连。
    """
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def post_json(
    url: str,
    payload: Any,
    *,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 30.0,
    opener: Optional[urllib.request.OpenerDirector] = None,
) -> Any:
    """POST 一个 JSON 体并解析 JSON 响应。

    异常（URLError / HTTPError / ValueError / OSError）**向上抛出**，
    由调用方按自身语义处理（降级返回 None、或区分鉴权失败给提示）。
    """
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        **(headers or {}),
    })
    op = opener or no_proxy_opener()
    with op.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def open_stream(
    url: str,
    payload: Any,
    *,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 300.0,
    opener: Optional[urllib.request.OpenerDirector] = None,
):
    """POST 一个 JSON 体并返回**未关闭的**响应对象（供 SSE 流式逐行读取）。

    调用方负责关闭（with / close）。响应对象按行可迭代。
    """
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        **(headers or {}),
    })
    op = opener or no_proxy_opener()
    return op.open(req, timeout=timeout)


def http_error_body(exc: BaseException, limit: int = 400) -> str:
    """取 HTTPError 的响应体（排查 401/400 这类带原因的错误很有用）。"""
    if isinstance(exc, urllib.error.HTTPError):
        try:
            return (exc.read().decode("utf-8", "ignore") or exc.reason or "")[:limit]
        except Exception:  # noqa: BLE001
            return str(exc.reason or "")
    return ""
