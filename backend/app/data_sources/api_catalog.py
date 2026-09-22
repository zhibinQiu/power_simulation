"""数据服务接口清单：历史/实时数据查询与指令下发的对外接口自描述。

清单是「接口清单的单一真值源」——每一项都对应一条已实现且已在路由注册的 HTTP 接口，
存在的意义是让第三方/前端不必翻代码就知道有哪些口、如何调用。清单本身不含任何配置：
调用地址在请求到达时按 base_url 现场拼接，部署地址变化无需改动这里。
"""
from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import urlencode

_PREFIX = "/api"

# 分组 id 与顺序对外稳定：前端按 id 渲染，重排只改本常量的顺序
_GROUPS: List[Dict[str, Any]] = [
    {
        "id": "history",
        "name": "历史数据查询",
        "desc": "按时间窗口从云端时序库取已入库的读数（降采样序列，用于趋势曲线与统计）",
        "items": [
            {
                "name": "时序库历史读数",
                "method": "GET",
                "path": "/box/cloud/tsdb/history",
                "desc": "按 box/设备/点位查云端 TDengine 的历史读数，返回 [{t, v}]；"
                        "设备改名不断链——身份按硬件唯一 ID（hwId）匹配，传显示名同样查得到。",
                "params": [
                    {"name": "box", "required": True, "desc": "盒子标识（node，如 nt001）", "example": "nt001"},
                    {"name": "device", "required": False, "desc": "设备名或 hwId", "example": ""},
                    {"name": "instance", "required": False, "desc": "设备实例名（默认同设备名）", "example": ""},
                    {"name": "prop", "required": False, "desc": "点位名（property 为同义别名）", "example": ""},
                    {"name": "start", "required": False, "desc": "起始时间，毫秒戳或 YYYY-MM-DD HH:MM:SS", "example": ""},
                    {"name": "end", "required": False, "desc": "结束时间（缺省当前）", "example": ""},
                    {"name": "points", "required": False, "desc": "目标点数，默认 500，上限 2000", "example": "500"},
                ],
            },
        ],
    },
    {
        "id": "realtime",
        "name": "实时数据查询",
        "desc": "取当下最新读数（不经时序库，直读平台实时通道：云端 CRD twins / MQTT 订阅数据）",
        "items": [
            {
                "name": "设备实时读数",
                "method": "GET",
                "path": "/box/devices/realtime",
                "desc": "全部设备的最新读数与近期趋势（云端 CRD 上报为主链路，MQTT 为兜底通道）。",
                "params": [],
            },
            {
                "name": "可绑定信号目录",
                "method": "GET",
                "path": "/data-sources/signals",
                "desc": "按数据源分组列出正在上报的设备及其全部数值，每条给出稳定 key（box/device/field）。",
                "params": [],
            },
            {
                "name": "云端已下发资源",
                "method": "GET",
                "path": "/box/devices/cloud",
                "desc": "云端 K3s 上真实存在的 Device/DeviceModel（每 5s 由云端推送刷新），"
                        "用于核对平台配置与云端实际生效是否一致。",
                "params": [
                    {"name": "force", "required": False, "desc": "true 时绕过缓存即时向云端拉取", "example": "false"},
                ],
            },
        ],
    },
    {
        "id": "command",
        "name": "指令下发",
        "desc": "向盒子/云端下发配置或指令；所有下发都是改配置即执行，无需再触发额外的同步动作",
        "items": [
            {
                "name": "保存采集设备（含改名）",
                "method": "POST",
                "path": "/box/devices",
                "desc": "新建或修改采集设备：每台设备各自持有链路参数（串口/从站号/DevEUI 等），"
                        "保存即自动同步云端 CRD 与盒子 mapper；带 origName 即改名，hwId 继承、历史不断链。",
                "params": [],
                "body": {
                    "deviceName": "shuitong-temp", "origName": "", "modelName": "lora-temp-model",
                    "protocol": "lora", "mode": "apply",
                    "lora": {"devEUI": "0120560100000245", "slaveId": 7}, "properties": [],
                },
            },
            {
                "name": "删除采集设备",
                "method": "POST",
                "path": "/box/devices/delete",
                "desc": "删除设备/模型：本地配置、云端 CRD、盒子取数配置同步清理，"
                        "盒子不再对该设备下发取数指令（避免平台上没有的幽灵数据）。",
                "params": [],
                "body": {"kind": "device", "name": "shuitong-temp", "cloud": True, "local": True},
            },
            {
                "name": "下发云端 CRD",
                "method": "POST",
                "path": "/box/devices/apply",
                "desc": "把平台上的设备/模型 YAML 经云端 agent 执行 kubectl apply 落到 K3s；"
                        "dry_run=true 只返回待下发 YAML 供核对。",
                "params": [],
                "body": {"name": "shuitong-temp", "model_name": "", "dry_run": False},
            },
            {
                "name": "下发盒子取数配置",
                "method": "POST",
                "path": "/box/lora/sync",
                "desc": "把每台设备各自的问帧推到盒子 mapper（同名覆盖，平台已无的条目停采）；"
                        "日常无需调用——保存设备已自动下发，此口用于手工补推与对账。",
                "params": [],
                "body": {"box": "nt001", "dry_run": False},
            },
            {
                "name": "盒子应用指令",
                "method": "POST",
                "path": "/box/apps/cmd",
                "desc": "经云端 Broker 向盒子的部署服务下发指令，盒子回报执行回执；"
                        "cmd 取值 deploy / start / stop / restart / remove / list。",
                "params": [],
                "body": {"box": "nt001", "cmd": "list"},
            },
            {
                "name": "向 Broker 发布消息",
                "method": "POST",
                "path": "/box/publish",
                "desc": "向云端 Broker 的任意主题发布一条消息（联通性测试、第三方以标准 data/ 主题回灌读数）；"
                        "payload 为字符串，回灌读数时写 JSON 文本。",
                "params": [],
                "body": {"topic": "data/nt001/demo/demo/temperature", "payload": '{"value": 23.5}'},
            },
            {
                "name": "重启服务",
                "method": "POST",
                "path": "/box/cloud/restart",
                "desc": "重启云端或边缘侧服务（kind=deployment/pod/systemd/edge），用于运维自愈。",
                "params": [],
                "body": {"kind": "edge", "name": "box-mapper"},
            },
        ],
    },
]


