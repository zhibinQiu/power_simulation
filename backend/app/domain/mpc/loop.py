"""闭环执行：**每台反馈设备各报一次 = 一轮** -> 用最新温度重解 -> 下发新的当前段。

为什么不是「一段跑完再切下一段」
--------------------------------
现场采集周期并不固定：`zhileng-temp` / `env-temp` / `shuitong-temp` 三台设备的上报
间隔各不相同（实测 5~30 s 都有），而且会随信号质量漂移。按固定时长切段会让「动作」
和「真实温度」错拍 —— 段还没跑完温度已经偏离预测，或者设备迟迟不报、动作一直停在旧值
（最坏情况：温度已经降下去了，制冷片还在满功率烧）。

所以改成事件驱动的闭环：

    三台反馈设备各出现一次**新的**上报  ->  算一轮
    用这一轮的最新温度 + 剩余时间重解    ->  把新的当前段下发到设备
    继续等下一轮

「段时长」仍然展示（没有新反馈时，它就是这段该跑多久的参考值），但**切换只由反馈驱动**，
不再由计时器驱动。

安全联锁（每条都对应一种现场事故）
----------------------------------
1. 当前温度 `DEADLOCK_S` 秒没有新上报 -> 立即 0/0 退出。
   「页面显示在控温、实际已经失联」是这里最不能接受的失败。
2. 到时限 -> 0/0 退出（计划本来就只覆盖到时限，超时继续跑就是没人负责的行为）。
3. 温度已低于目标 -> 0/0 退出。模型只做降温，没有加热能力，继续开就是过冷。
4. 重解被参数校验拒绝（如目标高于当前温度）连续 `MAX_REJECT` 次 -> 保持动作并告警，
   不盲目下发一个自己不认的解。
5. 未启用 / 自检不过 -> 拒绝启动与拒绝下发（与单段下发同一套闸门）。
6. `dry_run` -> 只组装载荷返回，**不启动线程、不发 MQTT**，用于联调核对点位。
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

from app.core.config import DATA_DIR

from . import actuator as AC
from . import decision_log as DL
from . import params as P
from . import service as SV
from .feedback import get_feedback

#: 闭环运行标记。服务重启 / 热重载会清空内存状态，但设备仍在按最后一次设定输出 ——
#: 启动时读这个文件，把「上次没正常收尾」的闭环归零（见 recover_on_boot）。
_STATE_PATH = os.path.join(DATA_DIR, "mpc_loop.json")

#: 轮询云端设备缓存的间隔 [s]。0.5 s 足以跟上最快的采集周期，又不至于空转烧 CPU。
POLL_S = 0.5
#: 两次重解之间的最小间隔 [s]。设备报得比这更快时合并成一轮，避免高频刷 Modbus。
MIN_REPLAN_S = 12.0
#: 一轮最多等多久 [s]。有设备长期不报时，用现有值继续，不把闭环卡死。
ROUND_MAX_WAIT_S = 180.0
#: 当前温度（zhileng-temp）多久没新数据就判定失联 [s]
DEADLOCK_S = float(P.FB_STALE_S) + 30.0
#: 连续多少次重解被拒就停机
MAX_REJECT = 3
#: 状态里保留的流水行数
LINES_MAX = 40
#: 剩余时间不足该值时不再重解，按「收尾」处理（DP 的最小段长是 300 s，再解没有意义）
TAIL_S = 60.0


# ==========================================================================
# 状态
# ==========================================================================
class _State:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.stop_evt = threading.Event()

        self.t_target = 0.0
        self.horizon_s = 0.0
        self.started_ts = 0.0
        self.deadline = 0.0

        self.rounds = 0            # 完成的「反馈齐一轮」次数
        self.replans = 0           # 成功重解次数
        self.sends = 0             # 实际下发次数
        self.rejects = 0           # 连续重解被拒次数
        self.reason = ""

        self.action: Optional[Dict[str, Any]] = None   # 当前正在执行的段
        self.plan: List[dict] = []                     # 最近一次求解的完整分段
        self.plan_mode = ""
        self.plan_ts: Optional[float] = None
        self.plan_t_s: Optional[float] = None          # 求解时用的当前温度

        self.t_now: Optional[float] = None
        self.tenv: Optional[float] = None
        self.twater: Optional[float] = None

        self.pending: Dict[str, Optional[float]] = {}   # 本轮基线（last_seen）
        self.seen: Dict[str, Optional[float]] = {}      # 最新 last_seen
        self.last_error = ""
        self.lines: List[str] = []
        self.last_send_ts: Optional[float] = None
        self.last_send_ok: Optional[bool] = None


_ST = _State()
_GUARD = threading.Lock()
#: 启动中标志：求解 + 首次下发要 3~4 s，期间若用户连点两次按钮，
#: 只靠 `_ST.running` 拦不住（它要等启动尾部才置 True）。
_STARTING = threading.Event()


def _devices() -> List[str]:
    """参与一轮判定的设备（三台温度源，去重后按固定顺序）。"""
    out: List[str] = []
    for dev in P.FB_SOURCES.values():
        if dev not in out:
            out.append(dev)
    return out


def _persist(running: bool) -> None:
    """把「闭环是否还在跑」落盘，供重启后的归零兜底使用。失败不影响主流程。"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        data = {
            "running": bool(running),
            "ts": time.time(),
            "t_target": _ST.t_target,
            "horizon_s": _ST.horizon_s,
            "started_ts": _ST.started_ts,
            "rounds": _ST.rounds,
        }
        tmp = _STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, _STATE_PATH)
    except Exception:                     # noqa: BLE001
        pass


