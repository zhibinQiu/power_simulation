"""LoRa 透传 DTU 多从站问帧：平台「从站号」→ 盒子 mapper 的 lora.polls，并下发生效。

平台侧口径（重要）：平台不建模「数据是从哪台物理设备来的」，只维护**每台采集
设备自己的一份配置**，用它下发取数指令、并按它查询这条序列的数据。

现场形态：一台 DR206 类 LoRa 透传 DTU = 一个 devEUI，下面挂多台 485 传感器，彼此
只靠 Modbus 从站号区分 —— 但在界面上它们就是几台**彼此平等**的采集设备：

  * 每台设备各有一份自己的配置（devEUI + 从站号 + 点位），据此生成它自己的那条
    问帧（lora.polls[0] = {slave, hex, fPort, points}），各自下发、各自上报；
  * **不存在「主设备 / 次要设备」**：谁都不代谁取数、谁也不给别人让路；某台设备
    参不参与采集，只由用户在平台上的启用状态（enabled）决定；
  * 同挂一个终端（同一个 devEUI）只是现场拓扑信息，用于展示，不参与任何控制决策；
  * slaveId 是这台设备自己的一致性配置，唯一用途就是拼出正确的下发指令。

本模块负责把「每台设备的 lora.slaveId」翻译成它自己的那条问帧，并经 MQTT
cmd/{box}/config 下发（盒子 mapper 有 config/config_get 分支：写盘后立即在运行期生效，
不依赖 systemctl 重启）。

历史故障（本模块存在的理由）：这段生成逻辑曾整体丢失，于是平台改从站号只写进本地配置
与云端 CRD，盒子 config.json 的 polls 不更新 —— 下发数据里根本没有问帧，设备长期无数据
且无任何报错（表现为"现场终端离线"）。这里把生成口径固化并用单测锁住。
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from .. import mqtt_source
from ._shared import _load_devices

LORA_PROTOCOLS = ("lora", "lorawan")
DEFAULT_FPORT = 10


# ---------------------------------------------------------------------------
# Modbus 帧与点位口径（与盒子 mapper 的 _build_modbus_read_frame / _decode_modbus_reply 同口径）
# ---------------------------------------------------------------------------
def _mb_crc16(data: bytes) -> int:
    """Modbus RTU CRC16（多项式 0xA001，低字节在前）。"""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 1) else (crc >> 1)
    return crc & 0xFFFF


def build_read_frame(slave: int, addr: int = 0, count: int = 1, fc: int = 3) -> str:
    """拼 Modbus 读请求帧（hex 字符串，含 CRC）。

    手算 CRC 是现场配置最常见的出错点：帧里错一个字节终端就完全不应答，
    表现为"设备离线"却查不出原因，所以一律由平台拼好再下发。
    """
    body = bytes([int(slave) & 0xFF, int(fc) & 0xFF,
                  (int(addr) >> 8) & 0xFF, int(addr) & 0xFF,
                  (int(count) >> 8) & 0xFF, int(count) & 0xFF])
    crc = _mb_crc16(body)
    return (body + bytes([crc & 0xFF, (crc >> 8) & 0xFF])).hex()


def _norm_eui(v: Any) -> str:
    return str(v or "").strip().lower().replace("-", "").replace(":", "").replace(" ", "")


def _mapper_type(t: Any) -> str:
    """平台点位类型 -> mapper 解析类型（只保留 mapper 认得的数值类型）。"""
    s = str(t or "").strip().lower()
    if s in ("float", "double", "float32", "f32"):
        return "float32"
    if s in ("uint", "uint16", "u16", "unsigned"):
        return "uint16"
    if s in ("int32", "i32", "long"):
        return "int32"
    return "int16"


def _reg_width(mapper_type: str) -> int:
    return 2 if mapper_type in ("float32", "int32", "uint32") else 1


def _register_span(props: List[Dict[str, Any]]) -> Tuple[int, int, int]:
    """点位集合 -> (起始寄存器地址, 寄存器个数, 功能码)。

    LoRa 透传 DTU 下面挂的就是 Modbus 传感器，所以问帧口径与 Modbus 设备一致：
    寄存器类型含 input 用 FC4，否则 FC3；未配寄存器口径（早期 LoRa 点位只有 scale）
    时按「0 号寄存器读 1 个」兜底 —— 与现场单寄存器温度传感器一致。
    """
    items = [p for p in (props or []) if isinstance(p, dict)]
    if not items:
        return 0, 1, 3
    spans = []
    for p in items:
        try:
            reg = int(p.get("register", p.get("registerAddr", 0)) or 0)
        except (TypeError, ValueError):
            reg = 0
        spans.append((reg, reg + _reg_width(_mapper_type(p.get("type")))))
    addr = min(a for a, _ in spans)
    end = max(b for _, b in spans)
    fc = 4 if any("input" in str(p.get("registerType") or "").lower() for p in items) else 3
    return addr, max(1, end - addr), fc


def _poll_points(props: List[Dict[str, Any]], addr: int) -> List[Dict[str, Any]]:
    """点位 -> mapper 应答解析规则（regIndex 相对起始地址的寄存器下标）。"""
    out = []
    for i, p in enumerate(props or []):
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "").strip()
        if not name:
            continue
        try:
            reg = int(p.get("register", p.get("registerAddr", 0)) or 0)
        except (TypeError, ValueError):
            reg = addr
        try:
            scale = float(p.get("scale", 1) or 1)
        except (TypeError, ValueError):
            scale = 1.0
        out.append({"property": name, "type": _mapper_type(p.get("type")),
                    "scale": scale, "regIndex": max(0, reg - addr)})
    return out


# ---------------------------------------------------------------------------
# 计划：按 devEUI 分组，算出每台设备的从站问帧
# ---------------------------------------------------------------------------
def _poll_of(dev: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """单台 LoRa 设备的多从站问帧项；无需主动轮询（无 devEUI / 站号为 0）返回 None。"""
    lora = dev.get("lora") or {}
    eui = _norm_eui(lora.get("devEUI"))
    try:
        slave = int(lora.get("slaveId") or 0)
    except (TypeError, ValueError):
        slave = 0
    if not eui or slave <= 0:
        return None
    props = dev.get("properties") or []
    addr, count, fc = _register_span(props)
    dl = lora.get("downlink") or {}
    try:
        fport = int(dl.get("fPort") or 0) or DEFAULT_FPORT
    except (TypeError, ValueError):
        fport = DEFAULT_FPORT
    return {
        "slave": slave,
        "device": str(dev.get("name") or "").strip(),
        "hex": build_read_frame(slave, addr, count, fc),
        "functionCode": fc,
        "registerAddr": addr,
        "count": count,
        "fPort": fport,
        "points": _poll_points(props, addr),
    }


def lora_plan(devices: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """把每台 LoRa 设备的 devEUI + 从站号翻译成它自己的那条问帧（纯函数，不触网）。

    返回：
      groups: [{devEUI, members:[设备名], polls:[每台设备自己的一条问帧]}]
      skipped: [{name, reason}] —— 未填 devEUI / 从站号为 0 的设备拼不出问帧

    按 devEUI 归组既是现场拓扑（这几台挂在同一台 LoRa 透传 DTU 下），也是采集口径：
    组内只由一台主设备承载全部 polls 串行轮询，其余成员停采、由主设备代报（见
    build_patches）。
    """
    if devices is None:
        devices = (_load_devices().get("devices") or [])
    groups: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    skipped: List[Dict[str, Any]] = []
    for d in devices or []:
        if not isinstance(d, dict):
            continue
        if str(d.get("protocol") or "").strip().lower() not in LORA_PROTOCOLS:
            continue
        name = str(d.get("name") or "").strip()
        lora = d.get("lora") or {}
        eui = _norm_eui(lora.get("devEUI"))
        if not eui:
            skipped.append({"name": name, "reason": "未填 devEUI，无法主动下发问帧"})
            continue
        poll = _poll_of(d)
        if poll is None:
            skipped.append({"name": name, "reason": "从站号为 0（被动上报），不入多从站轮询表"})
            continue
        g = groups.get(eui)
        if g is None:
            g = {"devEUI": eui, "members": [], "polls": []}
            groups[eui] = g
            order.append(eui)
        g["members"].append(name)
        g["polls"].append(poll)
    return {"groups": [groups[e] for e in order], "skipped": skipped}


# ---------------------------------------------------------------------------
# 下发条目：以盒子当前配置为底稿（拿不到则以平台定义为底稿），只改 LoRa 相关字段
# ---------------------------------------------------------------------------
def _device_points(dev: Dict[str, Any]) -> List[Dict[str, Any]]:
    """平台设备点位 -> mapper 条目 points（被动上报/单设备解析用）。"""
    props = dev.get("properties") or []
    addr, _count, _fc = _register_span(props)
    return _poll_points(props, addr)


def _base_entry(dev: Dict[str, Any], snap: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """下发条目的底稿：优先用盒子上正在跑的那份（避免覆盖现场定制），否则按平台定义生成。"""
    if snap:
        return json.loads(json.dumps(snap))  # 深拷贝，避免改到缓存里的对象
    lora = dict(dev.get("lora") or {})
    try:
        interval = float(int(dev.get("collectCycle") or 5000) / 1000.0)
    except (TypeError, ValueError):
        interval = 5.0
    return {
        "name": str(dev.get("name") or "").strip(),
        "namespace": str(dev.get("namespace") or "default"),
        "protocol": "lora",
        "interval": interval,
        "lora": lora,
        "points": _device_points(dev),
        "enabled": True,
    }


def build_patches(devices: Optional[List[Dict[str, Any]]] = None,
                  snapshot: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """生成要下发到盒子的设备条目 + 变更说明。

    snapshot 为盒子当前 devices（经 cmd/config_get 取回，可为空）：
    按 name 合并下发是「同名整体覆盖」，因此条目必须是完整的 —— 用盒子现配置做底稿
    可以保住现场的串口/点位等定制字段，只动 LoRa 的 polls/downlink 与 enabled。
    """
    if devices is None:
        devices = (_load_devices().get("devices") or [])
    snap_by_name = {str(d.get("name")): d for d in (snapshot or []) if isinstance(d, dict)}
    pl = lora_plan(devices)
    # 归组后整组只由「主设备」那一个采集线程串行轮询：mapper 的 _read_polls 是
    # 逐站下发、等该站应答再问下一站（半双工 485 本来就一问一答），多条问帧在同
    # 一瞬间挤同一个 DTU 的下行窗口会互相顶掉应答 —— 实测 4 台温度各 5s 独立下发
    # 时抓包 3 次里只有 1 次回数据，四台读数一路老化到几分钟。
    # 主设备 = 组内第一台启用中的设备，它的 polls 带上整组所有从站，应答按
    # polls[].device 由 mapper 分流上报到各自的平台设备（routed），成员因此停采。
    poll_of: Dict[str, Dict[str, Any]] = {}
    peers_of: Dict[str, List[str]] = {}
    group_polls_of: Dict[str, List[Dict[str, Any]]] = {}
    for g in pl["groups"]:
        for p in g["polls"]:
            poll_of[str(p.get("device") or "")] = p
        all_polls = sorted(g["polls"], key=lambda x: int(x.get("slave") or 0))
        for m in g["members"]:
            peers_of[str(m)] = list(g["members"])
            group_polls_of[str(m)] = all_polls
    # 主设备 = 组内第一台设备：采集设备没有「启用/停用」之分，平台上有就采集、
    # 不想采就在平台上删掉（三端同步），所以选主不看任何 enabled 之类的开关字段。

    patches: List[Dict[str, Any]] = []
    changes: List[str] = []
    # 盒子侧要删掉的条目：平台已删除的设备、以及由主设备代采的组内成员。
    # 采集设备没有「停用」这一档 —— 要么采集、要么在平台上删除（三端同步清干净）。
    remove: List[str] = []
    for d in devices or []:
        if not isinstance(d, dict):
            continue
        if str(d.get("protocol") or "").strip().lower() not in LORA_PROTOCOLS:
            continue
        name = str(d.get("name") or "").strip()
        lora = dict(d.get("lora") or {})
        entry = _base_entry(d, snap_by_name.get(name))
        # hwId：硬件唯一 ID 随配置下发到盒子，mapper 上报时回传 → 云端时序子表以它为身份键，
        # 设备改名只改显示名，历史曲线不断链。
        hwid = str(d.get("hwId") or "").strip()
        if hwid:
            entry["hwId"] = hwid
        cur_lora = dict(entry.get("lora") or {})
        cur_lora.update({k: v for k, v in lora.items()
                         if k not in ("polls", "downlink")})
        # 平台未配的 LoRa 高级项（decode/maxAge/账号等）沿用盒子现配置，不被空值冲掉
        for k, v in lora.items():
            if v not in (None, "", {}, []) or k not in cur_lora:
                cur_lora[k] = v

        mine = poll_of.get(name)
        members = [n for n in (peers_of.get(name) or []) if n]
        primary = members[0] if members else name
        if not (mine and primary == name):
            # 不生成下发条目：
            #   - 组内成员（由主设备代采）：读数由主设备按 polls[].device 代报，盒子
            #     侧不需要它的条目；
            #   - 缺 devEUI / 从站号：拼不出问帧，盒子侧同样无从采集。
            # 两种情况若盒子配置里还留着旧条目，都随本次下发一并删除（remove）。
            if mine:
                remove.append(name)
                changes.append("%s: 由主设备 %s 代采（终端…%s 站%d），盒子不保留该条目" % (
                    name, primary, str(lora.get("devEUI") or "")[-4:], int(mine["slave"])))
            else:
                changes.append("%s: 未配 devEUI 或从站号，拼不出下发指令" % name)
            continue
        # 主设备承载整组从站的问帧，逐站串行问；读数按 polls[].device 分流上报
        polls = [dict(p) for p in (group_polls_of.get(name) or [mine])]
        cur_lora["polls"] = polls
        dl = dict(cur_lora.get("downlink") or {})
        dl.update({
            "enabled": True,
            "mode": "poll",
            "fPort": int(mine.get("fPort") or DEFAULT_FPORT),
            "hex": "",            # 按各从站 poll 项自己的 hex 下发
            "timeout": dl.get("timeout") or 5.0,
        })
        cur_lora["downlink"] = dl
        cur_lora["slaveId"] = int(mine["slave"])
        entry["lora"] = cur_lora
        # 平台上有这台设备就采集；不想采就在平台上删掉（三端同步），没有「停用」态
        entry["enabled"] = True
        # 点位：盒子现配置里已有（现场定制）就沿用，没有才按平台点位生成
        entry["points"] = entry.get("points") or _device_points(d) or []

        others = [n for n in members if n != name]
        what = "主设备轮询站%s" % "、".join(str(int(p["slave"])) for p in polls)
        if others:
            what += "（终端…%s，代采：%s）" % (
                str(lora.get("devEUI") or "")[-4:], "、".join(others))
        changes.append("%s: %s" % (name, what))
        patches.append(entry)

    return {"patches": patches, "changes": changes, "plan": pl, "remove": remove,
            "snapshot": bool(snapshot)}


# ---------------------------------------------------------------------------
# 取盒子当前配置 + 下发
# ---------------------------------------------------------------------------
def fetch_box_devices(box: str, timeout: float = 8.0) -> Optional[List[Dict[str, Any]]]:
    """经 MQTT 向盒子要当前生效配置（cmd/config_get），等回执拿 devices。

    取不到返回 None（不阻断下发，只是失去"以盒子现配置为底稿"的保护）。
    """
    box = (box or "").strip()
    if not box:
        return None
    rid = uuid.uuid4().hex[:12]
    mqtt_source.publish_box_cmd(box, {"cmd": "config_get", "request_id": rid})
    deadline = time.time() + timeout
    seen = set()
    while time.time() < deadline:
        for ev in mqtt_source.box_app_events(box) or []:
            key = id(ev)
            if key in seen:
                continue
            seen.add(key)
            if str(ev.get("request_id") or "") != rid:
                continue
            detail = ev.get("detail") or {}
            devs = detail.get("devices")
            if isinstance(devs, list) and devs:
                return devs
            return None
        time.sleep(0.5)
    return None


def push_lora_config(box: str = "", dry_run: bool = False, timeout: float = 8.0) -> Dict[str, Any]:
    """把平台「每台采集设备自己的取数配置」推到盒子（cmd/{box}/config）。

    平台侧没有独立的「同步问帧」动作：slaveId 是每台设备自己的一致性配置，
    保存设备就该连带下发，规则是：

      * 同一 devEUI（同一台 LoRa 透传 DTU）下的多台 485 传感器只由「主设备」那一个
        采集线程串行轮询：主设备的 polls 带上整组从站的问帧，应答按 polls[].device
        分流上报到各自的平台设备，组内其余成员 enabled=false 停采 —— 否则多个线程
        同时下发会把同一个 DTU 的下行窗口挤爆（实测 4 台各 5s 独立下发时，抓包 3 次
        里只有 1 次回数据）；
      * 以盒子现配置为底稿，保住 broker/账号/maxAge/decode 等现场定制字段；
      * 采集设备没有「停用」这一档：盒子还在跑、平台已没有的条目（改名后的旧名 /
        已删设备 / 由主设备代采的成员）一律从盒子配置里删除（payload.remove）——
        否则旧任务继续上报幽灵数据，改名场景下还会和自己的新名抢同一个从站。
    """
    data = _load_devices()
    devices = data.get("devices") or []
    box = (box or "").strip()
    if not box:
        box = str(((devices or [{}])[0] or {}).get("node") or "").strip()
    if not box:
        return {"ok": False, "error": "未指定盒子（node），无法下发"}
    snapshot = fetch_box_devices(box, timeout=timeout) or []
    built = build_patches(devices, snapshot)
    patches = built["patches"]

    # 盒子侧要删掉的条目 = 代采成员（build_patches 给出）+ 盒子里还留着、但平台已
    # 没有的 LoRa 条目（平台上删掉的设备 / 改名前的旧名）。一律删除而非停采。
    wanted = {str(p.get("name") or "") for p in patches}
    remove = list(built.get("remove") or [])
    for d in snapshot:
        if not isinstance(d, dict) or not (d.get("lora") or {}):
            continue
        name = str(d.get("name") or "")
        if name and name not in wanted and name not in remove:
            remove.append(name)
    if remove:
        built["changes"].append("盒子删除条目：%s（平台上没有对应设备 / 由主设备代采）"
                                % "、".join(sorted(set(remove))))

    # 平台当前的 LoRa 设备名全集：盒子据此把名单外的 lora 条目（现场残留 / 改名旧名 /
    # 拿不到回执因而算不进 remove 的条目）一并删掉，不再上报幽灵数据
    lora_names = sorted({str(d.get("name") or "").strip() for d in devices or []
                         if isinstance(d, dict)
                         and str(d.get("protocol") or "").strip().lower() in LORA_PROTOCOLS
                         and str(d.get("name") or "").strip()})

    if not patches and not remove:
        return {"ok": True, "box": box, "applied": False, "changes": [],
                "note": "没有 LoRa 采集设备，无需下发", "plan": built["plan"]}
    if dry_run:
        return {"ok": True, "box": box, "dryRun": True, "changes": built["changes"],
                "patches": built["patches"], "remove": sorted(set(remove)),
                "loraNames": lora_names,
                "plan": built["plan"], "snapshot": built["snapshot"]}
    payload = {"cmd": "config", "devices": built["patches"], "replace": False,
               "lora_names": lora_names, "request_id": uuid.uuid4().hex[:12]}
    if remove:
        payload["remove"] = sorted(set(remove))
    res = mqtt_source.publish_box_cmd(box, payload)
    return {"ok": bool(res.get("ok")), "box": box, "topic": res.get("topic"),
            "error": res.get("error") if not res.get("ok") else "",
            "applied": bool(res.get("ok")), "changes": built["changes"],
            "remove": sorted(set(remove)),
            "plan": built["plan"], "snapshot": built["snapshot"],
            "note": "已下发；盒子写盘后运行期即生效（回执见云端日志 state/%s/deploy）" % box}


# 旧名兼容：/api/box/lora/sync 与运维脚本仍在用 lora_sync
lora_sync = push_lora_config
