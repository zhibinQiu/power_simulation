#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""能碳一体机云端 Agent —— 替代「平台 SSH 到云端执行 kubectl」的数据通道。

架构（部署于云端 K3s 主机，systemd 常驻，见 install_agent.sh）：
- 读：agent 定时本地采集（kubectl / openssl / ss / 证书路径）→ 通过本地 mosquitto
  publish 到 cloud/state、cloud/crds、cloud/logs 三个主题；平台已长连云端 Broker
  订阅 #，毫秒级收到推送，全程无轮询、无 SSH。
- 写：平台 HTTP POST 到 agent（/api/apply /api/delete /api/ingest /api/restart），agent 本地
  执行 kubectl apply/delete/patch/rollout（无需 SSH、不暴露 root 凭据）。
- 重启：/api/restart 支持 kind=deployment/pod（kubectl 重启云端工作负载）、
  kind=systemd（systemctl 重启云端服务，如 cloud-agent / nengtan-cloud-broker）、
  kind=edge（SSH 到边缘盒子 systemctl 重启 box-mapper / edgecore 等，凭据见 config.json 的 edge 字段）。

零第三方依赖：Python 标准库（http.server / subprocess）+ 系统命令
（kubectl / openssl / ss / mosquitto_pub / ssh / sshpass（可选））。

配置：/opt/cloud-agent/config.json（由 install_agent.sh 生成），示例：
{
  "http_port": 42083,
  "token": "<Bearer token，平台侧需一致>",
  "broker_host": "127.0.0.1",
  "broker_port": 41883,
  "broker_username": "",
  "broker_password": "",
  "intervals": {"state": 30, "crds": 5, "logs": 3},
  "edge": {
    "host": "",          // 边缘盒子可达地址（重启 box-mapper 等边缘服务用，SSH 可达即可；
                         //   现场内网/跳板机地址；盒子无直达 IP 时此功能不可用，需现场运维）
    "port": 22,
    "user": "root",
    "password": "",      // 密码方式（需安装 sshpass）；与 key 二选一
    "key": ""            // 密钥方式（绝对路径，如 /root/.ssh/id_rsa）
  }
}
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional

CONFIG_PATH = "/opt/cloud-agent/config.json"
DEFAULT_CONFIG: Dict[str, Any] = {
    "http_port": 42083,
    "token": "",
    "broker_host": "127.0.0.1",
    "broker_port": 41883,
    "broker_username": "",
    "broker_password": "",
    "intervals": {"state": 30, "crds": 5, "logs": 3},
    "edge": {"host": "", "port": 22, "user": "root", "password": "", "key": ""},
    "tdengine": {"url": "http://127.0.0.1:6041", "user": "root", "password": "taosdata", "db": "nengtan"},
}

# systemctl 重启白名单（云端 systemd 服务）
_SYSTEMD_ALLOW = {"cloud-agent", "nengtan-cloud-broker", "nengtan-collector", "nengtan-cloud-dashboard"}

# 边缘盒子 systemd 服务白名单（经 SSH 重启）
_EDGE_UNIT_ALLOW = {"box-mapper", "edgecore", "box-collector"}

_K8S_NAME_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$")

# CloudCore 日志行去重（增量推送，平台侧追加到环形缓冲）
_LOG_SEEN: "deque[str]" = deque(maxlen=200)


def log(msg: str) -> None:
    print(f"[cloud-agent] {msg}", flush=True)


def load_config() -> Dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        for k in ("http_port", "token", "broker_host", "broker_port",
                  "broker_username", "broker_password", "intervals", "edge", "tdengine"):
            if k in data:
                cfg[k] = data[k]
    except Exception as e:  # noqa: BLE001
        log(f"config 加载失败（{e}），使用默认值")
    return cfg


_CFG = load_config()


# ------------------------- 本地命令执行（kubectl / openssl / ss） -------------------------

def _run(cmd: str, stdin_data: Optional[str] = None, timeout: int = 90) -> "tuple[bool, str, str]":
    """本地执行一条 shell 命令，返回 (ok, stdout, stderr)。stdin_data 用于 kubectl apply/patch。"""
    try:
        proc = subprocess.run(
            ["bash", "-c", cmd], input=stdin_data,
            capture_output=True, text=True, timeout=timeout,
        )
    except Exception as e:  # noqa: BLE001
        return False, "", f"命令执行失败：{e}"
    if proc.returncode != 0:
        return False, proc.stdout, (proc.stderr or "").strip() or f"rc={proc.returncode}"
    return True, proc.stdout, ""


def _run_bin(cmd: str, stdin_bytes: bytes, timeout: int = 180) -> "tuple[bool, str, str]":
    """二进制 stdin 执行一条 shell 命令（用于 SSH 上传文件等），返回 (ok, stdout, stderr)。"""
    try:
        proc = subprocess.run(
            ["bash", "-c", cmd], input=stdin_bytes,
            capture_output=True, timeout=timeout,
        )
        out = proc.stdout.decode("utf-8", "replace")
        err = proc.stderr.decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return False, "", f"命令执行失败：{e}"
    if proc.returncode != 0:
        return False, out, err.strip() or f"rc={proc.returncode}"
    return True, out, ""