def recover_on_boot() -> Optional[Dict[str, Any]]:
    """服务启动时调用：上次进程退出前闭环没正常收尾 -> 主动把两路输出归零。

    为什么需要这一步：`uvicorn --reload`（或崩溃、断电重启）会清空内存里的闭环状态，
    但设备仍在按最后一次设定的电压/电流输出 —— 页面显示「未启动」，风扇还在转、
    制冷片还在耗电，没人知道。宁可启动时多发一次 0/0。
    """
    try:
        with open(_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:                     # noqa: BLE001 —— 没有文件 = 上次就正常结束过
        return None
    if not data.get("running"):
        return None

    _persist(False)                       # 先落盘，避免反复触发
    try:
        res = SV.stop_output(reason="服务重启：恢复上次未收尾的闭环")
    except Exception as e:                # noqa: BLE001
        res = {"ok": False, "error": str(e)}
    DL.write("loop", "重启恢复：上次闭环未正常收尾，已归零",
             [f"重启前设定：目标 {data.get('t_target')} ℃ / "
              f"{float(data.get('horizon_s') or 0) / 60.0:.1f} min，已完成 {data.get('rounds')} 轮",
              "两路输出归零" if res.get("ok") else f"归零失败：{res.get('error')}"],
             extra={"source": "boot", "ok": bool(res.get("ok"))})
    return {"ok": bool(res.get("ok")), "stop": res}


def _note(text: str) -> None:
    """往状态流水里追加一行（带时间戳），同时打到 stdout 之外的决策日志由调用方决定。"""
    line = "%s  %s" % (time.strftime("%H:%M:%S"), text)
    with _ST.lock:
        _ST.lines.append(line)
        if len(_ST.lines) > LINES_MAX:
            del _ST.lines[0:len(_ST.lines) - LINES_MAX]


def _seen() -> Dict[str, Optional[float]]:
    """各设备最近一次上报的 epoch 秒；没有上报则为 None。"""
    try:
        from app import mqtt_source
        snap = mqtt_source.snapshot_cloud_devices()
    except Exception:                     # noqa: BLE001 —— MQTT 异常不能让闭环崩
        return {d: None for d in _devices()}

    out: Dict[str, Optional[float]] = {}
    for dev in _devices():
        info = snap.get(dev) or {}
        try:
            out[dev] = float(info.get("last_seen"))
        except (TypeError, ValueError):
            out[dev] = None
    return out


def _fresh_devices(baseline: Dict[str, Optional[float]],
                   now_seen: Dict[str, Optional[float]]) -> List[str]:
    """本轮已经出现「新上报」的设备。"""
    out = []
    for dev in _devices():
        cur = now_seen.get(dev)
        base = baseline.get(dev)
        if cur is None:
            continue
        # 进程启动后第一次拿到数据（base 为 None）也算一次新上报
        if base is None or cur > base + 1e-6:
            out.append(dev)
    return out


# ==========================================================================
# 起停
# ==========================================================================
def start(t_target: float, horizon_s: float, *, dry_run: bool = False,
          note: str = "") -> Dict[str, Any]:
    """求解一次并下发当前段，然后进入「反馈齐一轮就重解」的闭环。

    :param t_target:  目标温度 [℃]
    :param horizon_s: 到达时限 [s]（从点击下发这一刻起算，闭环中按剩余时间重解）
    :param dry_run:   True = 只算 + 只组装载荷，不启动闭环、不发 MQTT
    """
    with _GUARD:
        if _ST.running or _STARTING.is_set():
            return {"ok": False, "error": "闭环已在运行（或正在启动），请先点「停止并归零」"}
        _STARTING.set()
    try:
        return _start_inner(t_target, horizon_s, dry_run=dry_run, note=note)
    finally:
        _STARTING.clear()


def _start_inner(t_target: float, horizon_s: float, *, dry_run: bool,
                 note: str) -> Dict[str, Any]:
    """`start` 的实际内容（`_STARTING` 已置位，异常/早退都由外层 finally 清掉）。"""
    fb = get_feedback()
    src = fb.get("sources") or {}
    t_now = (src.get("t_now") or {}).get("value")
    if t_now is None:
        return {"ok": False,
                "error": "当前温度（zhileng-temp）没有实时上报，拒绝启动闭环："
                         "拿不到温度就无从判断该不该降温"}

    tenv = (src.get("tenv") or {}).get("value")
    twater = (src.get("twater") or {}).get("value")

    try:
        t_target = float(t_target)
        horizon_s = float(horizon_s)
    except (TypeError, ValueError):
        return {"ok": False, "error": "目标温度 / 时限必须是数字"}

    # 先解一次：参数不合法（如目标比当前还高）在启动阶段就拒绝，而不是等下发了一半才发现
    try:
        plan = SV.get_plan(float(t_now), t_target, horizon_s,
                           None if tenv is None else float(tenv),
                           None if twater is None else float(twater))
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    seg = _first_seg(plan)
    res = SV.apply_step(seg["v_fan"], seg["i_tec"], hold_s=seg.get("duration_s"),
                        index=0, note=(note or "闭环启动：第 1 段"), dry_run=dry_run)
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error") or res.get("message") or "下发失败",
                "plan": plan.get("plan") or []}

    now = time.time()
    with _ST.lock:
        _ST.running = not dry_run
        _ST.stop_evt.clear()
        _ST.t_target = t_target
        _ST.horizon_s = horizon_s
        _ST.started_ts = now
        _ST.deadline = now + horizon_s
        _ST.rounds = 0
        _ST.replans = 0
        _ST.sends = 0 if dry_run else 1
        _ST.rejects = 0
        _ST.reason = ""
        _ST.lines = []
        _ST.t_now = float(t_now)
        _ST.tenv = None if tenv is None else float(tenv)
        _ST.twater = None if twater is None else float(twater)
        _ST.plan = plan.get("plan") or []
        _ST.plan_mode = plan.get("mode") or ""
        _ST.plan_ts = now
        _ST.plan_t_s = float(t_now)
        _ST.action = {"v_fan": seg["v_fan"], "i_tec": seg["i_tec"],
                      "hold_s": seg.get("duration_s"), "since": now, "round": 0}
        _ST.last_send_ts = now
        _ST.last_send_ok = True
        _ST.last_error = ""
        _ST.pending = _seen()
        _ST.seen = dict(_ST.pending)

    _note(f"启动闭环：T={float(t_now):.2f} ℃ → 目标 {t_target:.2f} ℃ / {horizon_s/60:.1f} min，"
          f"立即下发风扇 {seg['v_fan']:g} V / 制冷片 {seg['i_tec']:g} A")
    if not dry_run:
        _persist(True)

    if dry_run:
        return {"ok": True, "dry_run": True, "running": False,
                "message": "试运行通过（未下发、未启动闭环）",
                "plan": plan.get("plan") or [], "action": seg,
                "plan_result": plan, "apply": res}

    DL.write("loop", f"启动闭环 {float(t_now):.1f} → {t_target:.1f} ℃ / {horizon_s/60:.1f} min",
             [f"第 1 段立即下发：风扇 {seg['v_fan']:g} V / 制冷片 {seg['i_tec']:g} A，"
              f"参考保持 {seg.get('duration_s') or 0:.0f} s",
              "之后每三台反馈设备各上报一次就重解并下发新的当前段"],
             extra={"t_target": t_target, "horizon_s": horizon_s, "plan_mode": _ST.plan_mode})

    t = threading.Thread(target=_worker, name="mpc-loop", daemon=True)
    with _ST.lock:
        _ST.thread = t
    t.start()

    return {"ok": True, "running": True, "plan": plan.get("plan") or [],
            "action": seg, "plan_mode": plan.get("mode"),
            "plan_result": plan,
            "message": "已下发当前段并启动闭环：三台反馈设备各上报一次即重解一次",
            "status": status()}


