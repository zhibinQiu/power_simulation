"""智能体存储：动态管理「本析智擎」中的智能体。

- 内置 5 个默认智能体（builtin=True，可编辑但不可删除）
- 用户可新增自定义智能体 / 修改系统提示词 / 调整 Skills 白名单
- 文件：backend/data/agents.json（线程安全持久化）
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
AGENTS_FILE = DATA_DIR / "agents.json"

_APP_CONTEXT = (
    "你是「本析智擎」，面向全行业的能碳智控智能助手。"
    "你服务于各类工业与能源场景，可解答关于生产工艺、设备运行、能耗、"
    "碳排放、碳市场行情与减碳策略的问题（覆盖钢铁、化工、建材、"
    "有色金属等全行业）。"
    "回答要专业、准确、简洁，涉及数据时优先引用工具查询的真实数据，"
    "不要编造数据；涉及平台功能时可说明操作路径。"
)


@dataclass
class Agent:
    id: str
    name: str
    emoji: str
    description: str
    system_prompt: str
    default_skills: List[str] = field(default_factory=list)
    # None 表示可用全部 skills；否则为可用 skill 名列表（白名单）
    available_skills: Optional[List[str]] = None
    builtin: bool = False
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "emoji": self.emoji,
            "description": self.description, "system_prompt": self.system_prompt,
            "default_skills": list(self.default_skills),
            "available_skills": list(self.available_skills) if self.available_skills is not None else None,
            "builtin": self.builtin, "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Agent":
        d = dict(d or {})
        return Agent(
            id=d.get("id") or "", name=d.get("name") or "",
            emoji=d.get("emoji") or "🤖",
            description=d.get("description") or "",
            system_prompt=d.get("system_prompt") or "",
            default_skills=list(d.get("default_skills") or []),
            available_skills=(
                list(d["available_skills"]) if d.get("available_skills") is not None else None
            ),
            builtin=bool(d.get("builtin")),
            created_at=float(d.get("created_at") or 0),
            updated_at=float(d.get("updated_at") or 0),
        )


# 内置默认智能体（首次加载写入文件）
_SEED_AGENTS: List[Dict[str, Any]] = [
    {
        "id": "general", "name": "通用助手", "emoji": "🤖",
        "description": "全能助手，可解答平台各类问题并调用全部技能",
        "system_prompt": (
            _APP_CONTEXT +
            "你是默认入口。面对不确定的需求时，可先调用相应技能获取真实数据再作答。"
        ),
        "default_skills": ["query_realtime_devices", "run_simulation",
                           "get_carbon_market_quote", "get_emission_factors"],
        "available_skills": None,
        "builtin": True,
    },
    {
        "id": "data_analyst", "name": "数据分析师", "emoji": "📊",
        "description": "擅长设备数据查询、历史趋势与仿真结果解读",
        "system_prompt": (
            _APP_CONTEXT +
            "你的专长是数据分析：设备实时读数、历史序列、工艺仿真结果。"
            "回答时给出关键数值与简单解读，必要时用对比说明趋势。"
        ),
        "default_skills": ["query_realtime_devices", "query_device_history", "run_simulation"],
        "available_skills": ["query_realtime_devices", "query_device_history", "run_simulation"],
        "builtin": True,
    },
    {
        "id": "device_expert", "name": "设备运维专家", "emoji": "🔧",
        "description": "关注设备运行状态与历史数据，辅助故障排查",
        "system_prompt": (
            _APP_CONTEXT +
            "你的专长是设备运维：实时读数、历史采样、异常排查。"
            "描述设备状态时给出当前值、单位与判断依据。"
        ),
        "default_skills": ["query_realtime_devices", "query_device_history"],
        "available_skills": ["query_realtime_devices", "query_device_history"],
        "builtin": True,
    },
    {
        "id": "carbon_advisor", "name": "低碳减排顾问", "emoji": "🌿",
        "description": "围绕能耗、排放、强度与减排技术给出减碳建议",
        "system_prompt": (
            _APP_CONTEXT +
            "你的专长是节能减排：运行仿真了解各生产环节能耗与碳排放，结合排放因子"
            "给出降碳建议（如能效提升、工艺优化、技术应用），并可用碳价判断经济性。"
        ),
        "default_skills": ["run_simulation", "get_carbon_market_quote",
                           "get_emission_factors"],
        "available_skills": ["run_simulation", "get_carbon_market_quote",
                             "get_emission_factors", "get_carbon_forecast",
                             "query_realtime_devices",
                             "compute_carbon_accounting", "evaluate_carbon_compliance",
                             "judge_carbon_market_cycle",
                             "forecast_carbon_price_to_year_end",
                             "compute_cea_carry_forward", "recommend_carbon_strategy",
                             "query_carbon_enterprise_ledger", "list_carbon_enterprises"],
        "builtin": True,
    },
    {
        "id": "market_analyst", "name": "碳市场分析师", "emoji": "📈",
        "description": "专注全国碳市场行情、价格走势与预测",
        "system_prompt": (
            _APP_CONTEXT +
            "你的专长是碳市场：CEA/CCER 最新行情、历史走势、价格预测。"
            "回答引用工具返回的真实行情数据，给出涨跌幅与趋势判断。"
        ),
        "default_skills": ["get_carbon_market_quote", "get_carbon_forecast"],
        "available_skills": ["get_carbon_market_quote", "get_carbon_forecast",
                             "get_emission_factors",
                             "judge_carbon_market_cycle",
                             "forecast_carbon_price_to_year_end"],
        "builtin": True,
    },
    {
        "id": "compliance_advisor", "name": "履约合规顾问", "emoji": "🧾",
        "description": "专注碳排放核算、履约缺口、碳配额结转与合规策略",
        "system_prompt": (
            _APP_CONTEXT +
            "你的专长是碳履约合规：碳排放量核算（Scope1/2）、履约缺口测算、"
            "CCER 抵扣、CEA 结转、三档履约策略与合规建议。"
            "回答优先调用方法学技能基于真实台账与公式计算，给出关键数字与计算过程；"
            "需要企业数据时先调用 list_carbon_enterprises / query_carbon_enterprise_ledger 取数。"
        ),
        "default_skills": ["compute_carbon_accounting", "evaluate_carbon_compliance",
                           "recommend_carbon_strategy", "get_carbon_market_quote"],
        "available_skills": [
            "compute_carbon_accounting", "evaluate_carbon_compliance",
            "compute_cea_carry_forward", "recommend_carbon_strategy",
            "query_carbon_enterprise_ledger", "list_carbon_enterprises",
            "judge_carbon_market_cycle", "forecast_carbon_price_to_year_end",
            "get_carbon_market_quote", "get_emission_factors", "get_carbon_forecast",
        ],
        "builtin": True,
    },
]


class AgentStore:
    """线程安全的智能体存储（单例）。"""

    def __init__(self, file_path: Optional[Path] = None) -> None:
        self._file = file_path or AGENTS_FILE
        self._lock = threading.RLock()
        self._agents: Dict[str, Agent] = {}
        self._load_or_seed()

    def _load_or_seed(self) -> None:
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            if self._file.exists():
                data = json.loads(self._file.read_text("utf-8"))
                self._agents = {
                    a["id"]: Agent.from_dict(a) for a in data.get("agents", [])
                }
                if not self._agents:
                    self._seed()
                else:
                    self._merge_seed_missing()
                logger.info("agents loaded: %d", len(self._agents))
            else:
                self._seed()
        except Exception as e:  # noqa: BLE001
            logger.warning("load agents failed(%s), re-seed", e)
            self._seed()

    def _merge_seed_missing(self) -> None:
        """把缺失的内置智能体补回（升级场景），内置定义以 seed 为准。"""
        changed = False
        for s in _SEED_AGENTS:
            if s["id"] not in self._agents:
                self._agents[s["id"]] = Agent.from_dict(s)
                changed = True
        if changed:
            self.save()

    def _seed(self) -> None:
        self._agents = {s["id"]: Agent.from_dict(s) for s in _SEED_AGENTS}
        self.save()

    def save(self) -> None:
        with self._lock:
            payload = {"agents": [a.to_dict() for a in self._agents.values()],
                       "updated_at": time.time()}
            tmp = self._file.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
            os.replace(tmp, self._file)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            out = []
            for a in self._agents.values():
                d = a.to_dict()
                out.append(d)
            return out

    def get(self, agent_id: str) -> Optional[Agent]:
        with self._lock:
            return self._agents.get(agent_id)

    def get_or_default(self, agent_id: str) -> Agent:
        a = self.get(agent_id or "general")
        return a if a else self._agents.get("general", self._agents.get("data_analyst"))

    def add(self, data: Dict[str, Any]) -> Agent:
        with self._lock:
            agent = Agent.from_dict(dict(data, builtin=False))
            if not agent.id:
                agent.id = f"custom_{uuid.uuid4().hex[:8]}"
            if not agent.name.strip():
                raise ValueError("智能体名称不能为空")
            if not agent.system_prompt.strip():
                raise ValueError("系统提示词不能为空")
            if agent.id in self._agents:
                raise ValueError(f"智能体 id「{agent.id}」已存在")
            agent.created_at = time.time()
            agent.updated_at = agent.created_at
            agent.builtin = False
            self._agents[agent.id] = agent
            self.save()
            return agent

    def update(self, agent_id: str, data: Dict[str, Any]) -> Optional[Agent]:
        with self._lock:
            agent = self._agents.get(agent_id)
            if not agent:
                return None
            new_data = {**agent.to_dict(),
                        **{k: v for k, v in data.items() if k not in ("id", "created_at", "builtin")}}
            new_data["updated_at"] = time.time()
            updated = Agent.from_dict(new_data)
            updated.builtin = agent.builtin
            if not updated.name.strip():
                raise ValueError("智能体名称不能为空")
            if not updated.system_prompt.strip():
                raise ValueError("系统提示词不能为空")
            self._agents[agent_id] = updated
            self.save()
            return updated

    def delete(self, agent_id: str) -> bool:
        with self._lock:
            agent = self._agents.get(agent_id)
            if not agent:
                return False
            if agent.builtin:
                raise ValueError("内置智能体不可删除")
            del self._agents[agent_id]
            self.save()
            return True

    def reset(self) -> None:
        with self._lock:
            self._seed()


_store: Optional[AgentStore] = None
_store_lock = threading.Lock()


def get_store() -> AgentStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = AgentStore()
    return _store
