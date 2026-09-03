# -*- coding: utf-8 -*-
"""云端 Agent 客户端：MQTT cloud/# 推送解析（读）+ HTTP API（写），彻底替代 SSH。

数据链路（替代 box_console 里所有 _ssh_cloud_run）：
- 读：云端 cloud-agent 定时采集（kubectl/openssl/ss）→ 本地 mosquitto publish 到
  cloud/state、cloud/crds、cloud/logs 三个主题 → 本模块（由 mqtt_source 订阅线程
  调用 handle_push）更新内存缓存。请求路径只读缓存（毫秒级）；force=True 时直接
  HTTP GET agent 实时拉取（用于下发/删除后即时刷新）。
- 写：apply / delete / ingest 走 HTTP POST（Bearer token 认证），agent 本地执行 kubectl。
- 广播：云端状态/日志更新同时经 /api/ws/cloud WebSocket 推送给前端（实时订阅）。
- 配置：agent 连接信息存于 box_devices.json 顶层 cloud 字段
  （host / agent_port / agent_token / namespace）。

云端 agent 部署包见 platform/cloud-deploy/agent/（install_agent.sh 一键安装，deploy_cloud.sh --agent-only 可随云端一键部署）。
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import urllib.request
from collections import deque
from typing import Any, Dict, Optional, Set

_CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config")
_DEVICES_PATH = os.path.join(_CONFIG_DIR, "box_devices.json")
_BROKER_CFG_PATH = os.path.join(_CONFIG_DIR, "box_config.json")
_DEFAULT_HOST = "172.18.0.1"  # docker 网关: 平台容器与云端同机部署时经宿主回环访问 broker/agent
_DEFAULT_PORT = 42083

_LOCK = threading.Lock()

# 读数据缓存（来自云端 agent 的 MQTT 推送）
_CACHE: Dict[str, Any] = {
    "state": None,          # 概览（cloudcore/nodes/ports/certs/token）
    "state_ts": 0.0,
    "crds": None,           # CRD 列表（models + devices + twins）
    "crds_ts": 0.0,
    "logs_ring": deque(maxlen=300),
    "logs_cloudcore": None,
    "logs_ts": 0.0,
    "logs_error": "",
}
# 云端日志行去重（agent 已增量推送，平台侧再兜底去重）
_CLOUD_LOG_SEEN: "deque[str]" = deque(maxlen=300)

# WebSocket 广播订阅者（asyncio.Queue；同步线程 put_nowait 线程安全）
_WS_QUEUES: "Set[Any]" = set()
_WS_LOCK = threading.Lock()

# 缓存新鲜度 TTL（秒）：超过则视为「云端 agent 推送中断 / 数据过期」。
# 与 agent 推送间隔匹配（state 30s / crds 5s / logs 3s），取 3~4 倍余量。
_STATE_TTL = 120.0
_CRDS_TTL = 30.0
_LOGS_TTL = 15.0

def _is_fresh(kind: str) -> bool:
    """缓存是否新鲜（最近推送时间在 TTL 内）。"""
    ttl = {"state": _STATE_TTL, "crds": _CRDS_TTL, "logs": _LOGS_TTL}.get(kind, 60.0)
    with _LOCK:
        ts = _CACHE.get(f"{kind}_ts", 0.0)
    return bool(ts) and (time.time() - float(ts)) < ttl


# agent 连接配置读盘缓存：配置变更不频繁，避免每个请求重复读盘 + JSON 解析。
# 保存配置后调用 invalidate_cfg() 显式失效；即使未调用，TTL 兜底保证最终一致。
_CFG_TTL = 10.0
_cfg_cache: "Optional[Dict[str, Any]]" = None
_cfg_cache_ts = 0.0


def agent_cfg() -> Dict[str, Any]:
    """agent 连接配置：优先 box_devices.json cloud 字段，回退 broker host / 默认地址。"""
    global _cfg_cache, _cfg_cache_ts
    now = time.monotonic()
    if _cfg_cache is not None and now - _cfg_cache_ts < _CFG_TTL:
        return _cfg_cache
    cfg = _load_agent_cfg()
    _cfg_cache, _cfg_cache_ts = cfg, now
    return cfg


def invalidate_cfg() -> None:
    """使 agent 连接配置缓存失效（保存云端配置后调用，保证立即生效）。"""
    global _cfg_cache, _cfg_cache_ts
    _cfg_cache, _cfg_cache_ts = None, 0.0


def _load_agent_cfg() -> Dict[str, Any]:
    """读盘解析 agent 连接配置（仅由 agent_cfg 在缓存过期时调用）。"""
    host, port, token, namespace = "", _DEFAULT_PORT, "", "default"
    try:
        with open(_DEVICES_PATH, "r", encoding="utf-8") as f:
            c = (json.load(f) or {}).get("cloud") or {}
        host = str(c.get("host") or "").strip()
        if c.get("agent_port"):
            port = int(c["agent_port"])
        token = str(c.get("agent_token") or "").strip()
        namespace = str(c.get("namespace") or "default").strip()
    except Exception:  # noqa: BLE001
        pass
    if not host:
        try:
            with open(_BROKER_CFG_PATH, "r", encoding="utf-8") as f:
                bcfg = json.load(f) or {}
            host = str((bcfg.get("broker") or {}).get("host") or "").strip()
        except Exception:  # noqa: BLE001
            pass
    if not host:
        host = _DEFAULT_HOST
    return {"host": host, "agent_port": port, "agent_token": token, "namespace": namespace}


def _http(path: str, method: str = "GET", body: "Optional[Dict[str, Any]]" = None,
          timeout: int = 30) -> "tuple[bool, Optional[Dict[str, Any]], str]":
    """HTTP 调云端 agent，返回 (ok, json, error)。"""
    cfg = agent_cfg()
    host, port, token = cfg["host"], cfg["agent_port"], cfg["agent_token"]
    if not host or not token:
        return False, None, "云端 agent 未配置：请在「总览 → 配置」填写 agent_token（并确认 agent 端口）"
    url = f"http://{host}:{port}{path}"
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=timeout) as resp:
            return True, json.loads(resp.read().decode("utf-8", "replace")), ""
    except Exception as e:  # noqa: BLE001
        return False, None, f"云端 agent 不可达（{host}:{port}）：{e}"


# ------------------------- MQTT 推送解析（mqtt_source 订阅线程调用） -------------------------

def handle_push(topic: str, data: Dict[str, Any]) -> None:
    """收到 cloud/# 推送：更新对应缓存 + WebSocket 广播给前端。"""
    kind = topic.split("/", 1)[1] if "/" in topic else topic
    if not isinstance(data, dict):
        return
    ts = data.get("ts") or time.time()
    with _LOCK:
        if kind == "state":
            _CACHE["state"] = data
            _CACHE["state_ts"] = ts
        elif kind == "crds":
            _CACHE["crds"] = data
            _CACHE["crds_ts"] = ts
        elif kind == "logs":
            _CACHE["logs_ts"] = ts
            _CACHE["logs_error"] = str(data.get("error") or "")
            if data.get("cloudcore"):
                _CACHE["logs_cloudcore"] = data["cloudcore"]
            for line in data.get("lines") or []:
                if not line or line in _CLOUD_LOG_SEEN:
                    continue
                _CLOUD_LOG_SEEN.append(line)
                _CACHE["logs_ring"].append({"t": ts, "line": line})
    _broadcast(kind, data)