def stop(reason: str = "手动停止", *, zero: bool = True,
         dry_run: bool = False) -> Dict[str, Any]:
    """停止闭环。`zero=True` 时两路输出归零（停止永远真执行，不吃 dry_run）。"""
    with _ST.lock:
        was = _ST.running
        _ST.running = False
        _ST.reason = reason
    _ST.stop_evt.set()

    t = _ST.thread
    if t and t.is_alive() and t is not threading.current_thread():
        t.join(timeout=8.0)
    with _ST.lock:
        _ST.thread = None

    res = SV.stop_output(reason=reason, dry_run=dry_run) if zero else {"ok": True}
    if not dry_run:
        _persist(False)
    _note(f"停止闭环（{reason}）" + ("，两路输出已归零" if zero and res.get("ok") else ""))
    if was:
        DL.write("loop", f"停止闭环：{reason}",
                 [f"已运行 {(_ST.rounds)} 轮、重解 {_ST.replans} 次、下发 {_ST.sends} 次",
                  "两路输出归零（output_on=0，设定值清零）" if zero else "保留当前输出"],
                 extra={"reason": reason, "rounds": _ST.rounds, "zero": zero})
    return {"ok": bool(res.get("ok")), "running": False, "reason": reason,
            "stop": res, "status": status()}


