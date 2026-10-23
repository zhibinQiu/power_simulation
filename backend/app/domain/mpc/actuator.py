"""执行器：把 MPC 输出的 (v_fan, i_tec) 落到两台 24 V 电源的可写点位上。

映射（本文件是唯一出处，改硬件只改这里）
------------------------------------------------------------------
    v_fan  ->  fengshan-power.voltage_set    风扇电源，恒压模式（work_mode=0）
    i_tec  ->  zhileng-power.current_set     制冷片电源，恒流模式（work_mode=1）

下发通道
------------------------------------------------------------------
云端 Broker 主题 ``cmd/{box}/cmd``，载荷由盒子 mapper 解析：

    {"box", "device", "cmd": "write", "property", "value", "request_id", "ts"}

盒子只在 ``config.json`` 的 ``writes[]`` 里按 ``property`` 找点位，找不到一律拒绝。
四个点位（voltage_set / current_set / work_mode / output_on）在
``config/box_devices.json`` 里都是 ``accessMode=rw``，由 lora_dtu 派生进 writes[]。

三条必须遵守的时序（实测踩过）
------------------------------------------------------------------
1. ``output_on`` 是输出总开关，**设了电压/电流不置线圈等于没输出** ——
   现象是「命令写成功、设备一动不动」。
2. ``current_set`` 只在恒流模式（``work_mode=1``）下生效；制冷片电源出厂停在
   恒压模式，直接写电流不会有任何动作。
3. 因此 TEC 的写入顺序固定为 work_mode -> current_set -> output_on，
   风扇为 work_mode -> voltage_set -> output_on。

安全性
------------------------------------------------------------------
- 值域硬校验：v_fan ∈ [0, 24] V，i_tec ∈ [0, 3] A（3 A 以上是模型的黑名单档，
  焦耳热翻倍却无可测降温），超出直接拒绝，不做静默限幅。
- 同值保持：同一个点位 30 s 内重复写同一个值会被跳过，避免每次求解都刷一遍
  Modbus 总线；``force=True``（人工点「下发」）可绕过。
- 所有成功/失败都写进决策日志（kind="apply"），现场可回溯「谁在什么时候把
  哪个点位改成了多少」。
"""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from app.core.config import config_path

from . import decision_log as DL

# ==========================================================================
# 映射表
# ==========================================================================
FAN_DEV = "fengshan-power"
FAN_V_PROP = "voltage_set"
FAN_MODE_PROP = "work_mode"
FAN_ON_PROP = "output_on"
FAN_MODE_CV = 0.0        # 恒压：风扇只看电压

TEC_DEV = "zhileng-power"
TEC_I_PROP = "current_set"
TEC_MODE_PROP = "work_mode"
TEC_ON_PROP = "output_on"
TEC_MODE_CC = 1.0        # 恒流：制冷片只看电流

FAN_V_MIN, FAN_V_MAX = 0.0, 24.0
TEC_I_MIN, TEC_I_MAX = 0.0, 3.0    # 模型动作集上限（5 A 已进黑名单）

#: 同值保持期 [s]：期内重复写同值直接跳过
KEEP_S = 30.0
#: 上次失败时的重试间隔 [s]：失败不能缓太久，否则断线恢复后设备一直没动作
RETRY_S = 3.0

_LOCK = threading.Lock()
_LAST: Dict[str, Dict[str, Any]] = {}
#: 单调递增序号：同一毫秒内连发多条 write 时，光靠时间戳会撞出相同 request_id，
#: 盒子若按请求号去重就会把后两条静默丢掉（现象：只有第一个点位生效）。
_SEQ = 0


class ActuatorError(ValueError):
    """下发参数不合法（值域越界 / 找不到设备）。"""


