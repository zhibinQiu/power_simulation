"""概览：云端 MQTT Broker 实时统计（$SYS，真实）+ cloudcore/节点/端口/证书/token。

数据通道（替代 SSH）：云端 cloud-agent 定时采集（kubectl/openssl/ss）后经 MQTT
长连接推送到 cloud/state 主题，本平台订阅线程实时更新缓存，请求路径只读缓存（毫秒级）。
云端不可达/推送中断时明确返回 stale/unreachable + 原因，不伪造数据。
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List

from .. import cloud_agent
from .. import mqtt_source


def _fetch_cloud_k8s(force: bool = False) -> Dict[str, Any]:
    """云端 K3s/KubeEdge 状态（cloudcore / 节点 / 端口 / 证书 / token）。

    数据通道（替代 SSH）：云端 cloud-agent 定时采集（kubectl/openssl/ss）后经 MQTT
    长连接推送到 cloud/state 主题，本平台订阅线程实时更新缓存，请求路径只读缓存
    （毫秒级）；force=True 时 HTTP GET agent 实时拉取（盒子接入取最新 token 用）。
    云端不可达时返回 ok=False + 具体错误。
    """
    return cloud_agent.state(force=force)


def _mqtt_boxes() -> List[Dict[str, Any]]:
    """从 MQTT 云端设备分组识别盒子列表（box_overview 共用）。

    盒子侧版本未知时不虚构 version；age 取最近上报时间。
    """
    now = time.time()
    boxes: Dict[str, Dict[str, Any]] = {}
    for cid, info in mqtt_source.snapshot_cloud_devices().items():
        b = info.get("box") or "unknown-box"
        boxes.setdefault(b, {"box": b, "devices": 0, "last_seen": 0})
        boxes[b]["devices"] += 1
        boxes[b]["last_seen"] = max(boxes[b]["last_seen"], float(info.get("last_seen") or 0))

    mqtt_nodes: List[Dict[str, Any]] = []
    for b, info in sorted(boxes.items()):
        last = info["last_seen"]
        mqtt_nodes.append({
            "name": b, "ready": bool(last and (now - last) < 30),
            "roles": "edge", "version": "—",
            "age": datetime.fromtimestamp(last).strftime("%Y-%m-%d %H:%M:%S") if last else "未上报",
            "devices": info["devices"], "source": "mqtt", "is_edge": True,
        })
    return mqtt_nodes


def _merge_nodes(cloud: Dict[str, Any], mqtt_nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """合并 K8s edge 节点（SSH 真实）+ MQTT 识别盒子（按 name 去重）；无节点时返回空数组（不虚构 box-001）。

    去重按「归一化名称」比对：K8s 节点名（Device nodeName，如 nt001）与盒子 MQTT boxId
    （config.json mqtt.boxId，如 box-nt001）可能带/不带 box- 前缀，归一化后视为同一盒子，
    避免同一盒子在卡片上重复显示（保留 K8s 条目，其 name 为节点真实名）。
    """
    k8s_nodes = [n for n in cloud.get("nodes", []) if n.get("is_edge")]

    def _norm(name: str) -> str:
        s = str(name or "")
        return s[4:] if s.startswith("box-") else s

    seen = {_norm(n["name"]) for n in k8s_nodes}
    merged = list(k8s_nodes)
    for n in mqtt_nodes:
        key = _norm(n["name"])
        if key not in seen:
            seen.add(key)
            merged.append(n)
    return merged


def box_overview() -> Dict[str, Any]:
    """管理台概览：Broker 统计（$SYS，真实）+ cloudcore/节点/端口/证书/token（云端 cloud-agent 采集经 MQTT 推送）。

    云端不可达时明确返回 cloud_source=unreachable + 错误原因，不再返回任何仿真数据。
    """
    # 识别到的盒子（真实）：来自 MQTT 云端设备的分组
    mqtt_nodes = _mqtt_boxes()

    cloud = _fetch_cloud_k8s()
    # 缓存新鲜度：agent 推送中断（云端 broker/agent 离线）时旧缓存不得冒充实时状态
    cached_stale = bool(cloud.get("_cached")) and not cloud.get("_cache_fresh", True)
    live = bool(cloud.get("ok")) and not cached_stale
    nodes = _merge_nodes(cloud, mqtt_nodes)
    # 盒子卡片展示：附加盒子当前运行的服务/模型列表（来自盒子 state/{box}/services 周期上报）
    for n in nodes:
        nm = str(n.get("name") or "")
        svcs = mqtt_source.box_services(nm) or []
        if not svcs and nm and not nm.startswith("box-"):
            svcs = mqtt_source.box_services("box-" + nm) or []
        if not svcs and nm.startswith("box-") and len(nm) > 4:
            svcs = mqtt_source.box_services(nm[4:]) or []
        n["services"] = svcs
    # 云端推送中断：K8s 节点状态为过期缓存，标记「状态未知」而非误显示就绪/未就绪
    if cached_stale:
        for n in nodes:
            if n.get("is_edge") and n.get("ready") is not None:
                n["ready"] = None
                n["stale"] = True

    stats = mqtt_source.broker_stats()
    status = mqtt_source.get_status()
    cc = cloud.get("cloudcore")
    cc_ok = bool(cc and cc.get("phase") == "Running")
    if not cc:
        cc = {"name": "—", "phase": "未运行/未找到", "restarts": "—", "node": "—", "podIP": "—",
              "available": False,
              "error": cloud.get("error", "") or "云端未解析到 cloudcore Pod（kubectl get pod 无结果）"}
    else:
        cc["available"] = cc.get("phase") == "Running"
    # cloud_source 四态：live=agent 推送实时且 cloudcore 运行；stale=推送中断、展示的是过期缓存；
    # degraded=实时但组件异常；unreachable=云端完全不可达
    if not live and cached_stale:
        cloud_source = "stale"
    elif not live:
        cloud_source = "unreachable"
    elif cc_ok:
        cloud_source = "live"
    else:
        cloud_source = "degraded"
    if cloud_source == "live":
        cloud_error = ""
    elif cloud_source == "stale":
        age = cloud.get("_cache_age", 0)
        cloud_error = (f"云端推送已中断（缓存数据 {age}s 前更新，超过 120s 即视为过期）："
                       f"云端 MQTT Broker / cloud-agent 可能离线，或平台与云端 {status.get('broker_host')}:{status.get('broker_port')} 连接断开。"
                       f"当前节点/CloudCore 状态为过期缓存，请检查云端服务后重启平台后端恢复订阅。")
    else:
        cloud_error = cloud.get("error", "") or cc.get("error", "")
    return {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "broker": {
            "host": status.get("broker_host"), "port": status.get("broker_port"),
            "connected": status.get("connected", False),
            "stats": stats,   # $SYS 真实统计
        },
        "cloudcore": cc,
        "nodes": nodes,
        "ports": cloud.get("ports", []),
        "certs": cloud.get("certs", []),
        "token": cloud.get("token"),
        "cloud_source": cloud_source,
        "cloud_error": cloud_error,
        "demo_note": "" if cloud_source == "live" else (
            f"云端推送中断（数据 {cloud.get('_cache_age', 0)}s 前更新）：云端 MQTT Broker / cloud-agent 可能离线。"
            f"以下 CloudCore/端口/证书/token 为过期缓存（不伪造数据）。"
            if cloud_source == "stale" else
            f"云端数据通道不可达：{cloud.get('error', '')}。"
            f"以上 CloudCore/端口/证书/token 为空或不完整（不伪造数据），"
            f"请检查云端 MQTT Broker / cloud-agent 服务后重试。"
            if cloud_source == "unreachable" else
            f"云端 agent 实时可达，但 CloudCore 未运行或未解析到 Pod（{cloud_error}）。请检查云端 cloudcore 状态。"
        ),
    }
