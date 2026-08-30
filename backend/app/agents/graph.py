"""LangGraph 多智能体编排：调度智能体（规划与验收）+ 子智能体（执行）。

执行流程（用户提问后）：
1. analyze   —— 调度智能体「规划」：基于上下文补全问题 → 本体推理（概念/关系/规则）
                 → 命中可回答规则则直接给出答复；否则生成执行计划
2. worker    —— 子智能体「执行」：结合本体语义上下文 + 技能白名单，ReAct 循环
                 （LLM 决策 → 执行技能 → 观察结果 → 再决策），产出回复
3. verify    —— 调度智能体「验收」：校验回复是否满足用户需求；
                 不满足且有验收意见 → 回 worker 继续完善；满足 → 结束

事件协议（agent_chat_events 流式产出）：
  {"type":"thinking","stage":"plan|execute|verify","message":...}  阶段提示
  {"type":"reason","message":...}                                  本体命中提示
  {"type":"status","message":...}                                  技能调用提示
  {"type":"verify","pass":bool,"message":...}                      验收提示
  {"type":"delta","delta":...}                                     最终回复增量
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.llm_strategy import chat_completion, chat_completion_tools
from app.ontology.reason import get_reasoner
from app.skills.registry import get_registry

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6        # 单轮子智能体内工具调用上限
MAX_VERIFY_ROUNDS = 3      # 验收迭代上限（超过强制采纳）
MODEL_MISS_MSG = (
    "（模型未配置或未连通：请在后端设置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 后重启）"
)

_SUPERVISOR_PLAN_PROMPT = """你是「本析智擎」的调度智能体，负责规划与验收，不直接回答用户。
当前任务：基于【完整问题】【本体推理命中】与【可用技能清单】制定执行计划。
输出计划要点（简短、可执行，2-5 条），指导子智能体如何回答/查数据。只输出计划本身。"""

_SUPERVISOR_VERIFY_PROMPT = """你是「本析智擎」的调度智能体，负责验收子智能体的回复是否满足用户需求。
判断标准：
1. 是否完整回答了用户的全部提问点（含隐含的指代/追问）；
2. 数据类问题是否基于真实数据（技能返回）而非编造；
3. 是否专业、准确、可操作（建议类需给出具体措施）。
严格输出 JSON：{"pass": true/false, "comment": "验收意见（不通过时给出具体需补充/修正的内容）"}。
不要输出其它内容。"""


class AgentState(TypedDict):
    question: str                       # 原始问题
    completed_question: str             # 补全后问题
    reason: Dict[str, Any]              # 本体推理结果（ReasonResult.to_dict()）
    plan_hint: str                      # 调度智能体执行计划
    direct_reply: str                   # 本体规则直接回答（非空则跳过 worker）
    messages: List[Dict[str, Any]]      # LLM 消息（历史 + 工具往返）
    skill_names: List[str]
    tool_count: int
    rounds: int                         # worker 被调用次数（验收迭代）
    reply: str
    verified: bool
    verify_comment: str
    events: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# 调度智能体：规划（问题补全 + 本体推理 + 执行计划）
# ---------------------------------------------------------------------------
def _split_lines(text: str, width: int = 48) -> List[str]:
    """把长文本切成多行（优先在标点/空格断行），用于流式展示思考过程。"""
    out: List[str] = []
    seg = ""
    for para in (text or "").split("\n"):
        chunk = para.strip()
        if not chunk:
            continue
        while len(chunk) > width:
            cut = width
            for i in range(width, max(24, width // 2) - 1, -1):
                if chunk[i] in "，。；、,.;:：!?！? ":
                    cut = i + 1
                    break
            out.append((seg + chunk[:cut]).strip())
            seg = ""
            chunk = chunk[cut:]
        out.append((seg + chunk).strip())
        seg = ""
    return [x for x in out if x]


async def analyze_node(state: AgentState) -> Dict[str, Any]:
    question = (state.get("question") or "").strip()
    history = [m for m in (state.get("messages") or []) if m.get("role") in ("user", "assistant")]
    events: List[Dict[str, Any]] = []
    updates: Dict[str, Any] = {}

    # 1. 问题补全（LLM 优先，规则兜底）
    completed = question
    if history:
        try:
            hist_text = "\n".join(
                f"{m['role']}: {(m.get('content') or '')[:200]}" for m in history[-8:]
            )

            def _llm_complete(q: str, _h) -> Optional[str]:
                msgs = [
                    {"role": "system", "content": (
                        "你是对话理解助手。把用户最新问题基于对话历史补全为自包含、"
                        "完整的问题（补全指代与省略），保留原意。只输出补全后的问题，不要解释。"
                    )},
                    {"role": "user", "content": f"对话历史:\n{hist_text}\n\n用户最新问题: {q}\n\n补全后的问题:"},
                ]
                return chat_completion(msgs, timeout=30, max_tokens=200)

            completed = await asyncio.to_thread(
                get_reasoner().complete_question, question, history, _llm_complete
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("question completion failed: %s", e)
            completed = question
    updates["completed_question"] = completed or question
    if completed and completed != question:
        events.append({"type": "thinking", "stage": "plan",
                       "message": f"已补全问题：{completed}"})

    # 2. 本体推理（语义层：概念/关系/规则 → 能否直接回答或提供有效信息）
    reason = None
    try:
        reason = get_reasoner().reason(completed or question)
    except Exception as e:  # noqa: BLE001
        logger.warning("ontology reason failed: %s", e)
    reason_dict = reason.to_dict() if reason else {}
    updates["reason"] = reason_dict
    if reason and (reason.matched_concepts or reason.matched_rules):
        hit = "、".join(c["name"] for c in reason.matched_concepts[:6])
        rules = "、".join(r.get("name", "") for r in reason.matched_rules[:3])
        msg = f"本体推理命中：概念[{hit}]" + (f"，规则[{rules}]" if rules else "")
        events.append({"type": "reason", "message": msg})
        if reason.direct_answer:
            updates["direct_reply"] = reason.direct_answer
            events.append({"type": "reason", "message": "已命中可回答规则，将直接作答并提交验收"})
        else:
            events.append({"type": "reason", "message": "未命中直接答案规则，语义上下文已注入子智能体"})

    # 3. 调度智能体生成执行计划（LLM 失败则置空，子智能体自行决策）
    plan_hint = ""
    if reason and not updates.get("direct_reply"):
        try:
            skill_text = "、".join(state.get("skill_names") or []) or "（无）"
            evidence = (reason_dict.get("evidence") or "")[:1500]

            def _llm_plan() -> Optional[str]:
                msgs = [
                    {"role": "system", "content": _SUPERVISOR_PLAN_PROMPT},
                    {"role": "user", "content": (
                        f"【完整问题】{completed or question}\n"
                        f"【本体推理命中】\n{evidence}\n"
                        f"【可用技能】{skill_text}\n"
                        "请给出执行计划："
                    )},
                ]
                return chat_completion(msgs, timeout=30, max_tokens=400)

            plan_hint = await asyncio.to_thread(_llm_plan)
        except Exception as e:  # noqa: BLE001
            logger.warning("supervisor plan failed: %s", e)
    updates["plan_hint"] = plan_hint or ""

    if plan_hint:
        # 调度智能体的执行计划流式展示（plan 事件）
        for i, c in enumerate(_split_lines(plan_hint)):
            events.append({"type": "plan",
                           "message": ("调度智能体规划：" if i == 0 else "") + c})
    else:
        events.append({"type": "thinking", "stage": "plan",
                       "message": "调度智能体已完成规划，交由子智能体执行"})
    updates["events"] = events
    return updates


def route_analyze(state: AgentState) -> str:
    """有本体直接回答 → 直接验收；否则 → 子智能体执行。"""
    return "verify" if (state.get("direct_reply") or "").strip() else "worker"


# ---------------------------------------------------------------------------
# 子智能体：执行（ReAct 循环：LLM 决策 → 技能执行 → 观察）
# ---------------------------------------------------------------------------
def _build_worker_system(agent, state: AgentState) -> str:
    parts = [agent.system_prompt]
    reason = state.get("reason") or {}
    if reason:
        evidence = reason.get("evidence") or ""
        if evidence:
            parts.append("\n【领域语义上下文（本体推理，优先据此理解与作答）】\n" + evidence[:3000])
    if state.get("plan_hint"):
        parts.append("\n【调度智能体执行计划（需落实）】\n" + state["plan_hint"])
    if state.get("verify_comment"):
        parts.append("\n【调度智能体验收意见（据此完善回复）】\n" + state["verify_comment"])
    parts.append(
        "\n回答要求：优先结合语义上下文与技能返回的真实数据作答，不编造数据；"
        "需要数据时先调用技能；最终回复须完整满足用户问题。"
    )
    return "\n".join(parts)


async def worker_node(state: AgentState, agent, skill_names: List[str]) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    registry = get_registry()
    enabled_skills = [s for s in (skill_names or []) if (registry.get(s) is not None and registry.get(s).enabled)]
    # LLM tool calling 需用 OpenAI function calling 格式（MCP inputSchema 格式会被拒绝）
    tools = [registry.get(n).to_openai_tool() for n in enabled_skills]

    msgs = [m for m in (state.get("messages") or []) if m.get("role") != "system"]
    msgs.insert(0, {"role": "system", "content": _build_worker_system(agent, state)})
    tool_count = state.get("tool_count") or 0
    first_round = tool_count == 0 and not (state.get("reply") or "").strip()

    events.append({"type": "thinking", "stage": "execute",
                   "message": f"子智能体「{agent.name}」开始执行" + ("（首次执行）" if first_round else "（根据验收意见继续完善）")})

    # 无可用技能时，让 LLM 直接作答（不走 tool calling）
    if not tools:
        resp = await asyncio.to_thread(chat_completion, msgs, timeout=40, max_tokens=1536)
        if resp is None:
            events.append({"type": "thinking", "stage": "execute",
                           "message": "模型未连通，返回兜底提示"})
            events.append({"type": "verify", "pass": True, "message": "模型未连通，跳过验收"})
            return {"reply": MODEL_MISS_MSG, "verified": True,
                    "rounds": state.get("rounds", 0),
                    "tool_count": tool_count, "events": events}
        return {"reply": resp.strip(), "verified": False,
                "rounds": state.get("rounds", 0), "tool_count": tool_count,
                "messages": msgs, "events": events}

    while tool_count < MAX_TOOL_ROUNDS:
        resp = await asyncio.to_thread(chat_completion_tools, msgs, tools)
        if resp is None:
            # LLM 不可用或未配置
            events.append({"type": "thinking", "stage": "execute",
                           "message": "模型未连通，返回兜底提示"})
            events.append({"type": "verify", "pass": True, "message": "模型未连通，跳过验收"})
            return {"reply": MODEL_MISS_MSG, "verified": True,
                    "rounds": state.get("rounds", 0),
                    "tool_count": tool_count, "events": events}

        calls = resp.get("tool_calls") or []
        if not calls:
            content = (resp.get("content") or "").strip()
            if not content:
                content = "（模型未给出回复，请稍后重试或换一种问法）"
            return {"reply": content, "verified": False,
                    "rounds": state.get("rounds", 0), "tool_count": tool_count,
                    "messages": msgs, "events": events}

        # 执行工具调用
        assistant_msg = {
            "role": "assistant",
            "content": resp.get("content") or None,
            "tool_calls": [
                {"id": c["id"], "type": "function",
                 "function": {"name": c["name"], "arguments": c["arguments"]}}
                for c in calls
            ],
        }
        msgs.append(assistant_msg)
        # 子智能体的决策理由 → 流式展示思考过程
        why = (resp.get("content") or "").strip()
        if why:
            for i, c in enumerate(_split_lines(why)):
                events.append({"type": "reason",
                               "message": ("子智能体思考：" if i == 0 else "") + c})
        for call in calls:
            name = call.get("name") or ""
            try:
                args = json.loads(call.get("arguments") or "{}")
                if not isinstance(args, dict):
                    args = {}
            except (TypeError, ValueError):
                args = {}
            events.append({"type": "status", "message": f"调用技能：{name}"})
            tool_text = await registry.execute(name, args)
            msgs.append({"role": "tool", "tool_call_id": call.get("id") or "",
                         "content": tool_text[:2000]})
            tool_count += 1
        if tool_count >= MAX_TOOL_ROUNDS:
            # 达到工具轮次上限：让 LLM 基于已有信息收尾
            tail = await asyncio.to_thread(chat_completion_tools, msgs, tools) if tools else None
            if tail and not (tail.get("tool_calls") or []):
                return {"reply": (tail.get("content") or "").strip() or "（已达到工具调用上限，基于现有数据作答如下）",
                        "verified": False, "rounds": state.get("rounds", 0),
                        "tool_count": tool_count, "messages": msgs, "events": events}
            return {"reply": "（已达到工具调用上限，请基于以上数据作答）",
                    "verified": False, "rounds": state.get("rounds", 0),
                    "tool_count": tool_count, "messages": msgs, "events": events}
    return {"reply": "（已达到工具调用上限）", "verified": False,
            "rounds": state.get("rounds", 0), "tool_count": tool_count,
            "messages": msgs, "events": events}


def route_worker(state: AgentState) -> str:
    return END if state.get("verified") else "verify"


# ---------------------------------------------------------------------------
# 调度智能体：验收（校验回复是否满足用户需求）
# ---------------------------------------------------------------------------
async def verify_node(state: AgentState) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    reply = state.get("reply") or ""
    # 本体直接回答（跳过 worker）时，回复取自 direct_reply
    if not reply.strip() and (state.get("direct_reply") or "").strip():
        reply = state["direct_reply"]
    question = state.get("completed_question") or state.get("question") or ""
    rounds = state.get("rounds") or 0

    # 空回复直接视为不通过
    if not reply.strip():
        events.append({"type": "verify", "pass": False, "message": "回复为空，子智能体需重新作答"})
        return {"verified": False, "verify_comment": "回复为空，请重新作答。",
                "rounds": rounds + 1, "events": events}

    verdict = {"pass": True, "comment": ""}
    try:
        def _llm_verify() -> Optional[str]:
            msgs = [
                {"role": "system", "content": _SUPERVISOR_VERIFY_PROMPT},
                {"role": "user", "content": f"【用户问题】{question}\n\n【子智能体回复】\n{reply[:3000]}\n\n请验收："},
            ]
            return chat_completion(msgs, timeout=30, max_tokens=300)

        raw = await asyncio.to_thread(_llm_verify)
        if raw:
            parsed = _extract_json(raw)
            if isinstance(parsed, dict) and "pass" in parsed:
                verdict["pass"] = bool(parsed.get("pass"))
                verdict["comment"] = str(parsed.get("comment") or "")[:400]
    except Exception as e:  # noqa: BLE001
        logger.warning("supervisor verify failed: %s", e)

    if verdict["pass"] or rounds >= MAX_VERIFY_ROUNDS:
        if verdict["pass"]:
            events.append({"type": "verify", "pass": True, "message": "调度智能体验收通过，回复满足用户需求"})
        else:
            events.append({"type": "verify", "pass": True,
                           "message": f"已达最大验收轮次（{MAX_VERIFY_ROUNDS}），采纳当前回复"})
        return {"verified": True, "reply": reply, "events": events}

    comment = verdict["comment"] or "回复未完全满足用户需求，请补充关键信息后重新作答。"
    events.append({"type": "verify", "pass": False, "message": "验收未通过：" + comment[:120]})
    return {"verified": False, "verify_comment": comment,
            "rounds": rounds + 1, "events": events}


def route_verify(state: AgentState) -> str:
    return END if state.get("verified") else "worker"


def _extract_json(text: str) -> Optional[dict]:
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        pass
    s, e = text.find("{"), text.rfind("}")
    if 0 <= s < e:
        try:
            return json.loads(text[s:e + 1])
        except (TypeError, ValueError):
            return None
    return None


# ---------------------------------------------------------------------------
# 图构建与执行
# ---------------------------------------------------------------------------
def build_graph(agent, skill_names: List[str]) -> "StateGraph":
    g = StateGraph(AgentState)

    async def _analyze(state: AgentState) -> Dict[str, Any]:
        return await analyze_node(state)

    async def _worker(state: AgentState) -> Dict[str, Any]:
        return await worker_node(state, agent, skill_names)

    async def _verify(state: AgentState) -> Dict[str, Any]:
        return await verify_node(state)

    g.add_node("analyze", _analyze)
    g.add_node("worker", _worker)
    g.add_node("verify", _verify)
    g.add_edge(START, "analyze")
    g.add_conditional_edges("analyze", route_analyze, {"worker": "worker", "verify": "verify"})
    # worker：已验证（模型不可用兜底）→ 直接结束；否则 → 验收
    g.add_conditional_edges("worker", route_worker, {"verify": "verify", END: END})
    # verify：验收通过 → 结束；不通过 → 回 worker 按验收意见完善
    g.add_conditional_edges("verify", route_verify, {"worker": "worker", END: END})
    return g.compile()


async def agent_chat_events(agent, skill_names: List[str], question: str,
                            history: Optional[List[Dict[str, Any]]] = None,
                            max_steps: int = 30):
    """流式运行 LangGraph 图，逐条产出事件（thinking/reason/status/verify/delta）。"""
    history = [dict(m) for m in (history or [])]
    messages: List[Dict[str, Any]] = []
    for m in history:
        if m.get("role") in ("user", "assistant"):
            messages.append({"role": m["role"], "content": m.get("content") or ""})
    messages.append({"role": "user", "content": question})

    initial: AgentState = {
        "question": question,
        "completed_question": question,
        "reason": {},
        "plan_hint": "",
        "direct_reply": "",
        "messages": messages,
        "skill_names": list(skill_names or []),
        "tool_count": 0,
        "rounds": 0,
        "reply": "",
        "verified": False,
        "verify_comment": "",
        "events": [],
    }

    graph = build_graph(agent, skill_names)
    final_reply = ""
    try:
        async for chunk in graph.astream(initial, stream_mode="updates"):
            for _node, update in chunk.items():
                for ev in update.get("events") or []:
                    yield ev
                if update.get("reply"):
                    # 验收通过时 reply 为最终稿；未通过时为新一轮产出
                    if update.get("verified"):
                        final_reply = update["reply"] or final_reply
                    else:
                        final_reply = update["reply"] or final_reply
    except Exception as e:  # noqa: BLE001
        logger.exception("langgraph run failed")
        yield {"type": "delta", "delta": f"（智能体运行异常：{e}）"}
        return

    # 输出最终回复增量（分块，保留空格）
    if not final_reply.strip():
        final_reply = MODEL_MISS_MSG
    yield {"type": "verify", "pass": True, "message": "回复完成"}
    for i in range(0, len(final_reply), 64):
        yield {"type": "delta", "delta": final_reply[i:i + 64]}


async def agent_chat(agent, skill_names: List[str], question: str,
                     history: Optional[List[Dict[str, Any]]] = None) -> str:
    """非流式：运行图并聚合最终回复文本。"""
    reply = ""
    async for ev in agent_chat_events(agent, skill_names, question, history):
        if ev.get("type") == "delta":
            reply += ev.get("delta") or ""
    return reply
