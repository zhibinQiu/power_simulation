# -*- coding: utf-8 -*-
"""能碳一体机管理台 API（Box Console）。

参照参考项目 yunduan1 console + dashboard 全部功能：设备/模型多协议（Modbus / OPC-UA /
Bluetooth / LoRaWAN / 5G）YAML 生成、一键下发到云端 K3s（云端 agent 本地 kubectl apply，
HTTP API + MQTT 长连接数据通道，替代 SSH）、盒子接入（edgecore.yaml 模板 + 共享 token +
caHash）、实时数据（云端 MQTT 真实链路 + agent 回写 Device.status.twins）。

与 MQTT 实时数据源（mqtt_source）同属「能碳一体机管理」业务域：云端 Broker 配置、
云端识别设备、设备关联（link）、实时读数同步。路由统一挂载在 /api 前缀下
（/api/box/*、/api/realtime/*），业务实现见 box_console / mqtt_source / cloud_agent。
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .. import box_console
from .. import cloud_agent
from .. import github_deploy
from .. import mqtt_source

router = APIRouter(prefix="/api", tags=["box-console"])


# ------------------------- 实时数据源（MQTT，参照参考项目 yunduan1 数据链路） -------------------------

@router.get("/realtime/source")
def realtime_source_status():
    """实时数据源状态：MQTT 连接状态 / 订阅主题 / 最近消息 / 字段映射
    + 云端识别设备列表（cloud_devices）与设备关联表（links）。

    数据链路：边缘盒子 box-mapper 实时发布 data/# → 云端 MQTT Broker（Broker 在「能碳一体机管理」中配置）→
    平台订阅获取实时设备读数。

    关联制：云端设备必须与仿真系统中的设备实例手动关联（见 /api/realtime/link），
    未关联的设备读数不会同步到仿真系统。"""
    return mqtt_source.get_status()


class RealtimeLinkRequest(BaseModel):
    """云端设备 <-> 仿真设备实例关联请求。"""
    cloud_id: str = Field(..., description="云端识别设备 id（能碳一体机盒子下的设备）")
    local_id: str = Field(..., description="仿真系统设备实例 id（如 blast_furnace::belt_scale_0）")
    factor: float = Field(1.0, description="读数换算系数：云端原始读数 × factor = 同步到流程设备的读数（如 kg/min → t/h 填 0.06）")


@router.get("/realtime/link")
def realtime_links():
    """关联列表 + 云端识别设备（供连接面板渲染关联 UI）。"""
    return mqtt_source.get_links()


@router.put("/realtime/link")
def realtime_set_link(req: RealtimeLinkRequest):
    """建立/更新关联：把云端设备的数据同步到指定的仿真设备实例（一对一）。

    只有建立关联的云端设备，其读数才会经实时遥测同步到仿真系统对应设备实例。"""
    try:
        mqtt_source.set_link(req.cloud_id, req.local_id, req.factor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, **mqtt_source.get_links()}


@router.delete("/realtime/link/{cloud_id}")
def realtime_unlink(cloud_id: str):
    """解除关联：该云端设备数据不再同步到任何仿真设备实例。"""
    mqtt_source.remove_link(cloud_id)
    return {"ok": True, **mqtt_source.get_links()}


# ------------------------- 能碳一体机管理台（参照参考项目 yunduan1 console + dashboard 全部功能） -------------------------

class BoxDeviceRequest(BaseModel):
    """设备/模型创建请求（Modbus / OPC-UA / Bluetooth / LoRaWAN / 5G 五协议，YAML 生成参照 yunduan1 console）。"""
    mode: str = "apply"                # dryRun | apply
    protocol: str = "modbus"
    modelName: str = "box-metric-model"
    deviceName: str = "box-device"
    namespace: str = "default"
    nodeName: str = "edge-node"
    collectCycle: int = 1000
    desc: str = ""
    comm: Dict[str, Any] = Field(default_factory=dict)    # modbus: {commType, slaveID, tcpIP...}
    opcua: Dict[str, Any] = Field(default_factory=dict)   # opcua: {url, userName...}
    bluetooth: Dict[str, Any] = Field(default_factory=dict)  # bluetooth: {macAddress}
    lora: Dict[str, Any] = Field(default_factory=dict)    # lora: {broker, applicationID, devEUI, appKey...}
    cellular: Dict[str, Any] = Field(default_factory=dict)   # cellular: {serialPort, baudRate, apn, iface}
    cloudDevice: str = ""                                  # 可选：绑定云端识别设备 id（实时匹配优先）
    origName: str = ""                                     # 编辑时携带原设备名：改名场景后端据此移除旧记录（避免残留旧设备）
    properties: List[Dict[str, Any]] = Field(default_factory=list)


class BoxDeleteRequest(BaseModel):
    kind: str = "device"   # device | model | both
    name: str
    namespace: str = "default"
    cloud: bool = False    # 同时调云端 agent kubectl delete 真实 CRD
    local: bool = True     # 同时移除本地 box_devices.json 配置（local=False+cloud=True 仅删云端）


class BoxIngestRequest(BaseModel):
    """边缘桥接脚本上报单点实时值：云端 agent 本地 get→merge→patch 回写云端 Device.status.twins。"""
    device: str
    namespace: str = "default"
    property: str = "value"
    value: Any = None


class BoxOnboardRequest(BaseModel):
    hostname: str = "edge-box"
    cloudIP: str = ""
    boxIP: str = ""


class BoxOnboardRemoteRequest(BaseModel):
    """盒子远程一键接入（云端 agent SSH 推送并执行 onboard_box.sh）。

    boxIP/port/user/password/key 可选：覆盖云端 agent 默认 edge 连接（config.json edge 字段）。
    盒子无直达 IP 时云端无法 SSH 直达，请改用「下载脚本 → 现场执行」。"""
    hostname: str = "edge-box"
    cloudIP: str = ""
    boxIP: str = ""
    port: int = 22
    user: str = ""
    password: str = ""
    key: str = ""


class GitHubConfigRequest(BaseModel):
    """GitHub 托管配置（盒子一键接入资产同步到用户 GitHub 仓库）。

    token 为 GitHub 个人访问令牌（PAT，contents 写权限）；留空表示沿用已保存值。"""
    owner: str = ""
    repo: str = ""
    branch: str = "master"
    token: str = ""


class GitHubPushRequest(BaseModel):
    cloudIP: str = ""


class BoxPublishRequest(BaseModel):
    topic: str
    payload: str = ""


class BoxConfigRequest(BaseModel):
    """云端 Broker 配置（前端「能碳一体机管理」配置弹窗提交，配置化免手工编辑 yaml）。"""
    broker: Dict[str, Any] = Field(default_factory=dict)      # {host, port, username, password, client_id...}
    topics: List[str] = Field(default_factory=list)
    mapping: Dict[str, str] = Field(default_factory=dict)     # mqtt 字段 -> 平台设备 id（静态关联 seed）


class BoxApplyRequest(BaseModel):
    """一键下发请求：name 为空 = 下发全部设备（含各自模型）；model_name 指定 = 下发该模型 + 引用它的所有设备。
    dry_run=True 仅预览 YAML 内容。"""
    name: str = ""
    model_name: str = ""
    dry_run: bool = False


class BoxModelRequest(BaseModel):
    """模型更新请求：修改属性点位后对引用该模型的所有设备同时生效（mode=dryRun 仅预览模型 YAML）。"""
    mode: str = "apply"
    protocol: str = "modbus"
    modelName: str
    namespace: str = "default"
    properties: List[Dict[str, Any]] = Field(default_factory=list)


class BoxEdgeConfigRequest(BaseModel):
    """盒子连接配置（盒子卡片上填写现场可达 IP，用于重启 Mapper 等 SSH 操作）。

    - host：现场可达地址（现场内网 IP / 跳板机 / frp 地址）；运行期盒子无 IP，为空时拒绝重启 Mapper
    - port：SSH 端口（默认 22）
    - user / password / key：SSH 凭据（云端 agent 登录盒子用）
    - box / name：盒子显示名称别名（box=云端节点名，name=显示别名，留空恢复原名）
    """
    host: str = ""
    port: int = 22
    user: str = ""
    password: str = ""
    key: str = ""
    box: str = ""
    name: str = ""


class BoxAppCmdRequest(BaseModel):
    """向盒子下发应用/模型部署指令（云端→盒子方向，经云端 Broker 命令主题 cmd/{box}/deploy）。

    - box：目标盒子名（如 nt001）
    - cmd：deploy / start / stop / restart / remove / list
    - deploy 额外字段：name 应用名、type(model|service)、url(下载地址)、command(启动命令)、args、version
    """
    box: str = "nt001"
    cmd: str = "deploy"
    name: str = ""
    type: str = "service"          # model | service
    url: str = ""
    command: str = ""
    args: List[str] = Field(default_factory=list)
    version: str = "1.0.0"
    request_id: str = ""


@router.get("/box/config")
def box_get_config():
    """能碳一体机管理 - 云端 Broker 配置（前端配置化，password 脱敏）。"""
    return box_console.get_config()


@router.post("/box/config")
def box_update_config(req: BoxConfigRequest):
    """保存云端 Broker 配置并热更新（前端配置化，持久化到 box_config.json，无需手工编辑配置文件）。"""
    try:
        return box_console.update_config(req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/box/overview")
def box_overview():
    """能碳一体机管理台 - 概览：Broker 实时统计（真实 $SYS）+ cloudcore/节点/端口/证书/token（云端 agent MQTT 推送）。"""
    return box_console.box_overview()


@router.get("/box/devices")
def box_devices():
    """设备管理：DeviceModel/Device 列表 + 云端识别设备（真实读数）。"""
    return box_console.list_devices()


@router.post("/box/devices")
def box_create_device(req: BoxDeviceRequest):
    """创建设备：mode=dryRun 返回三协议 YAML 预览；mode=apply 保存到云端集群。
    模型点位变更会同步重刷所有引用该模型的设备（对同一模型的所有设备同时生效）。"""
    p = req.model_dump()
    try:
        return box_console.create_device(p)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/box/models")
def box_update_model(req: BoxModelRequest):
    """更新模型点位并下发：对引用该模型的所有设备同时生效（同步重刷各设备 YAML）。
    mode=dryRun 仅返回模型 YAML 预览；mode=apply 保存并返回受影响设备列表。"""
    try:
        return box_console.update_model(req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/box/devices/delete")
def box_delete_device(req: BoxDeleteRequest):
    """删除设备：本地 box_devices.json 移除（local=True）；cloud=True 时同时调云端 agent 删除真实 CRD。"""
    return box_console.delete_device(req.kind, req.name, req.namespace, cloud=req.cloud, local=req.local)


@router.get("/box/devices/cloud")
def box_devices_cloud(force: bool = False):
    """云端已下发 CRD 真实列表（云端 agent 每 5s 采集经 MQTT cloud/crds 推送缓存）。

    force=true 时 HTTP 实时拉取（用于下发/删除操作后的即时刷新）。"""
    return box_console.cloud_crds(force=force)


class BoxCloudConfigRequest(BaseModel):
    """云端 agent 连接配置（替代 SSH 的数据通道：MQTT cloud/# 推送读 + HTTP 42083 写）。"""
    host: str = ""
    agent_port: int = 42083
    agent_token: str = ""
    namespace: str = "default"