# ==========================================================================
# 状态查询
# ==========================================================================
def status() -> Dict[str, Any]:
    """闭环当前状态（页面每 2 s 轮询一次）。"""
    now = time.time()
    with _ST.lock:
        remain = max(0.0, _ST.deadline - now) if _ST.deadline else 0.0
        seen_now = _seen()
        pending = {}
        for dev in _devices():
            cur = seen_now.get(dev)
            base = _ST.pending.get(dev)
            last = None
            try:
                last = None if cur is None else round(max(0.0, now - cur), 1)
            except Exception:             # noqa: BLE001
                last = None
            pending[dev] = {
                "device": dev,
                "reported": bool(cur is not None),
                # 未运行时没有「本轮」概念，一律不标记为已反馈（避免停机后还显示 3/3）
                "fresh": bool(_ST.running and cur is not None
                              and (base is None or cur > base + 1e-6)),
                "age_s": last,
            }
        _ST.seen = seen_now
        out = {
            "ok": True,
            "running": bool(_ST.running),
            "reason": _ST.reason,
            "t_target": _ST.t_target,
            "horizon_min": round(_ST.horizon_s / 60.0, 2),
            "elapsed_s": round(now - _ST.started_ts, 1) if _ST.started_ts else 0.0,
            "remaining_s": round(remain, 1),
            "remaining_min": round(remain / 60.0, 2),
            "rounds": _ST.rounds,
            "replans": _ST.replans,
            "sends": _ST.sends,
            "action": _ST.action,
            "plan": _ST.plan,
            "plan_mode": _ST.plan_mode,
            "plan_ts": (None if not _ST.plan_ts
                        else time.strftime("%H:%M:%S", time.localtime(_ST.plan_ts))),
            "plan_t_s": _ST.plan_t_s,
            "t_now": _ST.t_now,
            "tenv": _ST.tenv,
            "twater": _ST.twater,
            "feeds": pending,
            "devices": _devices(),
            "last_send_ts": (None if not _ST.last_send_ts
                             else time.strftime("%H:%M:%S", time.localtime(_ST.last_send_ts))),
            "last_send_ok": _ST.last_send_ok,
            "last_error": _ST.last_error,
            "lines": list(_ST.lines),
            "params": {"min_replan_s": MIN_REPLAN_S, "round_max_wait_s": ROUND_MAX_WAIT_S,
                       "deadlock_s": DEADLOCK_S, "tail_s": TAIL_S},
        }
    return out