# ==========================================================================
# 设备 -> 盒子
# ==========================================================================
def _box_of(device: str) -> Optional[str]:
    """从 config/box_devices.json 查设备挂在哪个盒子上（node 即盒子 id）。"""
    try:
        with open(config_path("box_devices.json"), "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:  # noqa: BLE001
        return None
    for dev in (cfg.get("devices") or []):
        if str(dev.get("name") or "") == device:
            return str(dev.get("node") or dev.get("box") or "") or None
    return None


def _targets() -> Dict[str, str]:
    """两台设备的盒子（找不到就报错，绝不猜一个默认值乱发）。"""
    out: Dict[str, str] = {}
    for dev in (FAN_DEV, TEC_DEV):
        box = _box_of(dev)
        if not box:
            raise ActuatorError(f"配置里找不到设备 {dev} 所属的盒子（config/box_devices.json）")
        out[dev] = box
    return out


# ==========================================================================
# 单点写入
# ==========================================================================
def _write(box: str, device: str, prop: str, value: float,
           force: bool = False, tag: str = "mpc",
           dry_run: bool = False) -> Dict[str, Any]:
    """写一个点位。返回 {device, property, value, ok, skipped, error, dry}。"""
    global _SEQ
    from app.mqtt_source import publish

    v = float(value)
    key = "%s|%s|%s" % (box, device, prop)
    now = time.time()

    if not force:
        with _LOCK:
            last = _LAST.get(key)
        if last and abs(float(last.get("v") or 0.0) - v) < 1e-9:
            keep = KEEP_S if last.get("ok") else RETRY_S
            if now - float(last.get("ts") or 0.0) < keep:
                return {"device": device, "property": prop, "value": v,
                        "ok": True, "skipped": True, "error": "", "dry": dry_run}

    with _LOCK:
        _SEQ += 1
        seq = _SEQ
    payload = {
        "box": box, "device": device, "cmd": "write", "property": prop,
        "value": v,
        "request_id": "%s-%s-%s-%d-%d" % (tag, device, prop, int(now * 1000), seq),
        "ts": now,
    }

    # 试运行：只组装 payload，不发 MQTT（现场联调时先用它核对点位与取值）
    if dry_run:
        return {"device": device, "property": prop, "value": v,
                "ok": True, "skipped": False, "error": "", "dry": True,
                "payload": payload}

    try:
        res = publish("cmd/%s/cmd" % box, payload)
    except Exception as e:  # noqa: BLE001
        res = {"ok": False, "error": str(e)}
    ok = bool((res or {}).get("ok"))

    with _LOCK:
        _LAST[key] = {"v": v, "ts": now, "ok": ok}
    return {"device": device, "property": prop, "value": v, "ok": ok,
            "skipped": False, "error": "" if ok else str((res or {}).get("error") or "发布失败"),
            "dry": False}


# ==========================================================================
# 对外：下发一个动作
# ==========================================================================
def apply(v_fan: float, i_tec: float, *, force: bool = False,
          hold_s: Optional[float] = None, note: str = "",
          dry_run: bool = False) -> Dict[str, Any]:
    """把一组 (风扇电压, 制冷片电流) 下发到两台电源。

    :param v_fan:  风扇设定电压 [V]，0~24
    :param i_tec:  制冷片设定电流 [A]，0~3（0 表示关断 TEC 输出）
    :param force:  True = 无视同值保持期，强制重发（人工「下发」按钮用）
    :param hold_s: 本段计划保持时长 [s]，仅用于日志
    :param dry_run: True = 只组装 payload 不发布（联调核对点位用）
    """
    try:
        vv = float(v_fan)
        vi = float(i_tec)
    except (TypeError, ValueError):
        raise ActuatorError("v_fan / i_tec 必须是数字")
    if not (FAN_V_MIN - 1e-9 <= vv <= FAN_V_MAX + 1e-9):
        raise ActuatorError(f"风扇电压 {vv:g} V 超出可下发范围 {FAN_V_MIN:g}~{FAN_V_MAX:g} V")
    if not (TEC_I_MIN - 1e-9 <= vi <= TEC_I_MAX + 1e-9):
        raise ActuatorError(f"制冷片电流 {vi:g} A 超出可下发范围 {TEC_I_MIN:g}~{TEC_I_MAX:g} A")

    boxes = _targets()

    # 两台设备并行、设备内串行：
    #   publish() 每次建独立 MQTT 连接（约 1.1 s），6 条串行要 6.6 s，页面会一直是「下发中」。
    #   设备之间互不依赖，可并行；同一设备内的 3 条必须保序（output_on 要最后置位）。
    def _do_fan() -> List[Dict[str, Any]]:
        fb = boxes[FAN_DEV]
        # work_mode / output_on 走同值保持：稳态下这两条不变，跳过可省两次建连。
        # 首次（进程内无记录）一定会真发，不会漏掉 output_on。
        # 例外：断输出（=0）必须强发 —— 「以为停了其实没停」是这里最不能接受的失败。
        v_on = 1.0 if vv > 0 else 0.0
        return [
            _write(fb, FAN_DEV, FAN_MODE_PROP, FAN_MODE_CV, force=False, dry_run=dry_run),
            _write(fb, FAN_DEV, FAN_V_PROP, vv, force=force, dry_run=dry_run),
            _write(fb, FAN_DEV, FAN_ON_PROP, v_on, force=(True if v_on == 0.0 else force),
                   dry_run=dry_run),
        ]

    def _do_tec() -> List[Dict[str, Any]]:
        tb = boxes[TEC_DEV]
        i_on = 1.0 if vi > 0 else 0.0
        return [
            _write(tb, TEC_DEV, TEC_MODE_PROP, TEC_MODE_CC, force=False, dry_run=dry_run),
            _write(tb, TEC_DEV, TEC_I_PROP, vi, force=force, dry_run=dry_run),
            _write(tb, TEC_DEV, TEC_ON_PROP, i_on, force=(True if i_on == 0.0 else force),
                   dry_run=dry_run),
        ]

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_fan = pool.submit(_do_fan)
        f_tec = pool.submit(_do_tec)
        writes = f_fan.result() + f_tec.result()

    ok = all(w["ok"] for w in writes)
    fails = [w for w in writes if not w["ok"]]

    lines = [
        f"下发动作：风扇 {vv:g} V -> {FAN_DEV}.{FAN_V_PROP}，"
        f"制冷片 {vi:g} A -> {TEC_DEV}.{TEC_I_PROP}"
        + (f"，本段保持 {hold_s:.0f} s" if hold_s else "")
        + ("（试运行：只组装载荷，未真正下发）" if dry_run else ""),
        "点位明细：" + "，".join(
            f"{w['device']}.{w['property']}={w['value']:g}"
            + ("（同值跳过）" if w.get("skipped") else "" if w["ok"] else " ✗")
            for w in writes),
    ]
    if note:
        lines.insert(0, note)
    if fails:
        lines.append("失败点位：" + "；".join(f"{w['device']}.{w['property']} {w['error']}" for w in fails))
    if not dry_run:                     # 试运行不写业务日志，避免把演练混进现场轨迹
        DL.write("apply", f"下发 {vv:g} V / {vi:g} A", lines,
                 extra={"v_fan": vv, "i_tec": vi, "ok": ok, "writes": len(writes),
                        "failed": len(fails), "hold_s": hold_s})

    return {
        "ok": ok,
        "dry_run": bool(dry_run),
        "v_fan": vv, "i_tec": vi,
        "targets": {"v_fan": f"{FAN_DEV}.{FAN_V_PROP}", "i_tec": f"{TEC_DEV}.{TEC_I_PROP}"},
        "writes": writes,
        "failed": fails,
        "message": (("试运行通过（未下发）：" if dry_run else "已下发：")
                    + "，".join([f"风扇 {vv:g} V", f"制冷片 {vi:g} A"])) if ok
        else ("下发失败：" + "；".join(f"{w['device']}.{w['property']} {w['error']}" for w in fails)),
    }


def stop(*, reason: str = "手动停止", dry_run: bool = False) -> Dict[str, Any]:
    """两路输出全部归零（先断输出，再清设定）。"""
    return apply(0.0, 0.0, force=True, note=f"停止：{reason}", dry_run=dry_run)