# ------------------------- 读（缓存优先，force 时 HTTP 实时拉取） -------------------------

def _mark_cached(cached: Dict[str, Any], ts: float) -> Dict[str, Any]:
    """给缓存数据附新鲜度元信息（不改原始数据），供上层判断云端推送是否中断。"""
    out = dict(cached)
    out["_cached"] = True
    out["_cache_ts"] = ts
    out["_cache_age"] = round(time.time() - float(ts), 1)
    out["_cache_fresh"] = (time.time() - float(ts)) < _STATE_TTL
    return out


# force 实时拉取节流：云端 agent 不可达时 HTTP 会同步阻塞 4~5s，若每个轮询请求都触发
# force（缓存为空时容易发生），会把 uvicorn 同步线程池占满导致平台整体卡死。因此 force
# 拉取最小间隔 30s：间隔内直接复用缓存/不可达结果，绝不为缓存重复做同步 HTTP。
_FORCE_MIN_INTERVAL = 30.0
_last_force_ts: Dict[str, float] = {"state": 0.0, "crds": 0.0}


def _force_allowed(kind: str) -> bool:
    """force 拉取是否放行（30s 节流）。返回 False 表示应直接返回缓存/不可达。"""
    now = time.time()
    with _LOCK:
        last = _last_force_ts.get(kind, 0.0)
        if now - last < _FORCE_MIN_INTERVAL:
            return False
        _last_force_ts[kind] = now
    return True