class BoxCloudRestartRequest(BaseModel):
    """重启云端工作负载/服务/边缘服务。

    - kind=deployment（默认，name=cloudcore namespace=kubeedge）：kubectl rollout restart
    - kind=pod：kubectl delete pod（Deployment 自动重建）
    - kind=systemd：systemctl restart 云端服务（name ∈ cloud-agent / nengtan-cloud-broker
      / nengtan-collector / nengtan-cloud-dashboard，namespace 忽略）
    - kind=edge：SSH 到边缘盒子 systemctl restart 边缘服务（name ∈ box-mapper / edgecore
      / box-collector，namespace 忽略）
    """
    kind: str = "deployment"      # deployment | pod | systemd | edge
    name: str = ""                # 工作负载 / 云端服务 / 边缘服务名
    namespace: str = "default"    # kind=deployment/pod 时的命名空间


@router.get("/box/cloud/config")
def box_cloud_config():
    """一键下发配置：云端 agent 主机/端口/token + 命名空间（存于 box_devices.json 顶层 cloud）。"""
    return box_console.cloud_config()


@router.post("/box/cloud/config")
def box_cloud_config_update(req: BoxCloudConfigRequest):
    """保存云端 agent 连接配置（持久化到 box_devices.json 顶层 cloud，前端「总览 → 配置」）。"""
    try:
        result = box_console.update_cloud_config(req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    cloud_agent.invalidate_cfg()  # 配置已变更，立即失效 agent_cfg 读盘缓存
    return result


@router.get("/box/cloud/agent/status")
def box_cloud_agent_status():
    """云端 agent 健康检查：HTTP 可达性 + 版本 + 数据推送新鲜度（state/crds/logs 最近推送时间）。"""
    return cloud_agent.health()


@router.post("/box/cloud/restart")
def box_cloud_restart(req: BoxCloudRestartRequest):
    """重启云端工作负载 / 云端服务 / 边缘盒子服务：
    - deployment/pod → agent 本地 kubectl（CloudCore 崩溃/卡死快速恢复）；
    - systemd → agent 本地 systemctl restart（cloud-agent / MQTT Broker 等云端服务）；
    - edge → agent SSH 到边缘盒子 systemctl restart（box-mapper 等）。
    重启 edge 前会校验盒子 IP：IP 为空或 SSH 探测不通则拒绝。"""
    try:
        return box_console.restart_cloud_workload(req.kind, req.name, req.namespace)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/box/edge/config")
def box_edge_config():
    """盒子连接配置：现场可达 IP / SSH 凭据（重启 Mapper 等操作前必须配置且可达）。"""
    return box_console.edge_config()


@router.post("/box/edge/config")
def box_edge_config_update(req: BoxEdgeConfigRequest):
    """保存盒子连接配置（本地 + 云端 agent 同步），并立即探测连通性。"""
    p = req.model_dump()
    try:
        return box_console.update_edge_config(p)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/box/edge/check")
def box_edge_check(req: BoxEdgeConfigRequest):
    """探测盒子 SSH 可达性（经云端 agent TCP 探测，不实际登录）。

    用于前端校验：IP 为空或探测不通时，重启 Mapper 等 SSH 操作将被拒绝。"""
    try:
        return box_console.check_edge_reachable(host=req.host, port=req.port)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/box/apps/cmd")
def box_app_cmd(req: BoxAppCmdRequest):
    """向盒子下发应用/模型部署指令（云端→盒子，经云端 Broker 命令主题 cmd/{box}/deploy）。

    - deploy：下载 url 并安装到盒子 /opt/box-apps/{name}/，service 类型可配置启动命令并后台拉起
    - start / stop / restart / remove：管理已部署应用
    - list：查询盒子当前运行的服务/模型
    执行结果经 state/{box}/deploy 回报，运行服务列表周期上报 state/{box}/services。"""
    box = (req.box or "nt001").strip()
    payload = req.model_dump()
    return box_console.box_app_cmd(box, payload)


@router.get("/box/apps")
def box_apps(box: str = "box-nt001"):
    """查询盒子当前运行的服务/模型列表 + 最近命令执行结果（来自盒子周期上报）。"""
    return box_console.box_app_list(box)


@router.websocket("/ws/cloud")
async def ws_cloud(websocket: WebSocket):
    """云端实时推送：agent 经 MQTT cloud/# 推送的概览/CRD/日志，经此 WebSocket 实时转发给前端。

    连接后立即推送当前快照（state + logs），之后每次 cloud/state、cloud/crds、cloud/logs
    推送即时广播。前端断线自动重连（回退 HTTP 轮询兜底）。"""
    await websocket.accept()
    q: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue(maxsize=200)
    cloud_agent.subscribe(q)
    try:
        await websocket.send_json({
            "kind": "snapshot",
            "data": {"state": cloud_agent.state(), "logs": cloud_agent.logs()},
            "ts": time.time(),
        })
    except Exception:  # noqa: BLE001
        pass

    async def _send_loop() -> None:
        while True:
            msg = await q.get()
            await websocket.send_json(msg)

    task = asyncio.create_task(_send_loop())
    try:
        while True:
            await websocket.receive_text()   # 忽略客户端消息（心跳保活）
    except WebSocketDisconnect:
        pass
    finally:
        cloud_agent.unsubscribe(q)
        task.cancel()


@router.get("/box/cloud/logs")
def box_cloud_logs():
    """云端 CloudCore 实时日志（agent 每 3s 经 MQTT cloud/logs 推送，环形缓冲最近 300 行）。"""
    return box_console.cloud_logs()


@router.get("/box/cloud/tsdb/history")
def box_cloud_tsdb_history(box: str = "", device: str = "", instance: str = "",
                           prop: str = "", property_: str = Query("", alias="property"),
                           start: str = "", end: str = "", points: int = 500):
    """云端时序库历史读数查询（TDengine，经 agent /api/history）。

    参数：box/device/instance/prop 主题四元组（至少 box），prop 与 property 互为别名；
    start/end 支持毫秒时间戳或 'YYYY-MM-DD HH:MM:SS'（缺省近 24h）；
    points 目标点数（默认 500，最大 2000）。
    返回降采样序列 [{t, v}]，用于前端历史曲线。
    """
    return cloud_agent.history(box, device, instance, prop or property_, start, end, points)


@router.post("/box/devices/apply")
def box_devices_apply(req: BoxApplyRequest):
    """一键下发：调云端 agent 本地 kubectl apply（DeviceModel+Device，HTTP POST /api/apply）。
    model_name 指定时下发该模型 + 引用它的所有设备；dry_run=True 仅返回 YAML 内容用于前端预览，不执行下发。"""
    try:
        return box_console.apply_devices_to_cloud(req.name or None, dry_run=req.dry_run,
                                                  model_name=req.model_name or None)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"下发失败：{e}") from e


