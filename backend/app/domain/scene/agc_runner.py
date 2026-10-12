"""AI 群控策略「服务端常驻运行器」。

需求口径：群控策略一旦点「运行」，只要没人手动停止就一直跑 —— 不能依赖浏览器是否打开、
也不能依赖用户停留在编排页。此前规则求值在前端画布组件里（定时器随组件卸载而消失），
关掉页面 / 换台电脑打开，策略就停了。

本模块把执行搬到服务端：

  · 运行态读 designs/agc.json 各场景的 ``running`` 字段（前端点启停时写入，服务端是真源）；
  · 按模型各自的 period 周期求值规则（执行语义与前端 utils/ruleFlow.js 的 evalFlowGraph 一致）；
  · 命中可调模块 → 经 MQTT ``cmd/{box}/cmd`` 下发写命令到现场盒子
    （同值保持期内不重发，避免每轮一次的命令风暴）；
  · 每轮结果进 RUNTIME，供前端画布高亮与「运行中」状态展示。

只执行「规则」模型；强化学习 / 粒子群的采样与训练依赖浏览器侧数据，仍由前端页面驱动。
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

from . import design_store

# MQTT 发布（每次新建短连接，线程安全）与实时读数缓存（读缓存必须持 _LOCK）
from ...mqtt_source import publish
from ...mqtt_source import _LOCK as _MQTT_LOCK
from ...mqtt_source import CLOUD_DEVICES
from ...mqtt_source import BOX_DEVICES_FILE

_TICK = 1.0            # 调度粒度：每秒检查一次「哪个模型到执行周期了」
_WRITE_KEEP = 30.0     # 下发成功后：同值 30s 内不重复下发
_WRITE_RETRY = 10.0    # 下发失败后：至少 10s 才重试

_AGC_LOCK = threading.RLock()
_LAST_WRITE: Dict[str, Dict[str, Any]] = {}   # "box|device|prop" -> {v, ts, ok}
_NEXT_AT: Dict[str, float] = {}               # modelId -> 下一次执行时刻
_STATE: Dict[str, Dict[str, Any]] = {}        # modelId -> 循环模块挂起轮次
_WAS: Dict[str, Any] = {}                     # 上一轮在跑的模型（用于检测停止 → 设定值归零）
_RUNTIME: Dict[str, Any] = {"ts": 0, "running": [], "last": {}, "zero": {}}

# 设备名 -> 所属盒子（CLOUD_DEVICES 未上报时的兜底，配置文件带 mtime 缓存）
_DEV_NODE = {"mtime": 0, "map": {}}


# ══════════════ 规则图求值（与前端 utils/ruleFlow.js 同源） ══════════════

def _flow_path(graph: Dict[str, Any]) -> Dict[str, Any]:
    """通路分析：只有「开始 → … → 结束」通路上的模块才会被执行。"""
    nodes = [n for n in ((graph or {}).get("nodes") or []) if isinstance(n, dict) and n.get("id")]
    edges = [e for e in ((graph or {}).get("edges") or []) if isinstance(e, dict)]
    by_id = {n["id"] for n in nodes}
    out: Dict[str, List[str]] = {}
    inn: Dict[str, List[str]] = {}
    for e in edges:
        f, t = e.get("from"), e.get("to")
        if f not in by_id or t not in by_id:
            continue
        out.setdefault(f, [])
        if t not in out[f]:
            out[f].append(t)
        inn.setdefault(t, [])
        if f not in inn[t]:
            inn[t].append(f)

    def walk(seeds, nxt):
        seen = set()
        st = list(seeds)
        while st:
            i = st.pop()
            if i in seen:
                continue
            seen.add(i)
            for j in nxt.get(i) or []:
                if j not in seen:
                    st.append(j)
        return seen

    starts = [n["id"] for n in nodes if n.get("kind") == "start"]
    ends = [n["id"] for n in nodes if n.get("kind") == "end"]
    fwd = walk(starts, out)
    rev = walk(ends, inn)
    live = {i for i in fwd if i in rev}
    return {"starts": starts, "ends": ends, "live": live, "ok": any(e in fwd for e in ends)}


def _cmp(a, op, b) -> bool:
    try:
        x = float(a)
        y = float(b)
    except (TypeError, ValueError):
        return False
    if op == ">":
        return x > y
    if op == ">=":
        return x >= y
    if op == "<":
        return x < y
    if op == "<=":
        return x <= y
    if op == "==":
        return abs(x - y) < 1e-9
    if op == "!=":
        return abs(x - y) >= 1e-9
    return False


def _loop_times(n) -> int:
    try:
        v = int(round(float(n.get("times"))))
    except (TypeError, ValueError):
        return 1
    return max(1, min(999, v))


def _loop_gap(n) -> float:
    try:
        v = float(n.get("gap"))
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(3600.0, v))


def _eval_graph(graph, live_of, state) -> Dict[str, Any]:
    """执行一遍规则图；返回 { ok, acts, nodes, edges, branch }。

    acts 是结构化结果（前端据此生成文案，避免服务端写死中文）：
      { kind: 'adj'|'sen'|'gate'|'loop', write, nodeId, devId, value?, hit? }
    """
    nodes = [n for n in ((graph or {}).get("nodes") or []) if isinstance(n, dict) and n.get("id")]
    edges = [e for e in ((graph or {}).get("edges") or []) if isinstance(e, dict)]
    fp = _flow_path(graph)
    acts: List[Dict[str, Any]] = []
    an = set()
    ae = set()
    branch = ""
    pend = state.setdefault("pend", [])
    if not fp["ok"]:
        state["pend"] = []
        return {"ok": False, "acts": [], "nodes": [], "edges": [], "branch": ""}
    nmap = {n["id"]: n for n in nodes}

    def on_branch(v):
        nonlocal branch
        if not branch:
            branch = v

    def src_of(n, b):
        """分支判定来源：显式指定 > 上游连线"""
        if b and b.get("src"):
            x = nmap.get(b.get("src"))
            if x and x.get("kind") != "if":
                return x
        e = next((x for x in edges if x.get("to") == n.get("id")), None)
        if not e:
            return None
        s = nmap.get(e.get("from"))
        return s if (s and s.get("kind") != "if") else None

    def advance(e, depth, visited):
        if depth > 24:
            return
        tgt = nmap.get(e.get("to"))
        tid = (tgt or {}).get("id")
        if not tgt or tid not in fp["live"]:
            return
        ae.add(e.get("id"))
        an.add(tid)
        kind = tgt.get("kind")
        if kind == "end":
            return
        if kind == "if":
            eval_if(tgt, depth, visited)
            return
        if kind == "gate":
            eval_gate(tgt, depth, visited)
            return
        if kind == "loop":
            eval_loop(tgt, depth, visited)
            return
        if kind not in ("adj", "sen"):
            return
        if kind == "adj":
            try:
                v = float(tgt.get("value"))
            except (TypeError, ValueError):
                v = None
            if v is not None:
                acts.append({"kind": "adj", "write": True, "nodeId": tid, "devId": tgt.get("devId"), "value": v})
        else:
            acts.append({"kind": "sen", "write": False, "nodeId": tid, "devId": tgt.get("devId")})
        for nx in [x for x in edges if x.get("from") == tid]:
            advance(nx, depth + 1, visited)

    def eval_if(n, depth, visited):
        if depth > 8 or n.get("id") in visited:
            return
        visited.add(n.get("id"))
        hit = None
        for b in n.get("branches") or []:
            if not isinstance(b, dict) or b.get("type") == "else":
                continue
            s = src_of(n, b)
            v = live_of(s.get("devId")) if s else None
            if v is not None and _cmp(v, b.get("op"), b.get("val")):
                hit = b
                break
        if hit is None:
            hit = next((b for b in (n.get("branches") or []) if isinstance(b, dict) and b.get("type") == "else"), None)
        if hit is None:
            return
        on_branch("%s:%s" % (n.get("id"), hit.get("id")))
        for e in [x for x in edges if x.get("from") == n.get("id") and x.get("port") == hit.get("id")]:
            advance(e, depth, visited)

    def eval_gate(n, depth, visited):
        if depth > 8 or n.get("id") in visited:
            return
        visited.add(n.get("id"))
        is_or = n.get("op") == "or"
        ok = not is_or
        any_v = False
        for c in n.get("conds") or []:
            if not isinstance(c, dict):
                continue
            s = src_of(n, c) if not c.get("src") else nmap.get(c.get("src"))
            if s and (s.get("kind") == "gate" or s.get("kind") == "if"):
                s = src_of(n, c)
            v = live_of(s.get("devId")) if s else None
            if v is None:
                continue
            try:
                float(c.get("val"))
            except (TypeError, ValueError):
                continue
            any_v = True
            r = _cmp(v, c.get("op"), c.get("val"))
            if is_or:
                if r:
                    ok = True
                    break
            elif not r:
                ok = False
                break
        hit = "t" if (ok and any_v) else "f"
        on_branch("%s:%s" % (n.get("id"), hit))
        acts.append({"kind": "gate", "write": False, "nodeId": n.get("id"), "hit": hit})
        for e in [x for x in edges if x.get("from") == n.get("id") and x.get("port") == hit]:
            advance(e, depth, visited)

    def eval_loop(n, depth, visited):
        if depth > 8 or n.get("id") in visited:
            return
        times = _loop_times(n)
        gap = _loop_gap(n)
        seal = set(visited)
        seal.add(n.get("id"))
        state["pend"] = [q for q in state.get("pend") or [] if q.get("nodeId") != n.get("id")]
        for i in range(1, times + 1):
            if i > 1 and gap > 0:
                state["pend"].append({"at": time.time() + gap, "nodeId": n.get("id"), "round": i, "total": times, "gap": gap})
                break
            acts.append({"kind": "loop", "write": False, "nodeId": n.get("id"), "round": i, "total": times})
            for e in [x for x in edges if x.get("from") == n.get("id")]:
                advance(e, depth + 1, set(seal))

    # ① 到期的挂起轮次（循环模块「每轮间隔 > 0」时排在之后的 tick 执行）
    now = time.time()
    due = [q for q in (state.get("pend") or []) if float(q.get("at") or 0) <= now]
    state["pend"] = [q for q in (state.get("pend") or []) if float(q.get("at") or 0) > now]
    for q in due:
        n = nmap.get(q.get("nodeId"))
        if not n or n.get("id") not in fp["live"]:
            continue
        an.add(n.get("id"))
        acts.append({"kind": "loop", "write": False, "nodeId": n.get("id"), "round": q.get("round"), "total": q.get("total")})
        for e in [x for x in edges if x.get("from") == n.get("id")]:
            advance(e, 1, {n.get("id")})
        if int(q.get("round") or 0) < int(q.get("total") or 0):
            state["pend"].append({**q, "at": time.time() + float(q.get("gap") or 0), "round": int(q.get("round") or 0) + 1})

    # ② 主流程：从每个「开始」沿通路推进
    visited = set()
    for sid in fp["starts"]:
        an.add(sid)
        for e in [x for x in edges if x.get("from") == sid]:
            advance(e, 0, visited)

    return {"ok": True, "acts": acts, "nodes": sorted(an), "edges": sorted(x for x in ae if x), "branch": branch}


# ══════════════ 读数 / 绑定 / 下发 ══════════════

def _attach_of(scene: str, ext_id: str) -> Optional[Dict[str, Any]]:
    """ext::节点id::附加设备uid → 附加设备定义（来自 flow 桶的 scheme）。"""
    if not ext_id or not str(ext_id).startswith("ext::"):
        return None
    parts = str(ext_id).split("::")
    if len(parts) != 3:
        return None
    node_id, att_uid = parts[1], parts[2]
    try:
        raw = design_store.read_scene("flow", scene) or {}
        # flow 桶存的是 { sceneId, scheme, deviceSetpoints, ... }，图在 scheme 里
        scheme = raw.get("scheme") if isinstance(raw, dict) else None
        if not isinstance(scheme, dict):
            scheme = raw
    except Exception:
        return None
    for n in scheme.get("nodes") or []:
        if not isinstance(n, dict) or n.get("id") != node_id:
            continue
        for a in n.get("attached") or []:
            if isinstance(a, dict) and a.get("uid") == att_uid:
                return a
    return None


def _field_of(dev: str, prop: str):
    """取某设备点位的最新上报值与所属盒子：(value, box)。"""
    if not dev:
        return None, ""
    with _MQTT_LOCK:
        cd = CLOUD_DEVICES.get(dev) or {}
        fields = cd.get("fields") or {}
        box = cd.get("box") or ""
        v = fields.get(prop)
        if v is None:
            lp = str(prop or "").lower()
            for k, val in fields.items():
                if str(k).lower() == lp:
                    v = val
                    break
    try:
        return (None if v is None else float(v)), box
    except (TypeError, ValueError):
        return None, box


def _box_of_device(dev: str) -> str:
    """设备所属盒子（盒子配置文件兜底，带 mtime 缓存）。"""
    global _DEV_NODE
    try:
        mt = os.path.getmtime(BOX_DEVICES_FILE)
        if mt != _DEV_NODE["mtime"]:
            with open(BOX_DEVICES_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f) or {}
            mp = {}
            for d in cfg.get("devices") or []:
                if isinstance(d, dict) and d.get("name"):
                    mp[d["name"]] = d.get("node") or ""
            _DEV_NODE = {"mtime": mt, "map": mp}
        return _DEV_NODE["map"].get(dev) or ""
    except Exception:
        return ""


def _live_of(dev_id: str, scene: str):
    """规则里的「读数」：ext:: 按绑定取点位值 × factor；普通设备取主读数。"""
    if not dev_id:
        return None
    if str(dev_id).startswith("ext::"):
        att = _attach_of(scene, dev_id)
        if not att:
            return None
        src = att.get("src") or ""
        if src == "device":
            v, _box = _field_of(att.get("device"), att.get("prop"))
            if v is None:
                return None
            try:
                return v * float(att.get("factor") or 1)
            except (TypeError, ValueError):
                return v
        # fixed / sim / param：取编排里写死的缺省值；attach（跟随别的目标）暂按缺省值处理
        try:
            return float(att.get("def"))
        except (TypeError, ValueError):
            return None
    with _MQTT_LOCK:
        cd = CLOUD_DEVICES.get(dev_id) or {}
        v = cd.get("primary")
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _bound_of(dev_id: str, scene: str) -> Optional[Dict[str, Any]]:
    """可调设备的写入去向：{ device, prop, box }；未绑定数据源可写点位返回 None（只改平台内部值）。"""
    if not dev_id or not str(dev_id).startswith("ext::"):
        return None
    att = _attach_of(scene, dev_id)
    if not att or (att.get("src") or "") != "device":
        return None
    dev, prop = att.get("device"), att.get("prop")
    if not dev or not prop:
        return None
    _v, box = _field_of(dev, prop)
    if not box:
        box = _box_of_device(dev)
    return {"device": dev, "prop": prop, "box": box} if box else None


def _write_point(bound: Dict[str, Any], value, model_id: str):
    """下发写命令（同值保持期内不重发）；返回 (ok, err)。"""
    box, dev, prop = bound.get("box"), bound.get("device"), bound.get("prop")
    if not (box and dev and prop):
        return False, "缺少下发目标"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False, "设定值非法"
    key = "%s|%s|%s" % (box, dev, prop)
    now = time.time()
    last = _LAST_WRITE.get(key)
    if last and abs(float(last.get("v") or 0) - v) < 1e-9:
        keep = _WRITE_KEEP if last.get("ok") else _WRITE_RETRY
        if now - float(last.get("ts") or 0) < keep:
            return True, ""      # 保持期内：不发，也不算失败
    payload = {
        "box": box, "device": dev, "cmd": "write", "property": prop,
        "value": v, "request_id": "agc-%s-%d" % (model_id or "m", int(now * 1000)), "ts": now,
    }
    try:
        res = publish("cmd/%s/cmd" % box, payload)
    except Exception as e:      # 单条下发异常不影响运行器继续
        res = {"ok": False, "error": str(e)}
    ok = bool((res or {}).get("ok"))
    _LAST_WRITE[key] = {"v": v, "ts": now, "ok": ok}
    return ok, "" if ok else str((res or {}).get("error") or "下发失败")


# ══════════════ 调度 ══════════════

def _adj_dev_ids(model: Dict[str, Any]) -> List[str]:
    """规则里所有「可调模块」的设定值目标（停止归零的范围）。"""
    out = []
    for n in ((model.get("graph") or {}).get("nodes") or []):
        if not isinstance(n, dict) or n.get("kind") != "adj":
            continue
        d = n.get("devId")
        if d and d not in out:
            out.append(d)
    return out


def _zero_model(scene: str, model: Dict[str, Any], now: float) -> None:
    """停止时的归零：流程里所有可调模块的设定值写 0（并下发，让现场设备真正停下）。

    不只看本轮命中的模块 —— 停止后不应该留残余设定值。
    """
    mid = model.get("id")
    errs = []
    done = []
    for dev_id in _adj_dev_ids(model):
        b = _bound_of(dev_id, scene)
        if not b:
            continue      # 未绑定数据源可写点位：只在平台内部归零，由前端处理
        ok, err = _write_point(b, 0.0, mid)
        done.append("%s.%s" % (b.get("device"), b.get("prop")))
        if not ok and err:
            errs.append("%s.%s %s" % (b.get("device"), b.get("prop"), err))
    with _AGC_LOCK:
        _RUNTIME["zero"][mid] = {"ts": now, "devs": _adj_dev_ids(model), "written": done, "err": errs[-3:]}


def _run_once(scene: str, model: Dict[str, Any], now: float) -> None:
    mid = model.get("id")
    st = _STATE.setdefault(mid, {"pend": []})
    r = _eval_graph(model.get("graph") or {}, lambda dev: _live_of(dev, scene), st)
    errs = []
    for a in r["acts"]:
        if not a.get("write"):
            continue
        b = _bound_of(a.get("devId"), scene)
        if not b:
            continue
        ok, err = _write_point(b, a.get("value"), mid)
        if not ok and err:
            errs.append("%s.%s %s" % (b.get("device"), b.get("prop"), err))
    with _AGC_LOCK:
        _RUNTIME["last"][mid] = {
            "ts": now, "ok": r["ok"], "acts": r["acts"], "nodes": r["nodes"],
            "edges": r["edges"], "branch": r["branch"], "err": errs[-3:],
        }


def _tick() -> None:
    try:
        buckets = design_store.read_bucket("agc") or {}
    except Exception:
        return
    now = time.time()
    running: List[Dict[str, Any]] = []
    seen: Dict[str, Any] = {}
    for scene, payload in buckets.items():
        if not isinstance(payload, dict):
            continue
        models = {m.get("id"): m for m in (payload.get("designs") or []) if isinstance(m, dict) and m.get("id")}
        rlist = payload.get("running") or []
        if isinstance(rlist, str):
            rlist = [rlist]
        for mid in rlist:
            m = models.get(mid)
            if not m:
                continue
            seen[mid] = (scene, m)
            running.append({"scene": scene, "id": mid, "name": m.get("name") or mid, "alg": m.get("alg") or "rule"})
            if (m.get("alg") or "rule") != "rule":
                continue
            at = _NEXT_AT.get(mid)
            if at and now < at:
                continue
            _NEXT_AT[mid] = now + max(1.0, float(m.get("period") or 2))
            try:
                _run_once(scene, m, now)
            except Exception as _e:      # 单轮异常不能让运行器退出
                with _AGC_LOCK:
                    _RUNTIME["last"][mid] = {"ts": now, "ok": False, "acts": [], "nodes": [], "edges": [], "branch": "", "err": [str(_e)]}
    # 停止检测：上一轮还在跑、这一轮不在了 → 流程里所有设定值归零
    # （不管停止是从哪一端发起的：点「停止」、换端停、直接改存档都一样处理）
    for mid, (sc, m) in list(_WAS.items()):
        if mid in seen:
            continue
        _WAS.pop(mid, None)
        if (m.get("alg") or "rule") != "rule":
            continue
        try:
            _zero_model(sc, m, now)
        except Exception as _e:      # 归零失败不能让运行器退出
            with _AGC_LOCK:
                _RUNTIME["zero"][mid] = {"ts": now, "devs": _adj_dev_ids(m), "written": [], "err": [str(_e)]}
    _WAS.update(seen)
    with _AGC_LOCK:
        alive = {r["id"] for r in running}
        for k in list(_RUNTIME["last"].keys()):
            if k not in alive:
                _RUNTIME["last"].pop(k, None)
        for k in list(_STATE.keys()):
            if k not in alive:
                _STATE.pop(k, None)
        for k in list(_NEXT_AT.keys()):
            if k not in alive:
                _NEXT_AT.pop(k, None)
        _RUNTIME["ts"] = now
        _RUNTIME["running"] = running


class AgcRunner:
    """每 _TICK 秒调度一次的常驻线程（范式同 domain/sim/optimizers.TrainingScheduler）。"""

    def __init__(self, wake: float = _TICK):
        self.wake = wake
        self._t: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._t and self._t.is_alive():
            return
        self._stop.clear()
        self._t = threading.Thread(target=self._loop, name="agc-runner", daemon=True)
        self._t.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(self.wake)
            if self._stop.is_set():
                break
            try:
                _tick()
            except Exception:
                pass


runner = AgcRunner()


def start() -> None:
    runner.start()


def stop() -> None:
    runner.stop()


def runtime() -> Dict[str, Any]:
    """供前端查询：运行器是否在线、哪些模型在运行、每个模型最近一轮的执行结果。"""
    with _AGC_LOCK:
        return {
            "ok": True,
            "online": bool(runner._t and runner._t.is_alive()),
            "ts": _RUNTIME.get("ts") or 0,
            "running": [dict(r) for r in (_RUNTIME.get("running") or [])],
            "last": json.loads(json.dumps(_RUNTIME.get("last") or {})),
            # 停止时归零的结果：modelId -> { ts, devs, written, err }（前端据此把界面上的设定值也置 0）
            "zero": json.loads(json.dumps(_RUNTIME.get("zero") or {})),
        }