def state(force: bool = False) -> Dict[str, Any]:
    """云端概览状态：优先 MQTT 推送缓存；force=True 才 HTTP GET /api/state。

    非 force 且无缓存时直接返回不可达（不做同步 HTTP，避免轮询风暴阻塞线程池）。
    返回的缓存数据附带 _cache_ts/_cache_age/_cache_fresh，调用方据此区分
    「实时」「缓存已过期」（agent 推送中断、云端 broker 失联等），避免旧数据被当作 live。
    """
    if not force:
        with _LOCK:
            cached = _CACHE["state"]
            ts = _CACHE["state_ts"]
        if cached is not None:
            return _mark_cached(cached, ts)
        return {"ok": False,
                "error": "云端 agent 暂无缓存（MQTT 推送中断，云端 broker/agent 可能离线）",
                "cloudcore": None, "nodes": [], "ports": [], "certs": [], "token": None,
                "_cached": False, "_cache_ts": 0.0, "_cache_age": 0.0, "_cache_fresh": False}
    # force：30s 节流，避免云端不可达时每个请求都同步阻塞 HTTP
    if not _force_allowed("state"):
        with _LOCK:
            cached = _CACHE["state"]
            ts = _CACHE["state_ts"]
        if cached is not None:
            return _mark_cached(cached, ts)
        return {"ok": False,
                "error": "云端 agent 不可达（已节流，请稍后重试）",
                "cloudcore": None, "nodes": [], "ports": [], "certs": [], "token": None,
                "_cached": False, "_cache_ts": 0.0, "_cache_age": 0.0, "_cache_fresh": False}
    ok, data, err = _http("/api/state", timeout=4)
    if ok and data:
        with _LOCK:
            _CACHE["state"] = data
            _CACHE["state_ts"] = data.get("ts") or time.time()
        return _mark_cached(data, data.get("ts") or time.time())
    return {"ok": False, "error": err, "cloudcore": None, "nodes": [], "ports": [],
            "certs": [], "token": None,
            "_cached": False, "_cache_ts": 0.0, "_cache_age": 0.0, "_cache_fresh": False}


def crds(force: bool = False) -> Dict[str, Any]:
    """云端 CRD 列表（models + devices + twins）：优先 MQTT 推送缓存；force=True 实时拉取。

    非 force 且无缓存时直接返回不可达（不做同步 HTTP，避免轮询风暴阻塞线程池）。
    """
    if not force:
        with _LOCK:
            cached = _CACHE["crds"]
        if cached is not None:
            return cached
        return {"ok": False, "error": "云端 agent 暂无缓存（MQTT 推送中断，云端 broker/agent 可能离线）",
                "models": [], "devices": []}
    # force：30s 节流，避免云端不可达时每个请求都同步阻塞 HTTP
    if not _force_allowed("crds"):
        with _LOCK:
            cached = _CACHE["crds"]
        if cached is not None:
            return cached
        return {"ok": False, "error": "云端 agent 不可达（已节流，请稍后重试）",
                "models": [], "devices": []}
    ok, data, err = _http("/api/crds", timeout=5)
    if ok and data:
        with _LOCK:
            _CACHE["crds"] = data
            _CACHE["crds_ts"] = data.get("ts") or time.time()
        return data
    return {"ok": False, "error": err, "models": [], "devices": []}