def _split_sections(stdout: str) -> Dict[str, str]:
    """把 `==SECTION==` 多段文本切分为 {段名: 内容}。"""
    sections: Dict[str, str] = {}
    cur = None
    for line in stdout.splitlines():
        if line.startswith("=="):
            cur = line.strip("= ").strip()
            sections[cur] = ""
        elif cur:
            sections[cur] += line + "\n"
    return sections


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _mint_long_token(ca_hash: str, key_der_b64: str, days: int = 365) -> "Optional[Dict[str, Any]]":
    """用云端 CA 私钥重签 1 年长期共享 token（KubeEdge 四段式 caHash.header.payload.signature）。"""
    try:
        der = base64.b64decode(key_der_b64)
        now = int(time.time())
        header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode("utf-8"))
        payload = _b64url(json.dumps({"exp": now + days * 86400}, separators=(",", ":")).encode("utf-8"))
        sig = _b64url(hmac.new(der, f"{header}.{payload}".encode("ascii"), hashlib.sha256).digest())
        exp = datetime.fromtimestamp(now + days * 86400, tz=timezone.utc)
        return {
            "value": f"{ca_hash}.{header}.{payload}.{sig}",
            "source": "mint",
            "expires": exp.strftime("%Y-%m-%d"),
            "remain_days": str(days),
        }
    except Exception:  # noqa: BLE001
        return None


# ------------------------- 采集：概览（cloudcore / 节点 / 端口 / 证书 / token） -------------------------

_STATE_QUERY = (
    "echo '==POD=='; kubectl get pod -n kubeedge --no-headers -o custom-columns=NAME:.metadata.name,READY:.status.containerStatuses[0].ready,PHASE:.status.phase,RESTARTS:.status.containerStatuses[0].restartCount,AGE:.metadata.creationTimestamp,PODIP:.status.podIP,NODE:.spec.nodeName 2>/dev/null | grep -i cloudcore || echo NO_POD;"
    "echo '==NODES=='; kubectl get nodes -o wide 2>/dev/null || echo NO_NODES;"
    "echo '==PORTS=='; ss -tlnup 2>/dev/null | grep -E ':(1000[0-4])[^0-9]' | head -20;"
    "echo '==CERTS=='; for f in /etc/kubeedge/ca/*.crt /etc/kubeedge/certs/*.crt; do"
    " [ -f \"$f\" ] && echo \"$f :: $(openssl x509 -enddate -noout -in \"$f\" 2>/dev/null)\"; done;"
    "echo '==CAHASH=='; openssl x509 -in /etc/kubeedge/ca/rootCA.crt -outform DER 2>/dev/null | openssl sha256;"
    "echo '==CAKEYDER=='; openssl pkey -in /etc/kubeedge/ca/rootCA.key -outform DER 2>/dev/null | base64 -w0;"
    "echo '==TOKENSECRET=='; kubectl -n kubeedge get secret tokensecret -o jsonpath='{.data.tokendata}' 2>/dev/null | base64 -d"
)


def collect_state() -> Dict[str, Any]:
    """本地采集云端 K3s/KubeEdge 概览状态，返回与平台 box_overview 兼容的结构。"""
    out: Dict[str, Any] = {
        "ok": False, "error": "采集失败",
        "cloudcore": None, "nodes": [], "ports": [], "certs": [], "token": None,
    }
    ok, stdout, stderr = _run(_STATE_QUERY, timeout=45)
    if not ok:
        out["error"] = f"云端采集失败：{stderr or stdout or 'timeout'}"
        return out
    sections = _split_sections(stdout)

    for line in sections.get("POD", "").splitlines():
        p = line.split()
        if len(p) >= 7 and p[0] != "NAME":
            out["cloudcore"] = {
                "name": p[0], "ready": "1/1" if p[1].lower() == "true" else "0/1",
                "phase": p[2], "restarts": p[3], "age": p[4], "podIP": p[5], "node": p[6],
                "available": p[2] == "Running",
            }
            break

    for line in sections.get("NODES", "").splitlines():
        p = line.split()
        if len(p) < 5 or p[0] == "NAME":
            continue
        out["nodes"].append({
            "name": p[0], "ready": p[1] == "Ready", "roles": p[2],
            "age": p[3], "version": p[4],
            "internalIP": p[5] if len(p) > 5 else "",
            "is_edge": "edge" in p[2].lower(), "source": "k8s", "devices": 0,
        })

    for line in sections.get("PORTS", "").splitlines():
        p = line.split()
        if len(p) < 4:
            continue
        try:
            port = int(p[3].rsplit(":", 1)[-1])
        except ValueError:
            continue
        m = re.search(r'users:\(\("([^"]+)', line)
        out["ports"].append({
            "port": str(port), "proto": p[0].upper(),
            "svc": m.group(1) if m else "cloudcore", "listening": "yes",
        })
    out["ports"].sort(key=lambda x: int(x["port"]))

    for line in sections.get("CERTS", "").splitlines():
        if "::" not in line or "notAfter=" not in line:
            continue
        path, _, end = line.partition("::")
        try:
            raw = end.split("notAfter=", 1)[1].strip().replace(" GMT", "")
            exp = datetime.strptime(raw, "%b %d %H:%M:%S %Y").replace(tzinfo=timezone.utc)
        except ValueError:
            exp = None
        remain = (exp - datetime.now(timezone.utc)).days if exp else None
        out["certs"].append({
            "cn": os.path.basename(path.strip()),
            "expires": exp.strftime("%Y-%m-%d") if exp else "未知",
            "remain_days": str(remain) if remain is not None else "—",
        })
    if not out["certs"]:
        out["certs"] = [{"cn": c, "expires": "云端未找到（路径可能不同）", "remain_days": "—"}
                        for c in ("rootCA.crt", "cloudcore.crt", "stream.crt")]

    tok = sections.get("TOKENSECRET", "").strip()
    ca_hash = ""
    for ln in sections.get("CAHASH", "").splitlines():
        if ln.strip() and "=" in ln:
            ca_hash = ln.split("=", 1)[-1].strip()
    key_der_b64 = sections.get("CAKEYDER", "").strip()
    tok_data = _mint_long_token(ca_hash, key_der_b64) if (ca_hash and key_der_b64) else None
    if not tok_data and tok:
        tok_data = {"value": tok, "source": "tokensecret",
                    "expires": "云端 tokensecret（cloudcore 重启后约 24 小时有效）", "remain_days": "—"}
    if tok_data:
        out["token"] = tok_data
    else:
        out["token"] = {"value": "", "expires": "云端未获取到 token（tokensecret / CA 材料缺失）", "remain_days": "—"}

    out["ok"] = True
    out["error"] = ""
    return out


