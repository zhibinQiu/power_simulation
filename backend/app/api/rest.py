"""API 层 REST 小工具：统一回执 + 端点包装（消除各路由重复的样板）。

平台 REST 约定：成功直接返回业务 dict（含 ok=True），失败返回
``{"ok": False, "error": "<可操作的中文文案>"}``——前端统一弹该文案，因此
「异常 → 文案」的转换集中在 json_api 一个地方，路由里只写正常路径。
"""
from __future__ import annotations

import functools
from typing import Any, Dict


def err(msg: str) -> Dict[str, Any]:
    """失败回执。"""
    return {"ok": False, "error": msg}


def json_api(err_prefix: str, *, allow_empty: bool = False):
    """POST 端点统一包装（装饰器）：请求体校验 + 异常 → 中文回执。

    各端点原先各自重复「isinstance 校验 + try/except ValueError + except Exception →
    回执」三件套。业务函数只留正常路径：参数不合法抛 ValueError（文案直接回显给
    用户），其余异常由本装饰器加统一前缀兜底。

    :param err_prefix: 非 ValueError 异常的回执前缀（如「同步中间件失败」）
    :param allow_empty: True 时请求体缺失/非对象按空对象处理（可选参数型端点）

    functools.wraps 保留 __wrapped__，FastAPI 仍按被装饰函数的签名解析请求体。
    """

    def _deco(fn):
        @functools.wraps(fn)
        def _wrap(payload: Any = None):
            if not isinstance(payload, dict):
                if not allow_empty:
                    return err("请求体必须为 JSON 对象")
                payload = {}
            try:
                return fn(payload)
            except ValueError as e:
                return err(str(e))
            except Exception as e:  # noqa: BLE001
                return err(f"{err_prefix}：{e}")
        return _wrap
    return _deco