def _example_url(item: Dict[str, Any], base_url: str) -> str:
    """拼可直接访问的完整 URL：GET 把带示例值的参数放进 query。"""
    url = "%s%s%s" % (base_url, _PREFIX, item["path"])
    query = {p["name"]: p["example"] for p in (item.get("params") or [])
             if str(p.get("example") or "") != ""}
    return "%s?%s" % (url, urlencode(query)) if query else url


def _item_view(item: Dict[str, Any], base_url: str) -> Dict[str, Any]:
    """渲染一项接口：方法、路径、参数与调用示例（GET 给 URL，POST 给请求体）。"""
    out = {
        "name": item["name"], "method": item["method"], "path": _PREFIX + item["path"],
        "desc": item.get("desc") or "", "params": item.get("params") or [],
        "url": _example_url(item, base_url) if item["method"] == "GET"
               else "%s%s%s" % (base_url, _PREFIX, item["path"]),
    }
    if item["method"] != "GET":
        out["body"] = item.get("body") or {}
    return out


def catalog(base_url: str = "") -> Dict[str, Any]:
    """返回接口清单：{base_url, groups: [{id, name, desc, items: [...]}]}。"""
    base = str(base_url or "").rstrip("/")
    return {
        "ok": True, "base_url": base,
        "groups": [
            {
                "id": g["id"], "name": g["name"], "desc": g.get("desc") or "",
                "items": [_item_view(i, base) for i in (g.get("items") or [])],
            }
            for g in _GROUPS
        ],
    }
