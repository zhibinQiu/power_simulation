"""设备硬件唯一 ID（hwId）——绑定硬件特征，改名不变。

设计要点：
  * hwId 是设备在整条链路上的**唯一身份键**，与显示名（name）解耦：
    平台改名 → 只改 name，hwId 保持不变 → 云端 CRD、盒子配置、时序库历史不断链。
  * 取值规则按「协议 + 最能代表这块硬件的稳定特征」派生（LoRa 取 DevEUI、Modbus 取
    串口/从站号或 IP/端口/从站号、OPC UA 取 endpoint、蓝牙取 MAC、蜂窝取 IMEI），
    全部派生不出时才退化为随机 ID——随机 ID 仍是「一次生成、终身不变」。
  * 必须是 K8s label value 安全串（字母数字与 -_. ，长度 ≤63），因为它会写进
    Device CRD 的 metadata.labels（nengtan.io/hwid）。
"""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any, Dict

HWID_LABEL = "nengtan.io/hwid"   # Device CRD 上承载 hwId 的 label 键
_MAX_LEN = 63
_UNSAFE = re.compile(r"[^a-z0-9]+")


def slug(s: str, limit: int = _MAX_LEN) -> str:
    """转小写并把非法字符折叠成 '-'，保证可作为 K8s label value。"""
    t = _UNSAFE.sub("-", str(s or "").lower()).strip("-")
    return t[:limit].strip("-")


def _h8(s: str) -> str:
    return hashlib.sha1(str(s or "").encode("utf-8")).hexdigest()[:8]


def hwid_of(dev: Dict[str, Any]) -> str:
    """按硬件特征派生 hwId；特征不足时返回 ''（调用方应退化为 new_hwid()）。"""
    proto = str(dev.get("protocol") or "").strip().lower()
    lora = dev.get("lora") or {}
    comm = dev.get("comm") or {}

    # LoRa：一台 DR206 透传 DTU 下常挂多个 485 传感器，故「终端 DevEUI + 从站号」才是
    # 一块传感器的唯一标识（只取 DevEUI 会让同终端下的多个从站撞成同一个身份）。
    eui = str(lora.get("devEUI") or "").strip()
    if eui:
        slave = str(lora.get("slaveId") or lora.get("slaveID") or "").strip()
        return slug(f"lora-{eui}" + (f"-s{slave}" if slave not in ("", "0") else ""))

    if comm:
        slave = comm.get("slaveID", comm.get("slaveId"))
        ctype = str(comm.get("commType") or "").strip().lower()
        ip = str(comm.get("tcpIP") or "").strip()
        # Modbus TCP：IP + 端口 + 从站号（一台网关下挂多个从站）
        if ctype == "tcp" or (ip and ctype != "serial"):
            if ip:
                return slug(f"mb-{ip}-{comm.get('tcpPort') or 502}-s{slave}")
        # Modbus RTU：串口基名 + 从站号（同一条 485 总线上从站号唯一）
        port_name = str(comm.get("serialPort") or "").rstrip("/").split("/")[-1]
        if port_name:
            return slug(f"mb-{port_name}-s{slave}")

    if proto.startswith("opcua"):
        url = str((dev.get("opcua") or {}).get("url") or "").strip()
        if url:
            return "opc-" + _h8(url)

    if proto.startswith("cellular"):
        cell = dev.get("cellular") or {}
        cid = str(cell.get("imei") or cell.get("deviceId") or "").strip()
        return "cel-" + (slug(cid) if cid else _h8(str(dev.get("name") or "")))

    if proto.startswith("bluetooth"):
        mac = str((dev.get("bluetooth") or {}).get("macAddress") or "").strip()
        if mac and mac.upper() != "AA:BB:CC:DD:EE:FF":   # 占位 MAC 不作硬件特征
            return "bt-" + slug(mac)

    return ""


def new_hwid() -> str:
    """硬件特征不足时的兜底：随机但终身不变。"""
    return "dev-" + uuid.uuid4().hex[:12]


def ensure_hwid(dev: Dict[str, Any], inherit: str = "", taken: Any = None) -> str:
    """确定一台设备的 hwId，优先级：已有 → 改名继承 → 硬件派生 → 随机。

    dev      : 设备定义（平台 box_devices.json 的一条 device）
    inherit  : 改名场景下被改名前那条记录的 hwId（保证改名前后同一身份）
    taken    : 已被其它设备占用的 hwId 集合；冲突时追加名字摘要保证唯一
    """
    cur = str(dev.get("hwId") or "").strip()
    hwid = cur or (str(inherit).strip()) or hwid_of(dev) or new_hwid()
    if taken and hwid in taken and not cur:
        hwid = slug(f"{hwid}-{_h8(str(dev.get('name') or ''))}")
    return hwid


def backfill_hwids(devices: list, models: list | None = None) -> int:
    """给尚无 hwId 的设备补齐（存量数据一次性迁移）。返回补齐条数。

    冲突处理：同一 hwId 被多台设备派生出来时（现场误配同端口同从站号），
    除第一台外追加名字摘要，避免两台设备共用一个身份。
    """
    taken: Dict[str, str] = {}
    filled = 0
    for dev in devices or []:
        if not isinstance(dev, dict):
            continue
        cur = str(dev.get("hwId") or "").strip()
        if cur:
            taken.setdefault(cur, str(dev.get("name") or ""))
            continue
        base = hwid_of(dev) or new_hwid()
        hwid = base
        if hwid in taken:
            hwid = slug(f"{base}-{_h8(str(dev.get('name') or ''))}")
        dev["hwId"] = hwid
        taken.setdefault(hwid, str(dev.get("name") or ""))
        filled += 1
    return filled