@router.get("/box/devices/realtime")
def box_devices_realtime():
    """实时数据：Device.status.twins 上报值（云端 K3s CRD 主链路 + MQTT 兜底）+ 趋势历史。"""
    return box_console.realtime_devices()


@router.post("/box/devices/realtime/ingest")
def box_ingest(req: BoxIngestRequest):
    """手动上报单点值：云端 agent 本地 get→merge→patch 回写云端 Device.status.twins（HTTP POST /api/ingest）。"""
    return box_console.ingest_device_value(req.model_dump())


@router.post("/box/nodes/onboard")
def box_onboard(req: BoxOnboardRequest):
    """盒子接入：生成自解压一键脚本（内嵌 box-deploy 包 + rootCA + edgecore.yaml + token），
    返回脚本元信息（下载走 GET /box/nodes/onboard/script，远程一键走 POST /box/nodes/onboard/remote）。"""
    return box_console.onboard_node(req.model_dump())


@router.get("/box/nodes/onboard/script")
def box_onboard_script():
    """下载已生成的一键接入脚本（onboard_box.sh，base64），浏览器/前端可落盘为可执行文件。"""
    return box_console.onboard_script_download()


@router.post("/box/nodes/onboard/remote")
def box_onboard_remote(req: BoxOnboardRemoteRequest):
    """盒子远程一键接入：云端 agent 把 onboard_box.sh 推送到盒子并执行（bash /opt/onboard_box.sh）。

    前提：云端 agent config.json 已配置 edge（盒子可达地址）；或本请求带 boxIP/凭据覆盖。
    盒子无直达 IP 时返回友好错误，指引改用「下载脚本 → 现场执行」。"""
    return box_console.box_onboard_remote(req.model_dump())


