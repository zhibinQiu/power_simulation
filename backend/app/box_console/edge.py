"""盒子连接配置（IP/SSH 凭据）与云端部署指令（MQTT 命令主题）。

依赖方向：本模块仅依赖共享状态 _shared 与 mqtt_source / cloud_agent，被 cloud_ops 依赖（单向）。
"""
from __future__ import annotations

from typing import Any, Dict

from .. import cloud_agent
from .. import mqtt_source
from ._shared import _LOCK, _load_devices, _save_devices


def edge_config() -> Dict[str, Any]:
    """读取盒子连接配置：本地 box_devices.json 顶层 edge（优先）→ 云端 agent 已存配置。

    edge 结构：{"host": 现场可达地址, "port": 22, "user": "root", "password": "", "key": ""}。
    """
    data = _load_devices()
    local = data.get("edge") if isinstance(data.get("edge"), dict) else {}
    if not local:
        remote = cloud_agent.get_edge_config()
        if remote.get("ok") and isinstance(remote.get("edge"), dict):
            local = {k: remote["edge"].get(k) for k in ("host", "port", "user", "password", "key")}
    return {"ok": True, "edge": local or {}}


def update_edge_config(p: Dict[str, Any]) -> Dict[str, Any]:
    """保存盒子连接配置到本地 box_devices.json + 云端 agent，并立即探测连通性。

    平台侧保存后 agent 侧 config.json 同步更新，重启 Mapper 等 SSH 操作使用新地址。
    """
    with _LOCK:
        data = _load_devices()
        edge = dict(data.get("edge") or {})
        for k in ("host", "port", "user", "password", "key"):
            if k in p and p[k] is not None:
                if k == "port":
                    try:
                        edge[k] = int(p[k] or 22)
                    except (TypeError, ValueError):
                        return {"ok": False, "error": "port 必须是整数：%r" % (p[k],)}
                else:
                    edge[k] = str(p[k]).strip()
        if not edge:
            return {"ok": False, "error": "缺少配置字段（host/port/user/password/key）"}
        data["edge"] = edge
        _save_devices(data)
    # 同步到云端 agent（保存成功后立即探测）；agent 未部署/不可达时不阻断本地保存，
    # 仅在返回中提示（重启 Mapper 等 SSH 操作仍需要 agent 在线且盒子可达）
    result = cloud_agent.update_edge_config(edge)
    if not result.get("ok"):
        return {"ok": True, "edge": edge, "check": None,
                "warning": "本地已保存；同步到云端 agent 失败（%s），盒子 IP 生效前需先部署/恢复 agent" % result.get("error", "")}
    return {"ok": True, "edge": edge, "check": result.get("check")}


def check_edge_reachable(host: str = "", port: int = 22) -> Dict[str, Any]:
    """探测盒子 SSH 可达性（经云端 agent TCP 探测，不实际登录）。"""
    host = (host or "").strip()
    if not host:
        cfg = edge_config().get("edge") or {}
        host = str(cfg.get("host") or "").strip()
        port = int(cfg.get("port") or 22)
    if not host:
        return {"ok": False, "reachable": False, "host": "", "port": port,
                "error": "IP 为空（未配置盒子 IP，无法 SSH 直达）"}
    return cloud_agent.check_edge(host=host, port=port)


def _resolve_box_id(box: str) -> str:
    """盒子名 -> MQTT boxId：优先精确匹配，其次尝试 box- 前缀（兼容 K8s 节点名 vs MQTT boxId 不一致）。"""
    box = (box or "").strip()
    if not box:
        return box
    with mqtt_source._LOCK:  # noqa: SLF001
        known = {str(i.get("box")) for i in mqtt_source.CLOUD_DEVICES.values() if i.get("box")}
    if box in known:
        return box
    if box.startswith("box-"):
        return box
    if ("box-" + box) in known:
        return "box-" + box
    return box


def box_app_cmd(box: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """向盒子下发应用部署/启停指令（MQTT 命令主题 cmd/{box}/deploy）。

    盒子运行期无直达 IP，云端→盒子方向只能经云端 Broker 命令主题：
    盒子 mapper 订阅 cmd/{box}/# 收到指令后执行，并回报 state/{box}/deploy。
    """
    box = _resolve_box_id(box)
    if not box:
        return {"ok": False, "error": "box 名为空"}
    if not isinstance(payload, dict) or not str(payload.get("cmd") or "").strip():
        return {"ok": False, "error": "指令需包含 cmd 字段（deploy/start/stop/restart/remove/list）"}
    return mqtt_source.publish_box_cmd(box, payload)


def box_app_list(box: str) -> Dict[str, Any]:
    """查询盒子当前运行的服务/模型列表（来自盒子 state/{box}/services 周期上报）。"""
    box = _resolve_box_id(box)
    services = mqtt_source.box_services(box)
    events = mqtt_source.box_app_events(box)
    return {"ok": True, "box": box, "services": services, "events": events}