# ==========================================================================
# 主循环
# ==========================================================================
def _first_seg(plan: dict) -> dict:
    segs = plan.get("plan") or []
    if not segs:
        raise ValueError("求解结果没有任何分段")
    return segs[0]


def _wait_round() -> str:
    """等三台设备各出现一次新上报。

    返回：
        "ready"     本轮齐了
        "stop"      收到停止信号
        "deadline"  到时限
        "deadlock"  当前温度失联
        "timeout"   等太久（有设备不报），仍然往下走
    """
    base = _ST.pending
    t0 = time.time()
    while not _ST.stop_evt.is_set():
        if time.time() >= _ST.deadline:
            return "deadline"
        seen = _seen()
        if len(_fresh_devices(base, seen)) >= len(_devices()):
            return "ready"
        # 关键设备失联：温度都没有，任何动作都是瞎开
        tdev = P.FB_SOURCES["t_now"]
        last = seen.get(tdev)
        if last is None and time.time() - _ST.started_ts > DEADLOCK_S:
            return "deadlock"
        if last is not None and time.time() - last > DEADLOCK_S:
            return "deadlock"
        if time.time() - t0 > ROUND_MAX_WAIT_S:
            return "timeout"
        _ST.stop_evt.wait(POLL_S)
    return "stop"


def _worker() -> None:
    st = _ST
    try:
        while not st.stop_evt.is_set():
            outcome = _wait_round()
            if outcome == "stop":
                break
            if outcome == "deadline":
                _finish("到达时限")
                return
            if outcome == "deadlock":
                _finish("当前温度上报中断（失联保护）")
                return

            # 消费掉这一轮的上报（下一轮重新计数）
            st.pending = _seen()
            if outcome == "timeout":
                _note(f"本轮有设备未反馈，用现有值继续（已等 {ROUND_MAX_WAIT_S:.0f} s）")

            # 节流：设备报得太密时合并
            gap = MIN_REPLAN_S - (time.time() - (st.plan_ts or 0.0))
            if gap > 0:
                if st.stop_evt.wait(gap):
                    break

            verdict = _tick()
            if verdict == "stop":
                return
    except Exception as e:                 # noqa: BLE001 —— 线程不能静默死掉
        with st.lock:
            st.last_error = f"闭环异常：{e}"
        _note(f"闭环异常：{e}")
        DL.write("loop", "闭环异常终止", [str(e)], extra={"rounds": st.rounds})
        _finish("闭环异常")
        return

    with st.lock:
        st.running = False
    _note("闭环线程退出")


