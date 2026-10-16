"""设备/模型命名规则：名字必须是「三端都能存在」的名字。

设备只有一份定义，这份定义要同时落到两个地方：
- 云端（K3s）：Device / DeviceModel 的 metadata.name（RFC 1123 单标签，不允许下划线/大写）；
- 盒子（config.json + MQTT 主题）：data/{box}/{device}/{instance}/{property}。
云端的要求最严，所以定义必须以云端规则为准。现场故障正是踩在这里：本地有 flow_meter
（下划线），云端永远建不出这个对象——「本地有、云端怎么点都缺它」，下发多少次都不会出现，
只在 kubectl 报一句 RFC 1123 报错。

规则放在领域层，是为了让「保存路径 / 下发路径 / 报错文案」共用同一份判断，
而不是各写一遍正则（历史上校验只挂在创建设备这一个 API 里，其它写入路径（云端回写、
快照回滚、脚本导入）绕过它把非法名带进了定义）。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

# K8s 对象名（RFC 1123 subdomain）：小写字母/数字/中划线/点，且以字母数字开头结尾
K8S_NAME_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$")
MAX_NAME_LEN = 253
_INVALID_RUN_RE = re.compile(r"[^a-z0-9.-]+")
_DASH_RUN_RE = re.compile(r"-{2,}")


def is_valid_object_name(value: Any) -> bool:
    """是否为合法的 K8s 对象名（= 云端能建、盒子 MQTT 主题也能用的名字）。"""
    v = str(value or "").strip()
    return bool(v) and len(v) <= MAX_NAME_LEN and bool(K8S_NAME_RE.fullmatch(v))


def suggest_object_name(value: Any) -> str:
    """把用户输入规整成合法对象名（大写转小写，下划线/空格/中文等一律转中划线）。

    仅用于「输入无法在三端存在」时给出建议值：告诉用户改成什么可以，而不是只报非法。
    """
    v = str(value or "").strip().lower()
    v = _INVALID_RUN_RE.sub("-", v)
    v = _DASH_RUN_RE.sub("-", v)
    return v[:MAX_NAME_LEN].strip("-.")


def name_error(value: Any, label: str) -> str:
    """校验并返回可读错误（空串=合法）：带原因 + 可直接采用的建议名。"""
    v = str(value or "").strip()
    if not v:
        return f"{label}不能为空"
    if len(v) > MAX_NAME_LEN:
        return f"{label}过长（{len(v)} 字符 > {MAX_NAME_LEN}）"
    if not K8S_NAME_RE.fullmatch(v):
        return (f"{label}不合法：{v}。设备名/模型名就是 K8s 对象名，只能用"
                f"小写字母、数字、中划线（-）和点（.），且必须以字母或数字开头结尾"
                f"（不能含大写字母、下划线、空格）；建议改为 {suggest_object_name(v)}")
    return ""


def _duplicated(names: List[str]) -> str:
    seen, dup = set(), []
    for n in names:
        if not n:
            continue
        if n in seen:
            dup.append(n)
        seen.add(n)
    return "、".join(dup)


def normalize_definition_names(data: Dict[str, Any]) -> Dict[str, Any]:
    """就地规范化定义里的模型名/设备名，返回 {"renamed": {...}, "error": ""}。

    收口在这一层的理由：写入唯一定义的地方有多个（创建/更新设备、云端回写、删除回滚快照），
    校验写在某一个入口时其它入口就绕过了。这里在仓储写入前统一规范，任何路径都跑不掉。

    重命名必须整体做：模型名变了要同步改所有设备的 model 引用，否则会留下悬空引用
    （云端 Device.deviceModelRef 指向一个不存在的 DeviceModel）。规范化后若撞名，
    返回错误交回用户决定（不替用户猜哪台该改）。
    """
    models: List[Dict[str, Any]] = list(data.get("models") or [])
    devices: List[Dict[str, Any]] = list(data.get("devices") or [])
    renamed: Dict[str, Dict[str, str]] = {"models": {}, "devices": {}}

    for m in models:
        old = str(m.get("name") or "").strip()
        if not old or is_valid_object_name(old):
            continue
        m["name"] = suggest_object_name(old)
        renamed["models"][old] = m["name"]
    dup = _duplicated([str(m.get("name") or "") for m in models])
    if dup:
        return {"renamed": renamed,
                "error": "规范化后模型名重复：%s（请先区分开这两个模型）" % dup}

    # 设备的模型引用跟随模型改名（否则悬空引用）
    for d in devices:
        ref = str(d.get("model") or "").strip()
        if ref in renamed["models"]:
            d["model"] = renamed["models"][ref]

    for d in devices:
        old = str(d.get("name") or "").strip()
        if not old or is_valid_object_name(old):
            continue
        d["name"] = suggest_object_name(old)
        renamed["devices"][old] = d["name"]
    dup = _duplicated([str(d.get("name") or "") for d in devices])
    if dup:
        return {"renamed": renamed,
                "error": "规范化后设备名重复：%s（请先区分开这两台设备）" % dup}

    return {"renamed": renamed, "error": ""}


def renamed_summary(renamed: Dict[str, Dict[str, str]]) -> str:
    """把改名结果拼成一句可读文案（空串=没有改名）。"""
    parts = []
    for kind, label in (("models", "模型"), ("devices", "设备")):
        for old, new in (renamed.get(kind) or {}).items():
            parts.append("%s %s→%s" % (label, old, new))
    return "；".join(parts)


def has_renames(renamed: Dict[str, Dict[str, str]]) -> bool:
    """是否真的有改名（`{}` 与 `{"models": {}, "devices": {}}` 都算没有）。

    空结构也是「真」的坑：调用方若用 `if renamed:` 判断，会在没有改名时走进改名善后逻辑
    （删云端旧对象这类有副作用的动作），所以统一用本函数判断。
    """
    return any((renamed.get(k) or {}) for k in ("models", "devices"))


def invalid_definition_names(data: Dict[str, Any]) -> List[Dict[str, str]]:
    """列出定义里「云端用不了」的名字（三端一致性体检用：这是云端缺设备的最硬原因）。"""
    out: List[Dict[str, str]] = []
    for m in (data.get("models") or []):
        name = str(m.get("name") or "")
        if name and not is_valid_object_name(name):
            out.append({"kind": "model", "name": name, "suggest": suggest_object_name(name)})
    for d in (data.get("devices") or []):
        name = str(d.get("name") or "")
        if name and not is_valid_object_name(name):
            out.append({"kind": "device", "name": name, "suggest": suggest_object_name(name)})
    return out
