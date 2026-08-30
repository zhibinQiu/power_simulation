"""核心仿真域用例门面：对 API 层屏蔽引擎/解析/元数据等实现细节。

变更业务（如换算法引擎、换解析策略、调整参数元数据）只需改动本服务或 domain 层，
API 路由与前端契约保持不变。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..carbon_engine import cached_simulate, conservation_audit, sim_cache_stats
from ..devices import library_payload
from ..factors import default_factors
from ..llm_strategy import chat_completion, chat_completion_stream, llm_parse
from ..models import ParseResult, ParsedOp, ProcessModel, SimulateRequest, SimulateResponse
from ..nl_parser import apply_ops, parse_strategy
from ..param_schema import PARAM_SCHEMA, TECHS_INFO, UNIT_TYPES_INFO
from .. import presets

# 各模式系统提示词（与前端 CMD_MODES 保持一致）
CHAT_MODE_PROMPTS = {
    "chat": (
        "你是「本析智擎」，钢铁企业能碳智控平台的智能助手，专注钢铁企业节能减碳与平台系统数据。"
        "职责范围：1) 钢铁企业节能减碳问询与策略——能耗分析、碳排放核算（工序碳排、碳元素守恒）、"
        "节能降碳措施、关键工艺指标（焦比、高炉利用系数、转炉/电炉工序、吨钢综合能耗等）；"
        "2) 平台系统相关数据问询——设备状态、仿真系统参数与运行、能碳一体机管理、数据指标查询。"
        "超出以上范围的闲聊或与钢铁能碳无关的话题（天气、娱乐、新闻、情感等），一律礼貌回绝，"
        "说明自己只回答钢铁企业节能减碳与系统数据相关的问题，并引导用户提出相关问询。"
        "回答专业、简洁、条理清晰，可适当引用钢铁行业常识，但不得编造具体数值；"
        "涉及平台实时数据时，提示以平台实际数据为准。"
    ),
    "code": "你是一个资深程序员助手。优先给出可运行、带注释的代码，并解释关键思路；遇到报错帮助定位问题。",
    "plan": "你是一个项目规划助手。把用户诉求拆成有序、可执行的步骤，标注依赖与优先级，输出清单式计划。",
}


class SimulationService:
    """仿真/解析/扫描/审计/聊天等核心用例的门面。"""

    # ------------------------- 元数据 / 预置 -------------------------

    def get_preset(self) -> ProcessModel:
        return presets.default_model()

    def get_preset_strategies(self) -> List[Dict[str, Any]]:
        return presets.preset_strategies()

    def get_factors(self) -> Dict[str, Any]:
        """默认排放因子表（燃料 NCV/CC、电网因子、碳酸盐/电极因子）。"""
        return default_factors()

    def get_param_schema(self) -> Dict[str, Any]:
        """工序参数分级元数据 + 技术/单位类型说明，供前端编辑器渲染。"""
        return {
            "schema": PARAM_SCHEMA,
            "unit_types": UNIT_TYPES_INFO,
            "techs": TECHS_INFO,
            "kinds": {
                "config": "给定约束/因变量：由工厂既定条件决定，提供参考范围，不在策略自动优化范围",
                "optim": "节能减排决策变量/自变量：会直接影响能耗与碳排的操作与配比杠杆",
            },
        }

    def get_devices(self) -> Dict[str, Any]:
        """内置监测设备库：设备类型 + 工序设备规格 + 档位库。"""
        return library_payload()

    def cache_stats(self) -> Dict[str, Any]:
        """仿真缓存命中率（诊断用）。"""
        return sim_cache_stats()

    # ------------------------- 解析 / 仿真 -------------------------

    def parse(self, text: str, units: Optional[List[Dict[str, Any]]] = None) -> ParseResult:
        """自然语言策略解析：优先 LLM，失败回退确定性启发式。"""
        res = llm_parse(text, units)
        if res is None:
            res = parse_strategy(text, units)
        return res

    def simulate(self, req: SimulateRequest) -> SimulateResponse:
        """执行基线仿真，必要时叠加策略操作并计算前后 delta。"""
        baseline = cached_simulate(req.model, req.factors)
        resp = SimulateResponse(baseline=baseline)
        if req.ops:
            applied = apply_ops(req.model, req.ops)
            strategy = cached_simulate(applied)
            resp.strategy = strategy
            b, s = baseline.totals, strategy.totals
            resp.delta = {
                "co2_total": round(s.co2_total - b.co2_total, 2),
                "co2_direct": round(s.co2_direct - b.co2_direct, 2),
                "co2_indirect": round(s.co2_indirect - b.co2_indirect, 2),
                "intensity": round(s.intensity - b.intensity, 1),
                "carbon_utilization": round(s.carbon_utilization - b.carbon_utilization, 4),
                "steel_output": round(s.steel_output - b.steel_output, 1),
                "co2_reduction_pct": round((1 - s.co2_total / b.co2_total) * 100, 1) if b.co2_total else 0.0,
            }
        return resp

    def apply(self, model: ProcessModel, ops: List[ParsedOp],
              factors: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """对当前流程直接应用一组操作（无需保存策略）。"""
        applied = apply_ops(model, ops)
        return {"model": applied, "sim": cached_simulate(applied, factors)}

    # ------------------------- 求解 / 分析 -------------------------

    def audit(self, model: ProcessModel) -> Dict[str, Any]:
        """碳元素守恒审计：逐工序核对碳输入与各去向闭合余量。"""
        return conservation_audit(model, None)

    # ------------------------- 聊天 -------------------------

    def _history_messages(self, history: List) -> List[dict]:
        """把前端历史（[["user", "..."], ...] 或 [{"role":..., "content":...}, ...]）
        统一转为 OpenAI 消息列表。"""
        out: List[dict] = []
        for pair in (history or [])[-12:]:
            if isinstance(pair, dict):
                role = pair.get("role")
                content = pair.get("content")
                if role in ("user", "assistant") and content:
                    out.append({"role": role, "content": str(content)})
            elif isinstance(pair, (list, tuple)) and len(pair) == 2:
                out.append({"role": pair[0], "content": str(pair[1])})
        return out

    def resolve_skills(self, agent_id: str, skills: List[str]) -> List[str]:
        """按智能体白名单解析本次对话可用的 skill 列表。

        - 用户显式选择的技能仅作「提示」：优先排在前面；
        - 白名单（available_skills）内其余技能也全部纳入，由智能体根据问题
          自主检索合适的技能；available_skills 为 None 时使用全部已注册技能。
        """
        from app.agents.registry import get_agent
        from app.skills.registry import get_registry

        agent = get_agent(agent_id)
        registry = get_registry()
        allow = agent.available_skills
        # 用户提示技能也须在白名单内（available_skills=None 不限制），白名单外提示会被忽略
        chosen = [s for s in (skills or [])
                  if registry.get(s) is not None and (allow is None or s in allow)]
        if allow is not None:
            candidates = [n for n in allow if registry.get(n) is not None]
        else:
            candidates = list(registry.names(enabled_only=False))
        result = list(chosen)  # 用户提示排前
        for n in candidates:
            if n not in result:
                result.append(n)
        return result

    def chat(self, text: str, history: List, mode: str,
             agent: str = "", skills: List[str] = None) -> Dict[str, Any]:
        """命令行窗口的自然语言对话（复用已配置的 LLM）。

        agent 非空时走 LangGraph 多智能体（可调用 skills）；否则保持传统单轮聊天。
        """
        if agent:
            from app.agents.graph import agent_chat
            from app.agents.registry import get_agent

            a = get_agent(agent)
            skill_names = self.resolve_skills(agent, skills or [])
            history_msgs = self._history_messages(history)
            try:
                import asyncio
                reply = asyncio.run(agent_chat(a, skill_names, text, history_msgs))
                return {"ok": True, "mode": mode, "agent": agent,
                        "skills": skill_names, "reply": reply}
            except Exception:  # noqa: BLE001
                return {"ok": False, "mode": mode, "agent": agent, "reply": None}
        sys_prompt = CHAT_MODE_PROMPTS.get(mode, CHAT_MODE_PROMPTS["chat"])
        messages = [{"role": "system", "content": sys_prompt}]
        for pair in (history or [])[-12:]:
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                messages.append({"role": pair[0], "content": str(pair[1])})
        messages.append({"role": "user", "content": text})
        reply = chat_completion(messages)
        if reply is None:
            return {"ok": False, "mode": mode,
                    "reply": "（模型未配置或未连通：请在后端设置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 后重启）"}
        return {"ok": True, "mode": mode, "reply": reply}

    def agent_chat_stream(self, text: str, history: List, agent: str,
                          skills: List[str] = None):
        """多智能体流式聊天：返回 async generator（SSE 事件序列）。

        事件含 {"type":"status"}（技能调用提示）与 {"type":"delta"}（回复增量）。
        注意：本方法为普通函数（非 generator function），返回 async generator 对象；
        不能并入 chat_stream（其含同步 yield 是 generator function，return 会失效）。
        """
        from app.agents.graph import agent_chat_events
        from app.agents.registry import get_agent

        a = get_agent(agent)
        skill_names = self.resolve_skills(agent, skills or [])
        history_msgs = self._history_messages(history)

        async def _agent_gen():
            sent = False
            async for ev in agent_chat_events(a, skill_names, text, history_msgs):
                sent = True
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            if not sent:
                yield (f"data: {json.dumps({'type': 'delta', 'delta': '（模型未配置或未连通：请在后端设置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 后重启）'}, ensure_ascii=False)}\n\n")

        return _agent_gen()

    def chat_stream(self, text: str, history: List, mode: str):
        """流式聊天（传统单轮）：按 SSE（data: {"delta": "..."}）逐段产出增量回复文本。

        多智能体（agent/skills）请走 agent_chat_stream。未连通 LLM 时产出兜底提示。
        """
        sys_prompt = CHAT_MODE_PROMPTS.get(mode, CHAT_MODE_PROMPTS["chat"])
        messages = [{"role": "system", "content": sys_prompt}]
        for pair in (history or [])[-12:]:
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                messages.append({"role": pair[0], "content": str(pair[1])})
        messages.append({"role": "user", "content": text})
        sent = False
        for chunk in chat_completion_stream(messages):
            sent = True
            yield f"data: {json.dumps({'delta': chunk}, ensure_ascii=False)}\n\n"
        if not sent:
            yield f"data: {json.dumps({'delta': '（模型未配置或未连通：请在后端设置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 后重启）'}, ensure_ascii=False)}\n\n"


# 模块级单例（应用服务无状态，可安全共享）
simulation_service = SimulationService()