def _tick() -> str:
    """一次「重解 + 下发」。返回 "ok" / "skip" / "stop"。"""
    st = _ST
    fb = get_feedback()
    src = fb.get("sources") or {}
    t_now = (src.get("t_now") or {}).get("value")
    tenv = (src.get("tenv") or {}).get("value")
    twater = (src.get("twater") or {}).get("value")

    with st.lock:
        st.t_now = None if t_now is None else float(t_now)
        st.tenv = None if tenv is None else float(tenv)
        st.twater = None if twater is None else float(twater)
        st.rounds += 1

    if t_now is None:
        st.last_error = "本轮没有当前温度读数，跳过重解"
        _note(st.last_error)
        return "skip"

    # 已经降到目标以下：模型没有加热能力，继续开只会过冷
    if float(t_now) <= st.t_target + P.TOL_K:
        _note(f"T={float(t_now):.2f} ℃ 已到达目标 {st.t_target:.2f} ℃，停止制冷")
        _finish("已到达目标温度")
        return "stop"

    remain = st.deadline - time.time()
    if remain <= TAIL_S:
        _note(f"剩余 {max(0.0, remain):.0f} s 不足 {TAIL_S:.0f} s，按收尾处理（保持当前动作到时限）")
        return "skip"

    try:
        plan = SV.get_plan(float(t_now), st.t_target, remain,
                           None if tenv is None else float(tenv),
                           None if twater is None else float(twater))
    except ValueError as e:
        with st.lock:
            st.rejects += 1
            st.last_error = f"重解被拒：{e}"
        _note(f"重解被拒（{st.rejects}/{MAX_REJECT}）：{e}")
        if st.rejects >= MAX_REJECT:
            _finish("重解连续被拒")
            return "stop"
        return "skip"

    seg = _first_seg(plan)
    with st.lock:
        st.rejects = 0
        st.replans += 1
        st.plan = plan.get("plan") or []
        st.plan_mode = plan.get("mode") or ""
        st.plan_ts = time.time()
        st.plan_t_s = float(t_now)
        cur = st.action
        same = (cur is not None
                and abs(float(cur.get("v_fan", -1)) - float(seg["v_fan"])) < 1e-9
                and abs(float(cur.get("i_tec", -1)) - float(seg["i_tec"])) < 1e-9
                and bool(st.last_send_ok))

    if same:
        _note(f"第 {st.rounds} 轮：T={float(t_now):.2f} ℃，最优动作仍是 "
              f"{seg['v_fan']:g} V / {seg['i_tec']:g} A，保持不重发")
        return "ok"

    res = SV.apply_step(seg["v_fan"], seg["i_tec"], hold_s=seg.get("duration_s"),
                        index=0, note=f"闭环第 {st.rounds} 轮重解下发")
    ok = bool(res.get("ok"))
    with st.lock:
        st.last_send_ok = ok
        if ok:
            st.sends += 1
            st.last_send_ts = time.time()
            st.action = {"v_fan": seg["v_fan"], "i_tec": seg["i_tec"],
                         "hold_s": seg.get("duration_s"), "since": time.time(),
                         "round": st.rounds}
            st.last_error = ""
        else:
            st.last_error = res.get("error") or res.get("message") or "下发失败"

    if ok:
        _note(f"第 {st.rounds} 轮：T={float(t_now):.2f} ℃，重解 → "
              f"{seg['v_fan']:g} V / {seg['i_tec']:g} A（{len(st.plan)} 段，"
              f"剩余 {remain/60:.1f} min）已下发")
    else:
        _note(f"第 {st.rounds} 轮下发失败：{st.last_error}")
        # 未启用 / 自检不过属于「不该继续动设备」的错误：立即停
        if "尚未启用" in st.last_error or "自检" in st.last_error:
            _finish("下发被安全闸拒绝")
            return "stop"
    return "ok"


def _finish(reason: str) -> None:
    """闭环收尾：归零、置状态、落日志。"""
    st = _ST
    with st.lock:
        st.running = False
        st.reason = reason
    st.stop_evt.set()
    _persist(False)

    try:
        res = SV.stop_output(reason=f"闭环结束：{reason}")
    except Exception as e:               # noqa: BLE001 —— 归零失败也要落状态，不能把线程带崩
        res = {"ok": False, "error": str(e)}
    _note(f"闭环结束（{reason}），两路输出归零"
          + ("" if res.get("ok") else f"（归零命令发布失败：{res.get('error')}，请到设备命令页核对）"))
    DL.write("loop", f"闭环结束：{reason}",
             [f"共 {st.rounds} 轮、重解 {st.replans} 次、下发 {st.sends} 次",
              "两路输出归零，等待下一次启动"],
             extra={"reason": reason, "rounds": st.rounds,
                    "replans": st.replans, "sends": st.sends})


__all__ = ["start", "stop", "status", "POLL_S", "MIN_REPLAN_S"]