# ------------------------- 采集：CRD（DeviceModel / Device + twins） -------------------------

_CRD_QUERY = (
    "echo '==MODELS=='; kubectl get devicemodels -A -o json 2>/dev/null;"
    "echo '==DEVICES=='; kubectl get devices -A -o json 2>/dev/null"
)


def collect_crds() -> Dict[str, Any]:
    """本地读取 DeviceModel / Device CRD（含 twins 摘要），结构与平台 cloud_crds 一致。"""
    out: Dict[str, Any] = {"ok": False, "error": "采集失败", "models": [], "devices": []}
    ok, stdout, stderr = _run(_CRD_QUERY, timeout=45)
    if not ok:
        out["error"] = f"云端采集失败：{stderr or stdout or 'timeout'}"
        return out
    sections = _split_sections(stdout)
    errors: List[str] = []

    try:
        mraw = sections.get("MODELS", "").strip()
        mjson = json.loads(mraw) if mraw else {"items": []}
        for m in mjson.get("items", []):
            meta = m.get("metadata", {}) or {}
            spec = m.get("spec", {}) or {}
            props = spec.get("properties", []) or []
            out["models"].append({
                "name": meta.get("name", ""),
                "namespace": meta.get("namespace", "default"),
                "protocol": "",
                "property_count": len(props),
                "properties": [p.get("name", "") for p in props],
                "source": "cloud",
            })
    except Exception as e:  # noqa: BLE001
        errors.append(f"解析 DeviceModel 失败：{e}")

    try:
        draw = sections.get("DEVICES", "").strip()
        djson = json.loads(draw) if draw else {"items": []}
        for d in djson.get("items", []):
            meta = d.get("metadata", {}) or {}
            spec = d.get("spec", {}) or {}
            status = d.get("status", {}) or {}
            twins = status.get("twins", []) or []
            out["devices"].append({
                "name": meta.get("name", ""),
                "namespace": meta.get("namespace", "default"),
                "model": (spec.get("deviceModelRef") or {}).get("name", ""),
                "node": spec.get("nodeName", ""),
                "state": status.get("state", ""),
                "lastOnlineTime": status.get("lastOnlineTime", ""),
                "twins": [
                    {
                        "propertyName": t.get("propertyName", ""),
                        "reported": (t.get("reported") or {}).get("value"),
                        "observedDesired": (t.get("observedDesired") or {}).get("value"),
                        "timestamp": ((t.get("reported") or {}).get("metadata") or {}).get("timestamp", ""),
                    }
                    for t in twins
                ],
                "source": "cloud",
            })
    except Exception as e:  # noqa: BLE001
        errors.append(f"解析 Device 失败：{e}")

    out["error"] = "; ".join(errors) if errors else ""
    out["ok"] = not errors
    return out


# ------------------------- 采集：CloudCore 实时日志（增量） -------------------------

_LOG_QUERY = (
    "echo '==POD=='; kubectl get pods -n kubeedge -l app=cloudcore "
    "-o custom-columns=NAME:.metadata.name,READY:.status.containerStatuses[0].ready,"
    "PHASE:.status.phase,RESTARTS:.status.containerStatuses[0].restartCount --no-headers 2>/dev/null;"
    "echo '==LOG=='; kubectl logs --tail=8 --timestamps=true -n kubeedge -l app=cloudcore 2>/dev/null | tail -8;"
)


def collect_logs() -> Dict[str, Any]:
    """采集 CloudCore Pod 状态 + 最近日志行，只返回新增行（增量推送，平台侧去重兜底）。"""
    now = time.time()
    out: Dict[str, Any] = {"ts": now, "cloudcore": None, "error": "", "lines": []}
    ok, stdout, stderr = _run(_LOG_QUERY, timeout=30)
    if not ok:
        out["error"] = stderr or stdout or "采集失败"
        return out
    sections = _split_sections(stdout)
    for line in sections.get("POD", "").splitlines():
        p = line.split()
        if len(p) >= 4:
            out["cloudcore"] = {
                "name": p[0], "ready": p[1].lower() == "true",
                "phase": p[2], "restarts": p[3],
            }
            break
    fresh: List[str] = []
    for line in sections.get("LOG", "").splitlines():
        line = line.strip()
        if not line or line in _LOG_SEEN:
            continue
        _LOG_SEEN.append(line)
        fresh.append(line)
    out["lines"] = fresh
    return out


