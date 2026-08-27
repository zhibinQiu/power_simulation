# -*- coding: utf-8 -*-
"""SearXNG 联网搜索服务（simulation 项目的适配垫片）。

接口与 pdf_trans 的 app.services.searxng_service 对齐。simulation 项目未部署
SearXNG，is_enabled() 恒为 False，search_web() 抛出 SearxngNotConfiguredError，
让算法模块走内置兜底逻辑（规则过滤 / 政策回退）。
"""
from __future__ import annotations


class SearxngNotConfiguredError(RuntimeError):
    """SearXNG 未配置或不可用。"""


class SearxngSearchError(RuntimeError):
    """SearXNG 搜索执行失败。"""


def is_enabled(db=None) -> bool:
    """simulation 项目不内置 SearXNG 实例，恒为 False。"""
    return False


def search_web(query, *, page=1, page_size=20, db=None):
    """联网搜索（垫片：不实现，抛出未配置异常）。"""
    raise SearxngNotConfiguredError("SearXNG 未配置，联网搜索不可用")