@router.get("/box/onboard/github-config")
def box_github_config():
    """GitHub 托管配置（owner/repo/branch/token 是否已设置）。"""
    return github_deploy.get_config()


@router.post("/box/onboard/github-config")
def box_github_config_save(req: GitHubConfigRequest):
    """保存 GitHub 托管配置（token 留空表示沿用已保存值，存在本地文件 chmod 600）。"""
    return github_deploy.save_config(req.model_dump())


@router.post("/box/onboard/github-push")
def box_github_push(req: GitHubPushRequest):
    """把盒子一键接入资产（引导脚本 + box-deploy 包 + edgecore.yaml + rootCA + token）
    同步到 GitHub 仓库 onboard/ 目录（幂等覆盖）。返回盒子现场命令。"""
    return github_deploy.push_to_github(str(req.cloudIP or "").strip())


@router.get("/box/nodes/onboard/config-export")
def box_onboard_config_export(hostname: str = "", cloudIP: str = ""):
    """导出盒子现场接入配置文件 box-config.json（配合仓库 onboard_box.sh 使用）。

    场景：现场无平台、无源码，手头只有这份配置文件 ——
      放到盒子 /opt/weight-bridge/box-config.json 后一条命令 curl … | bash 即完成接入。
    """
    return github_deploy.export_box_config(hostname, cloudIP)


@router.get("/box/stats")
def box_stats():
    """云端 Broker 实时统计（$SYS）+ 最近消息流（实时仪表盘数据源）。"""
    return {"stats": box_console.broker_stats(), "messages": box_console.recent_messages()}


@router.post("/box/publish")
def box_publish(req: BoxPublishRequest):
    """发测试消息（向云端 Broker 发布，供仪表盘调试）。"""
    return box_console.publish_test(req.model_dump())