# ------------------------- MQTT 推送（mosquitto_pub，零依赖） -------------------------

def _pub(topic: str, payload: Dict[str, Any]) -> None:
    """向云端本地 Broker publish 一条 JSON 消息（mosquitto_pub 短连接）。"""
    try:
        cmd = ["mosquitto_pub", "-h", str(_CFG.get("broker_host", "127.0.0.1")),
               "-p", str(_CFG.get("broker_port", 41883)), "-t", topic,
               "-m", json.dumps(payload, ensure_ascii=False), "-q", "1"]
        if _CFG.get("broker_username"):
            cmd += ["-u", str(_CFG["broker_username"]), "-P", str(_CFG.get("broker_password", ""))]
        subprocess.run(cmd, capture_output=True, timeout=10)
    except Exception as e:  # noqa: BLE001
        log(f"publish {topic} 失败：{e}")


def _push_loop(interval: float, topic: str, collector: Any) -> None:
    """周期采集并推送（线程永不退出）。"""
    while True:
        try:
            data = collector()
            data["ts"] = time.time()
            _pub(topic, data)
        except Exception as e:  # noqa: BLE001
            log(f"{topic} 采集异常：{e}")
        time.sleep(max(1.0, interval))


def start_publishers() -> None:
    """启动三个推送线程：state 30s / crds 5s / logs 3s。"""
    intervals = _CFG.get("intervals") or {}
    jobs = [
        (float(intervals.get("state", 30)), "cloud/state", collect_state),
        (float(intervals.get("crds", 5)), "cloud/crds", collect_crds),
        (float(intervals.get("logs", 3)), "cloud/logs", collect_logs),
    ]
    for interval, topic, fn in jobs:
        threading.Thread(target=_push_loop, args=(interval, topic, fn),
                         name=f"pub-{topic}", daemon=True).start()
        log(f"推送线程启动：{topic} 每 {interval}s")


# ------------------------- HTTP API（平台写操作 + force 拉取） -------------------------

class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # 静默访问日志
        pass

    def _auth_ok(self) -> bool:
        expect = str(_CFG.get("token") or "")
        if not expect:
            return False
        auth = self.headers.get("Authorization", "")
        return auth == f"Bearer {expect}"

    def _json(self, code: int, data: Dict[str, Any]) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _denied(self) -> None:
        self._json(401, {"ok": False, "error": "unauthorized"})

    def _read_body(self, max_size: int = 4 * 1024 * 1024) -> Dict[str, Any]:
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > max_size:
                return {}
            return json.loads(self.rfile.read(n).decode("utf-8", "replace") or "{}")
        except Exception:  # noqa: BLE001
            return {}

    # ---- 读（force 拉取） ----
    def do_GET(self):  # noqa: N802
        if not self._auth_ok():
            return self._denied()
        path = self.path.split("?")[0]
        if path == "/api/health":
            return self._json(200, {"ok": True, "ts": time.time(), "version": "1.1"})
        if path == "/api/state":
            data = collect_state(); data["ts"] = time.time()
            return self._json(200, data)
        if path == "/api/crds":
            data = collect_crds(); data["ts"] = time.time()
            return self._json(200, data)
        if path == "/api/logs":
            return self._json(200, collect_logs())
        if path == "/api/edge/config":
            return self._json(200, {"ok": True, "edge": dict(_CFG.get("edge") or {})})
        if path == "/api/rootca":
            return self._json(200, _rootca())
        if path == "/api/history":
            q = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            g = lambda k, d="": (q.get(k) or [d])[0]  # noqa: E731
            try:
                pts = int(g("points", "500"))
            except (TypeError, ValueError):
                pts = 500
            return self._json(200, _tsdb_history(
                box=g("box"), device=g("device"), instance=g("instance"), prop=g("property"),
                start=g("start"), end=g("end"), points=pts))
        self._json(404, {"ok": False, "error": "not found"})

    # ---- 写（kubectl apply / delete / ingest / 盒子远程一键） ----
    def do_POST(self):  # noqa: N802
        if not self._auth_ok():
            return self._denied()
        path = self.path.split("?")[0]
        # /api/edge/upload 会携带整包 onboard 脚本（base64 可达数十 MB），放宽 body 上限
        body = self._read_body(max_size=256 * 1024 * 1024 if path == "/api/edge/upload" else 4 * 1024 * 1024)
        if path == "/api/apply":
            yaml_text = str(body.get("yaml") or "")
            if not yaml_text:
                return self._json(400, {"ok": False, "error": "yaml 不能为空"})
            ok, stdout, stderr = _run("kubectl apply -f -", stdin_data=yaml_text, timeout=150)
            return self._json(200, {"ok": ok, "rc": 0 if ok else 1,
                                    "stdout": stdout.strip(), "stderr": stderr.strip()})
        if path == "/api/delete":
            kind = str(body.get("kind") or "device")
            name = str(body.get("name") or "")
            ns = str(body.get("namespace") or "default")
            if not _K8S_NAME_RE.fullmatch(name):
                return self._json(400, {"ok": False, "error": f"对象名不合法：{name}"})
            if ns and not _K8S_NAME_RE.fullmatch(ns):
                return self._json(400, {"ok": False, "error": f"命名空间不合法：{ns}"})
            cmds, kinds = [], []
            if kind in ("device", "both"):
                cmds.append(f"kubectl delete device {name} -n {ns} --ignore-not-found")
                kinds.append("device")
            if kind in ("model", "both"):
                cmds.append(f"kubectl delete devicemodel {name} -n {ns} --ignore-not-found")
                kinds.append("devicemodel")
            if not cmds:
                return self._json(400, {"ok": False, "error": f"kind 不合法：{kind}"})
            ok, stdout, stderr = _run("; ".join(cmds))
            return self._json(200, {"ok": ok, "rc": 0 if ok else 1,
                                    "stdout": stdout.strip(), "stderr": stderr.strip(),
                                    "deleted": kinds})
        if path == "/api/ingest":
            return self._json(200, _ingest(body))
        if path == "/api/restart":
            return self._json(200, _restart(body))
        if path == "/api/edge/config":
            return self._json(200, _update_edge_config(body))
        if path == "/api/edge/check":
            return self._json(200, _edge_check(body))
        if path == "/api/edge/run":
            return self._json(200, _edge_run(body))
        if path == "/api/edge/upload":
            return self._json(200, _edge_upload(body))
        self._json(404, {"ok": False, "error": "not found"})


