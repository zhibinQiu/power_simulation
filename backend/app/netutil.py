"""共享网络工具（兼容转发层，实现位于 core/netutil.py）。

新代码请从 app.core.netutil 导入；本模块保留以兼容既有 import。
"""
from .core.netutil import UA, TtlCache, fetch_json, fetch_text, now_iso

__all__ = ["UA", "TtlCache", "fetch_json", "fetch_text", "now_iso"]
