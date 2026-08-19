"""基于大模型的策略拆解（OpenAI 兼容接口）。

把自然语言减碳策略拆解为结构化操作(ParsedOp)列表，供 apply_ops 直接执行。
默认接入 DeepSeek（https://api.deepseek.com/v1，OpenAI 兼容 chat/completions）。

配置（环境变量）：
  - LLM_API_KEY  : API Key（必填；为空则自动回退到启发式解析）
  - LLM_BASE_URL : 兼容 OpenAI 的 base url，默认 https://api.deepseek.com/v1
  - LLM_MODEL    : 模型名，默认 deepseek-chat

健壮性：任何异常（无 key / 网络超时 / 返回非 JSON / 解析失败）都返回 None，
调用方(api.parse)会回退到确定性的启发式解析，保证离线可用。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import List, Optional

from .models import ParseResult, ParsedOp
from .param_schema import PARAM_SCHEMA, TECHS_INFO, UNIT_TYPES_INFO

def _load_dotenv():
    """本地直接运行（run.sh / uvicorn）时，docker-compose 注入的 LLM_* 不会进入进程环境；
    这里从 backend/config/.env 与项目根 .env 读取并补进 os.environ，保证本地启动也能拿到配置。"""
    here = os.path.dirname(__file__)
    for cand in (
        os.path.join(here, "..", "config", ".env"),
        os.path.join(here, "..", ".env"),
        os.path.join(here, "..", "..", ".env"),
    ):
        if os.path.isfile(cand):
            try:
                with open(cand, "r", encoding="utf-8") as f:
                    for raw in f:
                        line = raw.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        if k and k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass
            break


_load_dotenv()


def _llm_cfg():
    """惰性读取 LLM 配置（支持进程环境变量与 .env 兜底）。"""
    return (
        os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/"),
        os.getenv("LLM_API_KEY", ""),
        os.getenv("LLM_MODEL", "deepseek-chat"),
    )

_VALID_ACTIONS = {"replace_type", "add_unit", "remove_unit", "apply_tech", "set_param"}
_VALID_TYPES = {u["type"] for u in UNIT_TYPES_INFO}
_VALID_TECHS = {t["tech"] for t in TECHS_INFO}


def _schema_block() -> str:
    """把参数分级表压缩成提示词文本。"""
    lines = []
    for utype, params in PARAM_SCHEMA.items():
        label = next((u["label"] for u in UNIT_TYPES_INFO if u["type"] == utype), utype)
        ps = []
        for p in params:
            ps.append(f"{p['key']}({p['label']},{p['unit']},{p['kind']},参考{p['min']}~{p['max']})")
        lines.append(f"  - {utype} [{label}]: " + "; ".join(ps))
    return "\n".join(lines)


def _build_messages(text: str, model_units: Optional[List[dict]]) -> List[dict]:
    unit_catalog = "\n".join(f"  - {u['type']} = {u['label']}（{u['cat']}）" for u in UNIT_TYPES_INFO)
    tech_catalog = "\n".join(f"  - {t['tech']} = {t['label']}" for t in TECHS_INFO)
    current = ""
    if model_units:
        current = "当前流程中的工序（name -> type）：\n" + "\n".join(
            f"  - {u.get('name','?')} -> {u.get('type','?')}" for u in model_units
        )
    else:
        current = "（未提供当前流程，按类型泛指处理）"

    system = f"""你是一个钢铁流程节能减碳策略解析器。请把用户的中文/英文节能减碳策略，拆解为严格 JSON 的操作列表。

## 可操作的工序类型（type id = 中文标签）
{unit_catalog}

## 减排技术（tech id = 中文标签）
{tech_catalog}

## 各工序可调参数（param key = 中文标签,单位,分级,参考范围）
说明：kind=config 是「给定约束/因变量」，通常如实填入、不作为优化杠杆；
     kind=optim 是「节能减排决策变量/自变量」，是建议优先调整的方向。
{_schema_block()}

## 操作(action) 规范（必须严格使用以下枚举）
1. replace_type : 把某工序替换为另一类型。字段 target(工序名或类型中文), to_type(类型id)
2. add_unit     : 新增工序。字段 to_type(类型id), count(整数,默认1)
3. remove_unit  : 删除工序。字段 target(工序名或类型中文)
4. apply_tech   : 应用节能减碳技术。字段 tech(技术id), target(可选,工序名或类型中文;缺省作用于全部工序)
5. set_param    : 调整参数。字段 target(可选,工序名或类型中文,缺省作用于该类型全部),
                  param(参数key), value(数值), mode("absolute"绝对设定 | "relative"相对调整)。
                  relative 时 value 为带符号百分比（负=降低，正=提高），如 -20 表示降低20%。

## 输出格式（只输出 JSON，不要解释）
{{
  "understood": ["要点1", "要点2"],
  "ops": [
    {{"action":"set_param","target":"高炉","param":"coke_rate","value":360,"mode":"absolute","note":"高炉焦比降至360"}},
    {{"action":"apply_tech","tech":"ccs","target":"高炉","note":"高炉加装碳捕集"}}
  ],
  "warnings": ["无法识别的内容说明"]
}}