def _parse_ms(s: str) -> int:
    """时间串 → 毫秒时间戳。支持毫秒整数 / '2026-08-27 10:00:00' / ISO T 分隔。"""
    s = str(s).strip()
    if not s:
        return 0
    if s.isdigit():
        return int(s)
    try:
        t = s.replace("T", " ")[:19]
        return int(datetime.strptime(t, "%Y-%m-%d %H:%M:%S").timestamp() * 1000)
    except Exception:  # noqa: BLE001
        return 0


def _tsdb_history(box: str = "", device: str = "", instance: str = "", prop: str = "",
                  start: str = "", end: str = "", points: int = 500) -> Dict[str, Any]:
    """查询云端 TDengine 设备历史读数（GET /api/history）。

    data/{box}/{device}/{instance}/{property} 主题写入 nengtan.readings 超表
    （deploy_cloud.sh --tsdb-only 部署）。按时间范围做 INTERVAL 降采样，
    返回 [{t: 毫秒窗口起点, v: 均值}]，目标点数由 points 控制（默认 500）。
    """
    td = dict(_CFG.get("tdengine") or {})
    url = str(td.get("url") or "http://127.0.0.1:6041").rstrip("/")
    user = str(td.get("user") or "root")
    password = str(td.get("password") or "taosdata")
    db = str(td.get("db") or "nengtan")
    if not box:
        return {"ok": False, "error": "box 必填"}
    try:
        points = max(1, min(int(points), 2000))
    except (TypeError, ValueError):
        points = 500
    now_ms = int(time.time() * 1000)
    start_ms = _parse_ms(start) or (now_ms - 24 * 3600 * 1000)
    end_ms = _parse_ms(end) or now_ms
    if end_ms <= start_ms:
        end_ms = start_ms + 1000
    interval_s = max(1, int((end_ms - start_ms) / 1000 / points))
    if interval_s < 60:
        interval = f"{interval_s}s"
    elif interval_s < 3600:
        interval = f"{interval_s // 60}m"
    else:
        interval = f"{interval_s // 3600}h"

    cond = f"box='{box.replace(chr(39), chr(39) * 2)}'"
    for name, val in (("device", device), ("instance", instance), ("property", prop)):
        if val:
            cond += f" AND {name}='{val.replace(chr(39), chr(39) * 2)}'"
    sql = (f"SELECT _wstart AS t, AVG(value) AS v FROM {db}.readings "
           f"WHERE {cond} AND ts>={start_ms} AND ts<={end_ms} "
           f"INTERVAL({interval}) FILL(NULL) ORDER BY t ASC")
    auth = base64.b64encode(f"{user}:{password}".encode()).decode()
    req = urllib.request.Request(f"{url}/rest/sql", data=sql.encode("utf-8"), method="POST",
                                 headers={"Authorization": f"Basic {auth}",
                                          "Content-Type": "text/plain"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"TDengine 查询失败：{e}（云端需先部署时序库：deploy_cloud.sh --tsdb-only）"}
    if not isinstance(data, dict) or data.get("code", 0) != 0:
        desc = data.get("desc") if isinstance(data, dict) else "未知错误"
        return {"ok": False, "error": f"TDengine 查询错误：{desc}"}
    series = [{"t": row[0], "v": row[1]} for row in (data.get("data") or []) if row and row[1] is not None]
    return {"ok": True, "box": box, "device": device, "instance": instance, "property": prop,
            "start": start_ms, "end": end_ms, "interval": interval, "count": len(series),
            "series": series}


def _ingest(body: Dict[str, Any]) -> Dict[str, Any]:
    """回写单点 twins：本地 get 当前 twins → 合并 → patch（与平台旧 SSH 逻辑等价）。"""
    name = str(body.get("device") or "").strip()
    ns = str(body.get("namespace") or "default").strip()
    prop = str(body.get("property") or "").strip()
    value = body.get("value")
    if not name or not _K8S_NAME_RE.fullmatch(name):
        return {"ok": False, "error": f"device 不合法：{name}"}
    if not ns or not _K8S_NAME_RE.fullmatch(ns):
        return {"ok": False, "error": f"namespace 不合法：{ns}"}
    if not prop:
        return {"ok": False, "error": "property 不能为空"}
    if value is None:
        return {"ok": False, "error": "value 不能为空"}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ok, stdout, stderr = _run(
        f"kubectl get device {name} -n {ns} -o jsonpath='{{.status.twins}}' 2>/dev/null"
    )
    if not ok:
        return {"ok": False, "error": f"云端读取设备失败（可能未下发）：{stderr or stdout or 'rc!=0'}"}
    try:
        twins = json.loads(stdout.strip()) if stdout.strip() else []
        if not isinstance(twins, list):
            twins = []
    except Exception:  # noqa: BLE001
        twins = []
    twin = {
        "propertyName": prop,
        "reported": {"value": str(value), "metadata": {"timestamp": now}},
        "observedDesired": {"value": str(value)},
    }
    for i, t in enumerate(twins):
        if t.get("propertyName") == prop:
            twins[i] = twin
            break
    else:
        twins.append(twin)
    patch = json.dumps({"status": {"state": "online", "lastOnlineTime": now, "twins": twins}},
                       ensure_ascii=False)
    ok, stdout, stderr = _run(
        f"kubectl patch device {name} -n {ns} --type=merge -p \"$(cat)\"",
        stdin_data=patch, timeout=90,
    )
    return {"ok": ok, "rc": 0 if ok else 1, "stdout": stdout.strip(), "stderr": stderr.strip(),
            "device": name, "namespace": ns, "property": prop,
            "reported": str(value), "timestamp": now}


def _update_edge_config(body: Dict[str, Any]) -> Dict[str, Any]:
    """保存边缘盒子连接配置到 config.json 并热更新（HTTP POST /api/edge/config）。

    body 可包含 host/port/user/password/key 任一字段；空串表示清除。同时返回 SSH 连通性探测结果，
    便于平台在保存后立即知晓盒子是否可达（IP 为空/不通时平台可拒绝重启 Mapper 等操作）。
    """
    fields = ("host", "port", "user", "password", "key")
    edge = dict(_CFG.get("edge") or {})
    updated: List[str] = []
    for f in fields:
        if f in body:
            val = body.get(f)
            if f == "port":
                try:
                    edge["port"] = int(val or 22)
                except (TypeError, ValueError):
                    return {"ok": False, "error": f"port 必须是整数：{val!r}"}
            else:
                edge[f] = str(val or "").strip() if val is not None else ""
            updated.append(f)
    if not updated:
        return {"ok": False, "error": "body 需包含 host/port/user/password/key 至少一个字段"}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
    except Exception:  # noqa: BLE001
        data = {}
    data["edge"] = edge
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"保存 config.json 失败：{e}"}
    _CFG["edge"] = edge
    log(f"edge 配置已更新：{','.join(updated)} host={edge.get('host') or '(空)'}")
    # 保存后立即探测连通性（仅 host 非空时）
    check = _edge_check({"host": edge.get("host"), "port": edge.get("port")})
    return {"ok": True, "edge": dict(edge), "updated": updated, "check": check}


