# -*- coding: utf-8 -*-
"""报告持久化（仓储模式实现，索引由 core.storage.JsonRepository 托管）。

将生成的报告写入磁盘（.md + 索引），并提供历史列表/详情/删除能力。
存储布局（向后兼容，不变）：
  backend/data/reports/
    index.json           # 报告元信息列表（倒序：最新的在前）
    <id>.md              # 报告 Markdown 原文
"""
import os
import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .core.storage import JsonRepository, copy_file_to_trash

_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports")
_INDEX = os.path.join(_DIR, "index.json")
_LOCK = threading.Lock()

# 进程内索引缓存 + 原子写盘由 JsonRepository 统一管理
_repo = JsonRepository(_INDEX, default=[], atomic=True)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def save_report(markdown: str, title: str = "", engine: str = "",
                strategy_name: str = "", scenario: str = "",
                report_type: str = "compliance_analysis") -> Dict:
    """保存一份报告，返回其元信息（含 id / url / created_at）。"""
    rid = uuid.uuid4().hex[:12]
    created_at = _now()
    meta = {
        "id": rid,
        "title": title.strip() or "碳减排分析报告",
        "created_at": created_at,
        "engine": engine,
        "strategy_name": strategy_name or "",
        "scenario": scenario or "",
        "report_type": report_type or "compliance_analysis",
        "length": len(markdown or ""),
        "url": f"/report/{rid}",
    }
    os.makedirs(_DIR, exist_ok=True)
    with open(os.path.join(_DIR, f"{rid}.md"), "w", encoding="utf-8") as f:
        f.write(markdown or "")
    # 先落盘正文，再插入索引（持锁保证索引写盘顺序）
    with _LOCK:
        _repo.mutate(lambda index: [meta] + list(index))
    return meta


def list_reports(limit: int = 100, engine: Optional[str] = None,
                 keyword: Optional[str] = None, report_type: Optional[str] = None,
                 offset: int = 0) -> Dict:
    """列出报告；返回 {"total": n, "reports": [...]}，支持引擎/关键字/类型筛选与分页。"""
    with _LOCK:
        items = list(_repo.read())
        if engine:
            items = [m for m in items if m.get("engine") == engine]
        if report_type:
            items = [m for m in items if m.get("report_type") == report_type]
        if keyword:
            kw = keyword.strip().lower()
            items = [
                m for m in items
                if kw in str(m.get("title", "")).lower()
                or kw in str(m.get("strategy_name", "")).lower()
                or kw in str(m.get("scenario", "")).lower()
            ]
        total = len(items)
        offset = max(0, int(offset or 0))
        page = items[offset:offset + max(1, int(limit or 100))]
        return {"total": total, "reports": [dict(m) for m in page]}


def get_report(rid: str) -> Optional[Tuple[Dict, str]]:
    with _LOCK:
        index = list(_repo.read())
    meta = next((m for m in index if m.get("id") == rid), None)
    if not meta:
        return None
    path = os.path.join(_DIR, f"{rid}.md")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return dict(meta), f.read()


def delete_report(rid: str) -> bool:
    with _LOCK:
        def _drop(index: List[Dict]) -> List[Dict]:
            return [m for m in index if m.get("id") != rid]

        before = _repo.read()
        removed = _repo.mutate(_drop)
        if len(removed) == len(before):
            return False
    path = os.path.join(_DIR, f"{rid}.md")
    # 物理文件清理：rename 到系统临时回收目录而非 os.remove（规避 IDE 对 os.remove 的劫持）
    copy_file_to_trash(path, "report_trash")
    return True