def history(box: str = "", device: str = "", instance: str = "", prop: str = "",
            start: str = "", end: str = "", points: int = 500) -> Dict[str, Any]:
    """查询云端 TDengine 设备历史读数（GET /api/history，经 agent 通道）。

    需云端已部署时序库（deploy_cloud.sh --tsdb-only）且 collector 持续把
    data/{box}/{device}/{instance}/{property} 写入 nengtan.readings。
    返回 agent 按时间窗口降采样后的序列 [{t: 毫秒窗口起点, v: 均值}]。
    """
    if not box:
        return {"ok": False, "error": "box 必填"}
    q = urllib.parse.urlencode({"box": box, "device": device, "instance": instance,
                                "property": prop, "start": start, "end": end, "points": points})
    ok, data, err = _http(f"/api/history?{q}", timeout=15)
    if not ok:
        return {"ok": False, "error": err}
    if not isinstance(data, dict):
        return {"ok": False, "error": "agent 返回格式异常"}
    return data


def logs() -> Dict[str, Any]:
    """云端 CloudCore 实时日志（MQTT cloud/logs 增量推送累积的环形缓冲）。"""
    with _LOCK:
        return {
            "ok": bool(_CACHE["logs_cloudcore"]),
            "cloudcore": _CACHE["logs_cloudcore"],
            "error": _CACHE["logs_error"],
            "lines": [{"t": x["t"], "line": x["line"]} for x in _CACHE["logs_ring"]],
            "time": time.time(),
        }


def freshness() -> Dict[str, float]:
    """各通道数据新鲜度（最近推送时间，0 表示尚未收到推送）。"""
    with _LOCK:
        return {"state": _CACHE["state_ts"], "crds": _CACHE["crds_ts"], "logs": _CACHE["logs_ts"]}


def health() -> Dict[str, Any]:
    """agent 健康检查（HTTP /api/health），含配置信息与缓存新鲜度。"""
    cfg = agent_cfg()
    ok, data, err = _http("/api/health", timeout=5)
    out: Dict[str, Any] = {
        "ok": ok, "error": err,
        "config": {"host": cfg["host"], "agent_port": cfg["agent_port"],
                   "agent_token": cfg["agent_token"], "namespace": cfg["namespace"]},
        "version": (data or {}).get("version", "") if ok else "",
        "freshness": freshness(),
        "state_fresh": _is_fresh("state"),
    }
    return out


# ------------------------- 写（HTTP POST，agent 本地 kubectl） -------------------------

def apply(yaml_text: str) -> Dict[str, Any]:
    """下发 YAML：POST /api/apply → agent 本地 kubectl apply -f -。"""
    ok, data, err = _http("/api/apply", "POST", {"yaml": yaml_text}, timeout=150)
    if ok and data:
        return data
    return {"ok": False, "rc": 1, "stdout": "", "stderr": err}


def delete(kind: str, name: str, namespace: str) -> Dict[str, Any]:
    """删除云端 CRD：POST /api/delete → agent 本地 kubectl delete。"""
    ok, data, err = _http("/api/delete", "POST",
                          {"kind": kind, "name": name, "namespace": namespace}, timeout=60)
    if ok and data:
        return data
    return {"ok": False, "rc": 1, "stdout": "", "stderr": err, "deleted": []}


def ingest(device: str, namespace: str, property: str, value: Any) -> Dict[str, Any]:
    """回写单点 twins：POST /api/ingest → agent 本地 get→merge→patch。"""
    ok, data, err = _http("/api/ingest", "POST",
                          {"device": device, "namespace": namespace,
                           "property": property, "value": value}, timeout=90)
    if ok and data:
        return data
    return {"ok": False, "rc": 1, "stdout": "", "stderr": err}