def _edge_check(body: Dict[str, Any]) -> Dict[str, Any]:
    """探测边缘盒子 SSH 可达性（HTTP POST /api/edge/check）。

    仅做 TCP 22 端口连通性探测（不实际登录），用于平台校验：
    IP 为空 → 不可达；TCP 连不上 → 不可达（盒子无直达 IP 或未上电/断网）。
    """
    edge = _CFG.get("edge") or {}
    host = str(body.get("host") if body.get("host") is not None else edge.get("host") or "").strip()
    port = int(body.get("port") or edge.get("port") or 22)
    if not host:
        return {"ok": False, "reachable": False, "error": "IP 为空（未配置盒子 IP，无法 SSH 直达）",
                "host": "", "port": port}
    import socket as _sock
    try:
        with _sock.create_connection((host, port), timeout=5):
            return {"ok": True, "reachable": True, "host": host, "port": port,
                    "error": ""}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reachable": False, "host": host, "port": port,
                "error": f"SSH({host}:{port}) 不可达：{e}"}


def _ssh_exec(remote_cmd: str, stdin_data: "Optional[str]" = None,
              stdin_bytes: "Optional[bytes]" = None, timeout: int = 120,
              edge_override: "Optional[Dict[str, Any]]" = None) -> "tuple[bool, str, str]":
    """SSH 到边缘盒子执行一条任意命令，凭据来自 config.json 的 edge 字段。

    支持密码（需系统安装 sshpass）或密钥两种认证方式；均未配置时返回友好错误。
    edge_override 可由调用方（平台）传入本次请求的 edge 配置，覆盖 config.json（未传则用配置值）。
    stdin_bytes 提供时按二进制通过 SSH stdin 传给远端（用于上传文件）。
    """
    edge = dict(_CFG.get("edge") or {})
    if edge_override:
        edge.update({k: v for k, v in edge_override.items() if v is not None})
    host = str(edge.get("host") or "").strip()
    if not host:
        return False, "", "config.json 未配置 edge 节点（host），请编辑 /opt/cloud-agent/config.json 填写边缘盒子可达地址（现场内网/跳板机）。盒子无直达 IP 时云端无法 SSH 直达，请现场运维或走 kubectl 下发"
    port = int(edge.get("port") or 22)
    user = str(edge.get("user") or "root").strip()
    password = str(edge.get("password") or "")
    key = str(edge.get("key") or "").strip()
    if not password and not key:
        return False, "", f"config.json 的 edge 节点未配置认证（password 或 key），请编辑 /opt/cloud-agent/config.json 补充后再试"
    common = (f"-p {port} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
              f"-o ConnectTimeout=8 -o ServerAliveInterval=5 -o ServerAliveCountMax=2")
    if key:
        if not os.path.isfile(key):
            return False, "", f"edge.key 不存在：{key}"
        prefix = f"ssh -i {key} {common} {user}@{host}"
    else:
        if subprocess.run(["bash", "-c", "command -v sshpass"],
                          capture_output=True).returncode != 0:
            return False, "", "需要 sshpass 命令（密码认证）：yum install -y sshpass 后重试，或改用 edge.key 密钥认证"
        prefix = f"sshpass -p '{password}' ssh {common} {user}@{host}"
    # 统一走 `ssh host bash -s` + stdin 传命令，避免远端命令引号/转义问题
    cmd = f"{prefix} 'bash -s'"
    if stdin_bytes is not None:
        ok, stdout, stderr = _run_bin(cmd, stdin_bytes, timeout=timeout)
    else:
        ok, stdout, stderr = _run(cmd, stdin_data=remote_cmd, timeout=timeout)
    return ok, stdout, stderr