## 约束
- param 必须是目标工序类型下存在的 key；value 需在参考范围内（越界也允许，但给出 warning）。
- 优先用 optim 类参数表达"节能减排"意图；config 类仅在用户明确要求时才改。
- target 尽量用 current 里真实的工序名（如"高炉"），以便精确定位。
"""

    user = f"{current}\n\n用户的策略文本：\n\"\"\"\n{text}\n\"\"\"\n请输出上述 JSON。"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _call_llm(messages: List[dict], timeout: float = 25.0, response_format=None,
              max_tokens: int = 1500) -> Optional[str]:
    base_url, api_key, model = _llm_cfg()
    if not api_key:
        return None
    url = f"{base_url}/chat/completions"
    is_json = response_format is not None
    payload = {
        "model": model,
        "messages": messages,
        # JSON 模式(策略解析)用 0 保证稳定；普通聊天用 0.7 更自然
        "temperature": 0.0 if is_json else 0.7,
        "max_tokens": max_tokens,
    }
    if is_json:
        payload["response_format"] = response_format
    payload = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    })
    # 绕过本机 HTTPS_PROXY（如 127.0.0.1:53483），直达 api.deepseek.com，
    # 否则 urllib 会把外部请求交给本地代理而失败。
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        msg = data["choices"][0]["message"]
        content = (msg.get("content") or "").strip()
        # reasoning 类模型（如 deepseek-v4-pro）先产出 reasoning_content；
        # 仅非 JSON 模式回退，避免污染结构化解析。
        if not content and not is_json:
            content = (msg.get("reasoning_content") or "").strip()
        return content
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError,
            ValueError, TimeoutError, OSError):
        return None


def chat_completion(messages: List[dict], timeout: float = 30.0,
                    max_tokens: int = 1500) -> Optional[str]:
    """通用聊天补全（OpenAI 兼容接口）。无 key / 网络异常返回 None，由调用方兜底。"""
    return _call_llm(messages, timeout=timeout, response_format=None, max_tokens=max_tokens)


def _extract_json(text: str) -> Optional[dict]:
    try:
        return json.loads(text)
    except ValueError:
        pass
    # 退而求其次：截取首个 { 到末个 }
    s, e = text.find("{"), text.rfind("}")
    if s >= 0 and e > s:
        try:
            return json.loads(text[s:e + 1])
        except ValueError:
            return None
    return None


def _resolve_type(target: Optional[str], model_units: Optional[List[dict]]) -> Optional[str]:
    if not target:
        return None
    t = target.strip()
    if t in _VALID_TYPES:
        return t
    # 在模型单元中按名/类型匹配
    if model_units:
        for u in model_units:
            nm = (u.get("name") or "").strip()
            ut = (u.get("type") or "").strip()
            if t == nm or t == ut or t in nm or t in ut:
                return ut
    # 模糊：看是否包含某类型中文标签
    for u in UNIT_TYPES_INFO:
        if u["label"] in t or t in u["label"]:
            return u["type"]
    return None


def llm_parse(text: str, model_units: Optional[List[dict]] = None) -> Optional[ParseResult]:
    """调用大模型拆解策略；失败返回 None（调用方回退启发式）。"""
    raw = _call_llm(_build_messages(text, model_units), response_format={"type": "json_object"})
    if not raw:
        return None
    data = _extract_json(raw)
    if not data or not isinstance(data, dict):
        return None

    ops: List[ParsedOp] = []
    warnings: List[str] = list(data.get("warnings", []))
    for i, o in enumerate(data.get("ops", [])):
        if not isinstance(o, dict):
            continue
        action = o.get("action")
        if action not in _VALID_ACTIONS:
            warnings.append(f"忽略未知操作类型: {action}")
            continue
        op = ParsedOp(action=action, note=str(o.get("note", ""))[:200])
        if action == "replace_type":
            tt = _resolve_type(o.get("to_type"), None) or (o.get("to_type") if o.get("to_type") in _VALID_TYPES else None)
            if not tt:
                warnings.append(f"操作{i}: 无法识别目标类型 {o.get('to_type')}")
                continue
            op.to_type = tt
            op.target = o.get("target")
        elif action == "add_unit":
            tt = o.get("to_type")
            if tt not in _VALID_TYPES:
                warnings.append(f"操作{i}: 无法识别新增类型 {tt}")
                continue
            op.to_type = tt
            op.count = int(o.get("count", 1) or 1)
        elif action == "remove_unit":
            op.target = o.get("target")
        elif action == "apply_tech":
            tech = o.get("tech")
            if tech not in _VALID_TECHS:
                warnings.append(f"操作{i}: 无法识别技术 {tech}")
                continue
            op.tech = tech
            op.target = o.get("target")
        elif action == "set_param":
            param = o.get("param")
            target_type = _resolve_type(o.get("target"), model_units)
            # 校验 param 是否属于目标工序类型
            allowed = set()
            if target_type and target_type in PARAM_SCHEMA:
                allowed = {p["key"] for p in PARAM_SCHEMA[target_type]}
            elif model_units and not target_type:
                # 缺省作用于全部：收集所有类型允许的 key
                for u in model_units:
                    allowed |= {p["key"] for p in PARAM_SCHEMA.get(u.get("type"), [])}
            if param not in allowed:
                warnings.append(f"操作{i}: 参数 {param} 不属于目标工序类型，已忽略")
                continue
            try:
                value = float(o.get("value"))
            except (TypeError, ValueError):
                warnings.append(f"操作{i}: 参数 {param} 的数值无效")
                continue
            op.param = param
            op.target = o.get("target")
            op.value = value
            op.mode = o.get("mode", "absolute")
            if op.mode not in ("absolute", "relative"):
                op.mode = "absolute"
        ops.append(op)

    understood = data.get("understood", [])
    if not isinstance(understood, list):
        understood = []
    if not ops:
        warnings.append("大模型未产出可执行操作，已回退启发式解析")
        return None
    return ParseResult(raw_text=text, understood=understood, ops=ops,
                       confidence=min(1.0, 0.5 + 0.1 * len(ops)), warnings=warnings,
                       engine="llm")
