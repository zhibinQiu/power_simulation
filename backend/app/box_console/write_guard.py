"""设备模型「可写属性」的数值范围与写操作硬性限制。

模型（DeviceModel）中具备可写能力的属性（accessMode = rw / ReadWrite）可在平台侧
配置**数值范围**（min / max）。引用该模型的设备在执行写操作（下发写设定命令、
回写 twins）时，平台按该范围做硬性校验：越界（或写入只读属性）一律拒绝下发，
避免误把超限设定值写进现场设备。

范围来源（优先级从高到低，取第一个配置了范围的来源）——**一律来自设备配置，
命令本身不携带安全上下限**（不在下发命令时临时填写，避免同一设备每次限幅口径不一致）：
1. 设备「可写点位」writes[] 上的 min / max（工程值域，盒子 mapper 同步校验）；
2. 设备 properties[]（由模型同步而来）中同名可写属性的 min / max；
3. 设备引用模型 models[] 中同名可写属性的 min / max。

只读限制：属性在设备/模型中登记为只读（accessMode = r / ReadOnly）且设备未单独
配置该点位的可写点位（writes[]）时，拒绝写入——「可写能力」由模型决定。

全局生效（任何调用方、任何触发源都绕不过）：
- **MQTT 下发出口** `mqtt_source.publish` → `guard_publish()`：命令主题
  （cmd/{box}/cmd、cmd/{box}/config）在此统一校验，前端命令面板、原始消息、
  自动化下发、脚本/工具/AI 调用全部经过这里；越界或缺少安全范围一律拒绝且不发出
  （安全范围只取设备配置，不接受命令载荷自带的 min/max）。
- **twins 回写出口** `cloud_agent.ingest` → `guard_ingest()`：越界数值一律拒绝。
- **统一写入入口** `box_console.write_device_value()`：平台内部/AI 训练等需要写设备
  时应调用它（自带硬校验），不要自行拼装主题发布。
- **边缘侧双保险** 盒子 mapper 收到写入命令时按可写点位 min/max 再校验一次
  （platform/box-deploy/mapper/box_mapper.py）。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from ._shared import _load_devices

logger = logging.getLogger(__name__)

# 可写 / 只读访问模式（容忍大小写与多种写法；未标注 accessMode 的历史属性不做只读拒绝）
_WRITABLE = {"rw", "w", "readwrite", "read_write", "write", "writeonly"}
_READONLY = {"r", "ro", "readonly", "read_only", "read"}

# 设备命令主题：cmd/{box}/cmd（盒子 mapper 的读/写/LoRa 下行命令通道）
_CMD_TOPIC_RE = re.compile(r"^cmd/([^/]+)/cmd$")
# 设备配置整包下发主题：cmd/{box}/config（写点位范围随配置下发到盒子）
_CONFIG_TOPIC_RE = re.compile(r"^cmd/([^/]+)/config$")
# 盒子命令主题（cmd/config/deploy）：出口硬约束覆盖全部命令动作，防旁路
_CMD_ANY_TOPIC_RE = re.compile(r"^cmd/([^/]+)/(cmd|config|deploy)$")


def _num(v: Any) -> Optional[float]:
    """宽松转数值：非法/空返回 None（布尔不参与数值比较）。"""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        try:
            return float(v)
        except (TypeError, ValueError, OverflowError):
            return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _mode_of(prop: Any) -> str:
    return str((prop or {}).get("accessMode") or "").strip().lower()


def is_writable(prop: Any) -> bool:
    """属性是否具备可写能力（模型/设备属性 accessMode）。"""
    return _mode_of(prop) in _WRITABLE


def is_readonly(prop: Any) -> bool:
    """属性是否显式登记为只读（未标注 accessMode 的历史数据不算只读）。"""
    return _mode_of(prop) in _READONLY


def _range_of(obj: Any) -> Tuple[Optional[float], Optional[float]]:
    return _num((obj or {}).get("min")), _num((obj or {}).get("max"))


def _raw_to_engineering(lo: Optional[float], hi: Optional[float],
                        scale: Any) -> Tuple[Optional[float], Optional[float]]:
    """寄存器原始值范围 -> 工程值范围（scale：工程值 × scale = 原始值）。"""
    sc = _num(scale)
    if not sc or sc == 0:
        return lo, hi
    return (None if lo is None else lo / sc, None if hi is None else hi / sc)


# ------------------------- 配置读取 -------------------------

def find_device(name: str, box: str = "") -> Optional[Dict[str, Any]]:
    """按设备名查找本地设备记录；box 非空时优先取挂载在该盒子上的同名设备。"""
    name = str(name or "").strip()
    if not name:
        return None
    devs = [d for d in (_load_devices().get("devices") or []) if isinstance(d, dict)]
    hit = [d for d in devs if str(d.get("name") or "").strip() == name]
    if len(hit) > 1 and box:
        b = str(box).strip()
        same_box = [d for d in hit if str(d.get("node") or "").strip() == b]
        if same_box:
            return same_box[0]
    return hit[0] if hit else None


def find_model(name: str) -> Optional[Dict[str, Any]]:
    name = str(name or "").strip()
    if not name:
        return None
    for m in (_load_devices().get("models") or []):
        if isinstance(m, dict) and str(m.get("name") or "").strip() == name:
            return m
    return None


def _same(a: Any, b: Any) -> bool:
    return str(a or "").strip() == str(b or "").strip()


def _candidates(dev: Dict[str, Any], prop: str) -> List[Tuple[Dict[str, Any], str]]:
    """该属性上可能配置范围的候选来源（按优先级）。"""
    out: List[Tuple[Dict[str, Any], str]] = []
    for w in (dev.get("writes") or []):
        if isinstance(w, dict) and _same(w.get("property"), prop):
            out.append((w, "设备可写点位"))
    for p in (dev.get("properties") or []):
        if isinstance(p, dict) and _same(p.get("name"), prop):
            out.append((p, "设备属性（来自模型）"))
    model = find_model(str(dev.get("model") or ""))
    if model:
        for p in (model.get("properties") or []):
            if isinstance(p, dict) and _same(p.get("name"), prop):
                out.append((p, "设备模型属性"))
    return out


def resolve_range(device_name: str, prop: str, box: str = "") -> Optional[Dict[str, Any]]:
    """解析某设备某属性的可写数值范围；无限制（未配置/设备不存在）返回 None。"""
    prop = str(prop or "").strip()
    if not prop:
        return None
    dev = find_device(device_name, box)
    if dev is None:
        return None
    for obj, source in _candidates(dev, prop):
        lo, hi = _range_of(obj)
        if source == "设备可写点位":
            # 可写点位的 min/max 是「寄存器原始值」（盒子 mapper 按原始值校验），
            # 而写入值是工程值：按 scale（工程值 × scale = 原始值）换算回工程量纲，
            # 保证平台侧与下发值同一量纲比较，避免误判。
            lo, hi = _raw_to_engineering(lo, hi, obj.get("scale"))
        if lo is None and hi is None:
            continue
        return {"min": lo, "max": hi, "source": source,
                "device": str(dev.get("name") or ""), "property": prop}
    return None


def check_writable(device_name: str, prop: str, box: str = "") -> Dict[str, Any]:
    """属性是否允许写入（模型登记为只读且未单独配置可写点位 → 拒绝）。"""
    prop = str(prop or "").strip()
    dev = find_device(device_name, box)
    if dev is None or not prop:
        return {"ok": True, "known": False}
    cands = _candidates(dev, prop)
    if not cands:
        return {"ok": True, "known": False}
    has_write_point = any(src == "设备可写点位" for _, src in cands)
    if has_write_point:
        return {"ok": True, "known": True}
    # 设备/模型属性中登记为只读 → 不允许写入
    for obj, src in cands:
        if is_readonly(obj):
            return {"ok": False, "known": True,
                    "error": f"属性「{prop}」在{src}中为只读（ReadOnly），不允许写入"}
    return {"ok": True, "known": True}


def validate_write(device_name: str, prop: str, value: Any,
                   box: str = "", enforce_readonly: bool = True) -> Dict[str, Any]:
    """写操作硬性校验：只读属性 + 数值范围。

    返回 {ok, error?}；ok=False 时调用方必须拒绝下发（不做任何降级放行）。

    enforce_readonly：True（下发写命令，默认）= 只读属性一律拒绝；False（数据回写/
    上报语义）= 只做数值范围限幅，不因属性只读而拒绝（上报测量值是合法行为）。
    """
    prop = str(prop or "").strip()
    if not prop:
        return {"ok": True}
    v = _num(value)
    if v is None:
        # 非数值（布尔线圈 / 字符串枚举）不做范围校验，交由盒子侧处理
        return {"ok": True}
    if enforce_readonly:
        w = check_writable(device_name, prop, box)
        if not w.get("ok"):
            return {"ok": False, "error": w.get("error") or "属性不可写"}
    rng = resolve_range(device_name, prop, box)
    if rng is None:
        return {"ok": True}
    lo, hi = rng.get("min"), rng.get("max")
    if lo is not None and v < lo:
        return {"ok": False, "range": rng,
                "error": f"写入值 {_fmt(v)} 低于下限 {_fmt(lo)}（{rng.get('source')}「{prop}」范围 {_fmt(lo)}~{_fmt(hi)}）"}
    if hi is not None and v > hi:
        return {"ok": False, "range": rng,
                "error": f"写入值 {_fmt(v)} 高于上限 {_fmt(hi)}（{rng.get('source')}「{prop}」范围 {_fmt(lo)}~{_fmt(hi)}）"}
    return {"ok": True, "range": rng}


def _fmt(v: Any) -> str:
    if v is None:
        return "不限"
    f = float(v)
    return str(int(f)) if f == int(f) else str(round(f, 6))


def addr_range(device_name: str, addr: Any, kind: str = "holding",
               box: str = "") -> Optional[Dict[str, Any]]:
    """按寄存器/线圈地址解析写入范围（**寄存器原始值**口径，供裸写 addr 模式使用）。

    来源：设备可写点位（min/max 即原始值）> 设备属性/模型属性（工程值按 scale 折回原始值）。
    """
    a = _num(addr)
    dev = find_device(device_name, box)
    if dev is None or a is None:
        return None
    want_coil = str(kind or "holding").strip().lower() == "coil"
    for w in (dev.get("writes") or []):
        if not isinstance(w, dict):
            continue
        if (str(w.get("kind") or "holding").lower() == "coil") != want_coil:
            continue
        wa = _num(w.get("coilAddr") if want_coil else w.get("registerAddr"))
        if wa is None or int(wa) != int(a):
            continue
        lo, hi = _range_of(w)
        if lo is None and hi is None:
            continue
        return {"min": lo, "max": hi, "source": "设备可写点位",
                "device": str(dev.get("name") or ""), "addr": int(a)}
    for p in (dev.get("properties") or []):
        if not isinstance(p, dict) or not is_writable(p):
            continue
        if ("coil" in str(p.get("registerType") or "").lower()) != want_coil:
            continue
        pa = _num(p.get("register"))
        if pa is None or int(pa) != int(a):
            continue
        lo, hi = _range_of(p)
        if lo is None and hi is None:
            continue
        if not want_coil:
            sc = _num(p.get("scale")) or 1.0   # points.scale：原始值 × scale = 工程值
            lo = None if lo is None else lo / sc
            hi = None if hi is None else hi / sc
        return {"min": lo, "max": hi, "source": "设备属性（来自模型）",
                "device": str(dev.get("name") or ""), "addr": int(a)}
    return None


def config_slave(dev: Any) -> Optional[int]:
    """设备配置中的从站号（Modbus：comm.slaveID / modbus.slaveId；LoRa 透传：lora.slaveId）。

    从站号与数值范围一样属于设备配置，不在下发命令时指定：命令里带 slaveId 会被
    盒子拿来覆盖设备配置，等于把值写到同一总线上另一台设备（而范围校验是按当前
    设备做的），因此出口只认配置值。
    """
    if not isinstance(dev, dict):
        return None
    for src in (dev.get("comm") or {}, dev.get("modbus") or {}, dev.get("lora") or {}):
        if not isinstance(src, dict):
            continue
        v = _num(src.get("slaveID") if "slaveID" in src else src.get("slaveId"))
        if v is not None and v > 0:
            return int(v)
    return None


def _as_dict(payload: Any) -> Optional[Dict[str, Any]]:
    """宽松解析 MQTT 载荷为 dict（bytes/JSON 字符串/dict）；无法解析返回 None。"""
    data: Any = payload
    if isinstance(data, (bytes, bytearray)):
        try:
            data = data.decode("utf-8")
        except Exception:  # noqa: BLE001
            return None
    if isinstance(data, str):
        s = data.strip()
        if not (s.startswith("{") and s.endswith("}")):
            return None
        try:
            data = json.loads(s)
        except Exception:  # noqa: BLE001
            return None
    return data if isinstance(data, dict) else None


# ------------------------- 写操作入口校验 -------------------------

def validate_cmd_payload(topic: str, payload: Any) -> Optional[str]:
    """校验盒子写命令载荷（cmd/{box}/cmd）。返回错误说明；None = 放行。

    拦截「设备写设定」这一类会真正落到现场设备的写入（cmd=write）：
    - property 模式：按设备配置（可写点位 / 设备属性 / 模型属性）的范围 + 只读属性硬校验；
    - addr 裸写模式：范围同样只认设备配置（同地址可写点位 / 可写属性），配置中
      没有范围则拒绝（fail-closed，防止误写超限值烧设备）；
    - **载荷自带的 min/max 不再生效**：安全上下限只在设备配置中设置，不在下发
      命令时临时填写，避免同一设备每次下发的限幅口径不一致；
    - **从站号同样只认设备配置**：命令自带 slaveId 与配置不一致时拒绝（否则等于
      把值写到同一总线上另一台设备，而范围校验是按当前设备做的）。
    读命令、LoRa 下行（cmd=down，值非标量）、非 JSON 载荷一律放行（不影响调试）。
    """
    m = _CMD_TOPIC_RE.match(str(topic or "").strip())
    if not m:
        return None
    box = m.group(1)
    data = _as_dict(payload)
    if data is None:
        return None
    if str(data.get("cmd") or "").strip().lower() != "write":
        return None
    device = str(data.get("device") or "").strip()
    v = _num(data.get("value"))
    if not device or v is None:
        return None
    # 从站号属于设备配置：命令不得另行指定（未登记设备不做校验，保持放行）
    dev_obj = find_device(device, box)
    if dev_obj is not None:
        slave = _num(data.get("slaveId") if "slaveId" in data else data.get("slave"))
        cfg_slave = config_slave(dev_obj)
        if slave is not None and cfg_slave is not None and int(slave) != cfg_slave:
            return (f"命令中的从站号 {int(slave)} 与设备配置（{cfg_slave}）不一致："
                    f"从站号属于设备配置，请在设备配置中修改，命令中不允许另行指定")
    prop = str(data.get("property") or "").strip()
    if prop:
        res = validate_write(device, prop, v, box=box)
        if not res.get("ok"):
            return res.get("error") or "写入值超出允许范围"
        return None
    # 裸写模式（addr）：value 为寄存器/线圈原始值
    addr = _num(data.get("addr"))
    if addr is None:
        return None
    kind = str(data.get("kind") or "holding").strip().lower()
    r = addr_range(device, addr, kind, box=box)
    if r is None:
        return (f"裸写{('线圈' if kind == 'coil' else '寄存器')} {int(addr)} 缺少安全范围："
                f"请在设备配置中为该可写点位/属性设置数值范围（min/max）"
                f"（平台拒绝无范围的设备写入，防止超限损伤设备）")
    lo, hi = r.get("min"), r.get("max")
    if lo is not None and v < lo:
        return f"写入值 {_fmt(v)} 低于下限 {_fmt(lo)}"
    if hi is not None and v > hi:
        return f"写入值 {_fmt(v)} 高于上限 {_fmt(hi)}"
    return None


def validate_config_payload(payload: Any) -> Optional[str]:
    """校验下发给盒子的设备配置整包（cmd/{box}/config）中可写点位范围是否合法。

    范围非法的配置会让盒子侧的限幅失效（甚至按 NaN 比较放行），因此在下发出口拒绝。
    """
    data = _as_dict(payload)
    if data is None:
        return None
    for d in (data.get("devices") or []):
        if not isinstance(d, dict):
            continue
        name = str(d.get("name") or "")
        for w in (d.get("writes") or []):
            if not isinstance(w, dict):
                continue
            raw_lo, raw_hi = w.get("min"), w.get("max")
            lo, hi = _num(raw_lo), _num(raw_hi)
            if raw_lo not in (None, "") and lo is None:
                return f"设备 {name} 可写点位 {w.get('property')} 的下限非法：{raw_lo!r}"
            if raw_hi not in (None, "") and hi is None:
                return f"设备 {name} 可写点位 {w.get('property')} 的上限非法：{raw_hi!r}"
            if lo is not None and hi is not None and lo > hi:
                return (f"设备 {name} 可写点位 {w.get('property')} 的范围非法"
                        f"（下限 {_fmt(lo)} 大于上限 {_fmt(hi)}），拒绝下发")
    return None


def guard_publish(topic: str, payload: Any) -> Optional[str]:
    """MQTT 发布出口的统一设备写入硬约束（全局生效）。返回错误说明；None = 放行。

    所有下发到盒子的消息都经 mqtt_source.publish 这一个出口（前端命令面板、原始消息、
    自动化下发、脚本/工具/AI 调用），在此统一拦截，避免任何旁路绕过数值范围限制。

    覆盖 cmd/{box}/{cmd|config|deploy} 三类命令主题：
    - cmd/{box}/cmd 且 cmd=write → 数值范围 + 只读属性硬校验（裸写无范围即拒绝）；
    - cmd/{box}/config 或任何带 devices[] 的载荷 → 可写点位范围自洽校验；
    - deploy 等其它命令若夹带 write 命令 / devices 配置同样校验（防旁路）。
    """
    t = str(topic or "").strip()
    m = _CMD_ANY_TOPIC_RE.match(t)
    if not m:
        return None
    box = m.group(1)
    data = _as_dict(payload)
    err: Optional[str] = None
    if m.group(2) == "config" or (data is not None and isinstance(data.get("devices"), list)):
        err = validate_config_payload(payload)
    if not err and data is not None and str(data.get("cmd") or "").strip().lower() == "write":
        err = validate_cmd_payload("cmd/%s/cmd" % box, payload)
    if err:
        # 审计留痕：被硬约束拒绝的下发（便于排查「为什么写不进去」）
        logger.warning("设备写入被硬约束拒绝：topic=%s payload=%s reason=%s",
                       t, str(payload)[:300], err)
    return err


def guard_ingest(device: str, prop: str, value: Any, box: str = "") -> Optional[str]:
    """回写 twins 出口的统一限幅校验（数据上报语义：不拒只读属性，只拦越界值）。"""
    res = validate_write(device, prop, value, box=box, enforce_readonly=False)
    if res.get("ok"):
        return None
    err = res.get("error") or "写入值超出允许范围"
    logger.warning("twins 回写被硬约束拒绝：device=%s property=%s value=%s reason=%s",
                   device, prop, value, err)
    return err


# ------------------------- 配置规范化 -------------------------

def normalize_properties(props: Any) -> List[Dict[str, Any]]:
    """属性点位规范化：数值范围（min/max）仅对可写属性保留，非法值丢弃。

    避免把「只读属性上误填的范围」或空字符串写进配置，也避免范围校验读到
    字符串导致比较异常。
    """
    if not isinstance(props, list):
        return []
    out: List[Dict[str, Any]] = []
    for raw in props:
        if not isinstance(raw, dict):
            continue
        p = dict(raw)
        if is_writable(p):
            for k in ("min", "max"):
                v = _num(p.get(k))
                if v is None:
                    p.pop(k, None)
                else:
                    p[k] = v
            lo, hi = _range_of(p)
            if lo is not None and hi is not None and lo > hi:
                # 下限大于上限：视为填写无效（保留原值但交换无意义，直接清空）
                p.pop("min", None)
                p.pop("max", None)
        else:
            p.pop("min", None)
            p.pop("max", None)
        out.append(p)
    return out