def _ssh_run(remote_cmd: str, timeout: int = 60,
             edge_override: "Optional[Dict[str, Any]]" = None) -> "tuple[bool, str, str]":
    """SSH 到边缘盒子 systemctl 重启一条服务（重启 box-mapper 等），凭据来自 config.json 的 edge 字段。"""
    return _ssh_exec(f"systemctl restart {remote_cmd} && systemctl is-active {remote_cmd}",
                     timeout=timeout, edge_override=edge_override)


def _restart(body: Dict[str, Any]) -> Dict[str, Any]:
    """重启云端工作负载 / 云端服务 / 边缘盒子服务（HTTP POST /api/restart）。

    - kind=deployment（默认，如 cloudcore）：kubectl rollout restart deployment/<name>
      （滚动重启，Pod 逐个重建，服务不中断）；
    - kind=pod：kubectl delete pod <name>（由 Deployment/StatefulSet 自动重建）；
    - kind=systemd：systemctl restart <name>（白名单：cloud-agent / nengtan-cloud-broker
      / nengtan-collector / nengtan-cloud-dashboard）。重启 cloud-agent 自身时延迟 2s 执行，
      先返回响应再重启自身进程；
    - kind=edge：SSH 到边缘盒子 systemctl restart <name>（白名单：box-mapper / edgecore
      / box-collector），凭据见 config.json 的 edge 字段。
    名称/命名空间按 k8s 命名规则校验防注入。
    """
    kind = str(body.get("kind") or "deployment").strip().lower()
    name = str(body.get("name") or "cloudcore").strip()
    ns = str(body.get("namespace") or "kubeedge").strip()
    if not name:
        return {"ok": False, "error": "name 不能为空"}
    if not _K8S_NAME_RE.fullmatch(name):
        return {"ok": False, "error": f"对象名不合法：{name}"}
    if kind in ("deployment", "deploy"):
        if not ns or not _K8S_NAME_RE.fullmatch(ns):
            return {"ok": False, "error": f"命名空间不合法：{ns}"}
        cmd = f"kubectl rollout restart deployment/{name} -n {ns}"
        ok, stdout, stderr = _run(cmd, timeout=120)
        return {"ok": ok, "rc": 0 if ok else 1, "stdout": stdout.strip(), "stderr": stderr.strip(),
                "kind": kind, "name": name, "namespace": ns}
    if kind == "pod":
        if not ns or not _K8S_NAME_RE.fullmatch(ns):
            return {"ok": False, "error": f"命名空间不合法：{ns}"}
        cmd = f"kubectl delete pod {name} -n {ns}"
        ok, stdout, stderr = _run(cmd, timeout=120)
        return {"ok": ok, "rc": 0 if ok else 1, "stdout": stdout.strip(), "stderr": stderr.strip(),
                "kind": kind, "name": name, "namespace": ns}
    if kind == "systemd":
        if name not in _SYSTEMD_ALLOW:
            return {"ok": False, "error": f"systemd 服务不在白名单：{name}（仅支持 {'/'.join(sorted(_SYSTEMD_ALLOW))}）"}
        if name == "cloud-agent":
            # 重启自身：延迟 2s 执行，先返回 HTTP 响应再被 systemd 拉起
            _run("nohup bash -c 'sleep 2; systemctl restart cloud-agent' >/dev/null 2>&1 &",
                 timeout=5)
            return {"ok": True, "rc": 0, "stdout": "", "stderr": "",
                    "kind": kind, "name": name, "namespace": "",
                    "info": "cloud-agent 延迟 2 秒后重启（先返回响应再拉起自身），期间 HTTP 短暂不可用"}
        ok, stdout, stderr = _run(f"systemctl restart {name} && systemctl is-active {name}",
                                  timeout=120)
        return {"ok": ok, "rc": 0 if ok else 1, "stdout": stdout.strip(), "stderr": stderr.strip(),
                "kind": kind, "name": name, "namespace": ""}
    if kind == "edge":
        if name not in _EDGE_UNIT_ALLOW:
            return {"ok": False, "error": f"边缘服务不在白名单：{name}（仅支持 {'/'.join(sorted(_EDGE_UNIT_ALLOW))}）"}
        # 平台可随请求携带 edge 覆盖配置（host/port/user/password/key），用于保存盒子 IP 后立即重启
        edge_ovr = body.get("edge") if isinstance(body.get("edge"), dict) else None
        ok, stdout, stderr = _ssh_run(name, edge_override=edge_ovr)
        return {"ok": ok, "rc": 0 if ok else 1, "stdout": stdout.strip(), "stderr": stderr.strip(),
                "kind": kind, "name": name, "namespace": ""}
    return {"ok": False, "error": f"kind 不合法：{kind}（仅支持 deployment / pod / systemd / edge）"}


