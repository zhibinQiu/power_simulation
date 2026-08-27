"""策略库用例门面：CRUD / 应用 / 标记为已应用。

对 API 层屏蔽 store 的实现细节（存储介质、持久化方式可替换）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..carbon_engine import cached_simulate
from ..models import ParsedOp, ProcessModel, Strategy
from ..nl_parser import apply_ops
from ..store import store


class StrategyService:
    """策略库（保存/检索/应用策略）用例门面。"""

    def list(self) -> List[Strategy]:
        return store.list()

    def get(self, sid: str) -> Optional[Strategy]:
        return store.get(sid)

    def create(self, name: str, description: str, raw_text: str,
               ops: List[ParsedOp]) -> Strategy:
        return store.create(name=name, description=description,
                            raw_text=raw_text, ops=ops)

    def update(self, sid: str, name: Optional[str] = None, description: Optional[str] = None,
               raw_text: Optional[str] = None, ops: Optional[list] = None) -> Optional[Strategy]:
        """None 字段保持原值；ops 为 ParsedOp 列表（调用方负责从 JSON 解析）。"""
        return store.update(sid, name=name, description=description,
                            raw_text=raw_text, ops=ops)

    def delete(self, sid: str) -> bool:
        return store.delete(sid)

    def apply_to(self, sid: str, model: ProcessModel,
                 factors: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """将已保存策略应用到当前流程（标记为已应用，返回新模型 + 仿真）。"""
        s = store.get(sid)
        if not s:
            return {"error": "not found"}
        applied = apply_ops(model, s.ops)
        store.set_applied(sid, True)
        return {"model": applied, "sim": cached_simulate(applied, factors)}


# 模块级单例
strategy_service = StrategyService()