def restart(kind: str = "deployment", name: str = "cloudcore",
            namespace: str = "kubeedge", edge: "Optional[Dict[str, Any]]" = None) -> Dict[str, Any]:
    """重启云端/边缘工作负载：POST /api/restart → agent 本地 kubectl/systemctl/SSH 执行。

    - kind=deployment/pod：kubectl rollout restart / delete pod（控制器自动重建）；
    - kind=systemd：systemctl restart 云端服务；
    - kind=edge：SSH 到边缘盒子 systemctl restart（edge 可携带盒子连接配置覆盖 agent 侧 config.json）。
    """
    body: Dict[str, Any] = {"kind": kind, "name": name, "namespace": namespace}
    if edge:
        body["edge"] = edge
    ok, data, err = _http("/api/restart", "POST", body, timeout=150)
    if ok and data:
        return data
    return {"ok": False, "rc": 1, "stdout": "", "stderr": err}


def get_edge_config() -> Dict[str, Any]:
    """读取云端 agent 上保存的边缘盒子连接配置（GET /api/edge/config）。"""
    ok, data, err = _http("/api/edge/config", "GET", timeout=15)
    if ok and data:
        return data
    return {"ok": False, "error": err}


def update_edge_config(p: Dict[str, Any]) -> Dict[str, Any]:
    """保存边缘盒子连接配置到云端 agent（POST /api/edge/config），返回连通性探测结果。"""
    body = {k: p.get(k) for k in ("host", "port", "user", "password", "key") if k in p}
    if not body:
        return {"ok": False, "error": "至少提供 host/port/user/password/key 中的一个字段"}
    ok, data, err = _http("/api/edge/config", "POST", body, timeout=20)
    if ok and data:
        return data
    return {"ok": False, "error": err}


def check_edge(host: str = "", port: int = 22) -> Dict[str, Any]:
    """探测边缘盒子 SSH 可达性（POST /api/edge/check，仅 TCP 探测不实际登录）。"""
    ok, data, err = _http("/api/edge/check", "POST", {"host": host, "port": port}, timeout=15)
    if ok and data:
        return data
    return {"ok": False, "reachable": False, "error": err}


def rootca() -> Dict[str, Any]:
    """拉取云端 rootCA.crt（base64），供盒子一键接入脚本内嵌，免除现场 scp。"""
    ok, data, err = _http("/api/rootca", "GET", timeout=15)
    if ok and data:
        return data
    return {"ok": False, "error": err}


def edge_run(cmd: str, timeout: int = 300,
             edge: "Optional[Dict[str, Any]]" = None) -> Dict[str, Any]:
    """远程在边缘盒子执行一条命令（POST /api/edge/run，一键接入脚本执行用）。"""
    body: Dict[str, Any] = {"cmd": cmd, "timeout": timeout}
    if edge:
        body["edge"] = edge
    ok, data, err = _http("/api/edge/run", "POST", body, timeout=min(timeout + 30, 950))
    if ok and data:
        return data
    return {"ok": False, "rc": 1, "stdout": "", "stderr": err}


def edge_upload(path: str, data_b64: str, mode: str = "0644",
                edge: "Optional[Dict[str, Any]]" = None) -> Dict[str, Any]:
    """上传文件到边缘盒子（POST /api/edge/upload，base64 传输，用于推送一键接入脚本）。"""
    body: Dict[str, Any] = {"path": path, "data": data_b64, "mode": mode}
    if edge:
        body["edge"] = edge
    ok, data, err = _http("/api/edge/upload", "POST", body, timeout=600)
    if ok and data:
        return data
    return {"ok": False, "rc": 1, "bytes": 0, "path": path, "stdout": "", "stderr": err}


# ------------------------- WebSocket 广播（/api/ws/cloud） -------------------------

def subscribe(q: Any) -> None:
    with _WS_LOCK:
        _WS_QUEUES.add(q)


def unsubscribe(q: Any) -> None:
    with _WS_LOCK:
        _WS_QUEUES.discard(q)


def _broadcast(kind: str, data: Dict[str, Any]) -> None:
    with _WS_LOCK:
        queues = list(_WS_QUEUES)
    if not queues:
        return
    payload = {"kind": kind, "data": data, "ts": time.time()}
    for q in queues:
        try:
            q.put_nowait(payload)
        except Exception:  # noqa: BLE001
            pass