# ------------------------- 盒子一键接入通道（平台远程操作盒子） -------------------------

def _rootca() -> Dict[str, Any]:
    """返回云端 rootCA.crt（base64），供平台内嵌到盒子一键接入脚本，免除现场 scp。"""
    for cand in ("/etc/kubeedge/ca/rootCA.crt", "/etc/kubeedge/ca/ca.crt"):
        if os.path.isfile(cand):
            try:
                b64 = base64.b64encode(open(cand, "rb").read()).decode("ascii")
                return {"ok": True, "path": cand, "data": b64, "size": len(b64)}
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"读取 {cand} 失败：{e}"}
    return {"ok": False, "error": "云端 rootCA.crt 不存在（请先部署 KubeEdge 控制面 gen_certs）"}


def _edge_run(body: Dict[str, Any]) -> Dict[str, Any]:
    """SSH 到边缘盒子执行一条任意命令（HTTP POST /api/edge/run）。

    body: {cmd, timeout?, edge?}。cmd 为空拒绝；timeout 上限 900s（一键接入脚本可跑较久）。
    该接口仅供平台经 Bearer token 调用，用途：盒子一键接入 / 现场远程运维。
    """
    cmd = str(body.get("cmd") or "").strip()
    if not cmd:
        return {"ok": False, "rc": 1, "stdout": "", "stderr": "cmd 不能为空"}
    if "rm -rf /" in cmd.replace(" ", "").replace("\t", ""):
        return {"ok": False, "rc": 1, "stdout": "", "stderr": "危险命令被拒绝"}
    timeout = min(max(int(body.get("timeout") or 300), 10), 900)
    edge_ovr = body.get("edge") if isinstance(body.get("edge"), dict) else None
    ok, stdout, stderr = _ssh_exec(cmd, timeout=timeout, edge_override=edge_ovr)
    return {"ok": ok, "rc": 0 if ok else 1, "stdout": stdout.strip(), "stderr": stderr.strip()}


def _edge_upload(body: Dict[str, Any]) -> Dict[str, Any]:
    """上传文件到边缘盒子（HTTP POST /api/edge/upload，base64 传输，可承载数十 MB）。

    body: {path, data(base64), mode?, edge?}。path 必须是绝对路径；数据经 SSH stdin 写入，无命令行长度限制。
    """
    path = str(body.get("path") or "").strip()
    data_b64 = str(body.get("data") or "")
    mode = str(body.get("mode") or "0644").strip()
    if not path:
        return {"ok": False, "rc": 1, "stdout": "", "stderr": "path 不能为空"}
    if not path.startswith("/"):
        return {"ok": False, "rc": 1, "stdout": "", "stderr": f"path 必须是绝对路径：{path}"}
    if not data_b64:
        return {"ok": False, "rc": 1, "stdout": "", "stderr": "data(base64) 不能为空"}
    if not re.fullmatch(r"[0-7]{3,4}", mode):
        return {"ok": False, "rc": 1, "stdout": "", "stderr": f"mode 不合法：{mode}"}
    try:
        raw = base64.b64decode(data_b64)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "rc": 1, "stdout": "", "stderr": f"data 不是合法 base64：{e}"}
    d = path.rsplit("/", 1)[0] or "/"
    edge_ovr = body.get("edge") if isinstance(body.get("edge"), dict) else None
    cmd = f"mkdir -p '{d}' && cat > '{path}' && chmod {mode} '{path}' && echo OK"
    ok, stdout, stderr = _ssh_exec(cmd, stdin_bytes=raw, timeout=300, edge_override=edge_ovr)
    return {"ok": ok, "rc": 0 if ok else 1, "bytes": len(raw), "path": path,
            "stdout": stdout.strip(), "stderr": stderr.strip()}


def main() -> None:
    if os.geteuid() != 0:
        log("建议以 root 运行（需要执行 kubectl/openssl 等系统命令）")
    if not _CFG.get("token"):
        log("警告：config.json 未配置 token，HTTP API 将拒绝所有请求")
    start_publishers()
    host, port = "0.0.0.0", int(_CFG.get("http_port", 42083))
    server = ThreadingHTTPServer((host, port), _Handler)
    log(f"HTTP 服务启动：{host}:{port}（Bearer token 认证）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
