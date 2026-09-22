"""云端一键下发/重启/删除（云端 agent HTTP API，替代 SSH）+ 云端/边缘服务重启。

依赖方向：本模块依赖 edge.py（盒子连接配置），被 devices.py 依赖（创建/更新设备后自动同步）。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..integrations import cloud_agent
from .. import mqtt_source
from ._shared import _load_devices, _save_devices
from .edge import check_edge_reachable, edge_config

# k8s 对象名规则（防注入校验，多处使用）
_K8S_NAME_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$")

# systemd 服务重启白名单（云端，经 agent systemctl restart）
_SYSTEMD_ALLOW = {"cloud-agent", "nengtan-cloud-broker", "nengtan-collector", "nengtan-cloud-dashboard"}

# 边缘盒子服务重启白名单（经 agent SSH 到边缘盒子 systemctl restart）
_EDGE_UNIT_ALLOW = {"box-mapper", "edgecore", "box-collector"}


def restart_cloud_workload(kind: str = "deployment", name: str = "cloudcore",
                           namespace: str = "kubeedge") -> Dict[str, Any]:
    """重启云端/边缘服务（默认 cloudcore）：调云端 agent 本地执行（HTTP POST /api/restart）。

    - kind=deployment（默认，cloudcore）：kubectl rollout restart deployment（滚动重启不中断）；
    - kind=pod：kubectl delete pod（Deployment 自动重建）；
    - kind=systemd：systemctl restart 云端服务（白名单：cloud-agent / nengtan-cloud-broker
      / nengtan-collector / nengtan-cloud-dashboard），namespace 忽略；
    - kind=edge：SSH 到边缘盒子 systemctl restart 边缘服务（白名单：box-mapper / edgecore
      / box-collector），namespace 忽略。

    用于 CloudCore 崩溃/边缘 Mapper 掉线时快速恢复。名称按 k8s 命名规则校验防注入。
    """
    if not name or not _K8S_NAME_RE.fullmatch(name):
        return {"ok": False, "error": f"云端对象名不合法：{name}"}
    if kind in ("deployment", "deploy", "pod"):
        if namespace and not _K8S_NAME_RE.fullmatch(namespace):
            return {"ok": False, "error": f"命名空间不合法：{namespace}"}
        return cloud_agent.restart(kind, name, namespace)
    if kind == "systemd":
        if name not in _SYSTEMD_ALLOW:
            return {"ok": False, "error": f"systemd 服务不在白名单：{name}（仅支持 {'/'.join(sorted(_SYSTEMD_ALLOW))}）"}
        return cloud_agent.restart("systemd", name, "")
    if kind == "edge":
        if name not in _EDGE_UNIT_ALLOW:
            return {"ok": False, "error": f"边缘服务不在白名单：{name}（仅支持 {'/'.join(sorted(_EDGE_UNIT_ALLOW))}）"}
        # 盒子运行期无直达 IP：重启 Mapper 必须配置可达地址（现场内网/跳板机/frp），
        # IP 为空或 SSH 探测不通时拒绝重启，避免无意义下发
        edge_cfg = edge_config().get("edge") or {}
        host = str(edge_cfg.get("host") or "").strip()
        if not host:
            return {"ok": False, "error": "未配置盒子 IP（在盒子卡片上填写现场可达地址后重试），拒绝重启 %s" % name}
        check = check_edge_reachable(host=host, port=int(edge_cfg.get("port") or 22))
        if not check.get("reachable"):
            return {"ok": False, "error": "盒子 IP 不通（%s），拒绝重启 %s：%s"
                    % (host, name, check.get("error", "SSH 不可达"))}
        return cloud_agent.restart("edge", name, "", edge=edge_cfg)
    return {"ok": False, "error": f"kind 不合法：{kind}（仅支持 deployment / pod / systemd / edge）"}


def cloud_config() -> Dict[str, Any]:
    """云端部署配置：agent 主机/端口/token + 命名空间（数据通道替代 SSH）。

    主机地址默认复用云端 Broker 配置中的 host（broker 即部署于云端，无需再单独配置 IP），
    仅在 box_devices.json 顶层 cloud.host 显式设置时优先使用该值。
    """
    data = _load_devices()
    c = data.get("cloud") or {}
    broker_host = mqtt_source.get_config().get("broker", {}).get("host", "") if mqtt_source else ""
    return {
        "host": (c.get("host") or "").strip() or broker_host or "36.151.146.71",
        "agent_port": int(c.get("agent_port", 42083)),
        "agent_token": c.get("agent_token", ""),
        "namespace": c.get("namespace", "default"),
    }


def update_cloud_config(p: Dict[str, Any]) -> Dict[str, Any]:
    """保存云端 agent 连接配置（agent_port/agent_token/namespace）到 box_devices.json 顶层 cloud。"""
    data = _load_devices()
    c = data.get("cloud") or {}
    if p.get("host"):
        c["host"] = str(p.get("host") or "").strip()
    if p.get("agent_port"):
        try:
            c["agent_port"] = int(p["agent_port"])
        except (TypeError, ValueError):
            raise ValueError(f"agent 端口不合法：{p.get('agent_port')}")
    if "agent_token" in p:
        c["agent_token"] = str(p.get("agent_token") or "").strip()
    if p.get("namespace"):
        c["namespace"] = str(p.get("namespace") or "default").strip()
    data["cloud"] = c
    _save_devices(data)
    return {"ok": True, "cloud": cloud_config()}


def apply_devices_to_cloud(device_name: Optional[str] = None, dry_run: bool = False,
                           model_name: Optional[str] = None) -> Dict[str, Any]:
    """一键下发：调云端 agent 本地执行 kubectl apply -f -（HTTP POST /api/apply）。

    支持三种粒度：
    - model_name：下发该模型 + 引用它的所有设备（模型点位修改后对同模型所有设备同时生效）
    - device_name：单设备
    - 都为空：下发全部设备（每个设备带上其模型文档，模型在前保证依赖顺序）
    dry_run=True 时不执行下发，仅返回即将下发的 YAML 内容（前端预览）。
    """
    cfg = cloud_config()
    host = cfg["host"]
    data = _load_devices()
    models = {m.get("name"): m for m in data.get("models", []) if m.get("yaml")}
    devices = data.get("devices", [])
    if model_name:
        devices = [d for d in devices if d.get("model") == model_name]
    elif device_name:
        devices = [d for d in devices if d.get("name") == device_name]

    docs, applied, missing = [], [], []
    for d in devices:
        name, model = d.get("name"), d.get("model")
        if model in models and d.get("yaml"):
            docs.append(models[model]["yaml"].rstrip("\n") + "\n---\n" + d["yaml"].rstrip("\n"))
            applied.append(f"{model} + {name}")
        else:
            missing.append(name)
    if not docs:
        return {"ok": False, "error": "没有可下发的设备（缺模型或本地 YAML）：" + ",".join(missing)}

    payload = "\n---\n".join(docs) + "\n"
    if dry_run:
        return {"ok": True, "dry_run": True, "payload": payload,
                "applied": applied, "missing": missing,
                "target": f"cloud-agent@{host}:{cfg['agent_port']}  kubectl apply -f -"}

    res = cloud_agent.apply(payload)
    return {
        "ok": bool(res.get("ok")),
        "rc": res.get("rc", 1),
        "stdout": res.get("stdout", ""),
        "stderr": res.get("stderr", ""),
        "payload": payload,
        "applied": applied,
        "missing": missing,
    }


def _k8s_name_equal(a: str, b: str) -> bool:
    """判断两个名字在 K8s 里是否指向同一对象（大小写/下划线 ↔ 连字符 归一化后相同）。

    kubectl delete 与 apply 都按对象名定位，若改名只是「shuitong_temp → shuitong-temp」这类
    等价写法，删除旧名会把刚下发的设备一起删掉，改名后设备凭空消失。
    """
    def _norm(v: str) -> str:
        return (v or "").strip().lower().replace("_", "-").replace(".", "-")
    return bool(_norm(a)) and _norm(a) == _norm(b)


def _applied_device_confirmed(res: Dict[str, Any], device_name: str) -> bool:
    """从 kubectl apply 输出确认目标 Device 文档确实被应用（created/configured/unchanged）。"""
    out = "\n".join([str(res.get("stdout") or ""), str(res.get("stderr") or "")])
    token = f"device.devices.kubeedge.io/{device_name}"
    for line in out.splitlines():
        line = line.strip()
        if token in line and any(k in line for k in ("created", "configured", "unchanged", "serverside-applied")):
            return True
    return False


def _cloud_device_exists(name: str, namespace: str = "default") -> bool:
    """查询云端 CRD 列表确认该 Device 已存在（force 拉取，30s 节流）。"""
    try:
        crds = cloud_agent.crds(force=True)
    except Exception:  # noqa: BLE001
        return False
    if not crds.get("ok"):
        return False
    for d in crds.get("devices") or []:
        if str(d.get("name") or "") == name:
            return True
    return False


def _old_name_still_used(old: str, exclude: str = "") -> bool:
    """旧设备名是否仍被本地其它设备占用（设备名或云端绑定标识）。

    读不到配置时保守返回 True（不删除），避免误删仍在使用的云端设备。
    """
    try:
        data = _load_devices()
    except Exception:  # noqa: BLE001
        return True
    for d in data.get("devices") or []:
        name = str(d.get("name") or "")
        if exclude and name == exclude:
            continue
        if name == old or str(d.get("cloudDevice") or "").strip() == old:
            return True
    return False


def _auto_sync_cloud(device_name: str, namespace: str = "default", renamed_from: str = "",
                     extra_devices: "Optional[List[str]]" = None) -> Dict[str, Any]:
    """本地保存配置后自动同步云端（保存即下发，云端及时同步）。

    - 下发该设备（含其模型文档）到云端 K3s（kubectl apply）；
    - extra_devices：本次被连带重刷 YAML 的其它设备（模型点位变更会重刷同模型所有设备），
      一并发下，避免「本地 YAML 已变、云端仍是旧配置」的一致性漂移；
    - 改名场景（renamed_from 非空且 != device_name）：**先确认新设备已在云端生效**再联动删除
      云端旧名 CRD。确认不到就保留旧设备（宁可残留，不可让设备云端身份丢失导致实时数据断链）。

    云端不可达/下发失败时本地配置不受影响，仅返回失败信息供前端提示。
    """
    try:
        res = apply_devices_to_cloud(device_name=device_name)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"云端同步异常：{e}"}
    if not res.get("ok"):
        return {
            "ok": False,
            "error": (res.get("error") or res.get("stderr") or res.get("stdout") or "云端同步失败").strip(),
        }
    sync: Dict[str, Any] = {"ok": True, "applied": list(res.get("applied") or [])}
    # 连带设备（同模型被重刷 YAML 的其它设备）一并发下，保证本地/云端一致
    for extra in [x for x in (extra_devices or []) if x and x != device_name]:
        try:
            er = apply_devices_to_cloud(device_name=extra)
        except Exception as e:  # noqa: BLE001
            sync.setdefault("extra_errors", {})[extra] = f"云端同步异常：{e}"
            continue
        if er.get("ok"):
            sync["applied"].extend(er.get("applied") or [])
        else:
            sync.setdefault("extra_errors", {})[extra] = (
                er.get("error") or er.get("stderr") or er.get("stdout") or "云端同步失败").strip()
    if renamed_from and renamed_from != device_name:
        if _k8s_name_equal(renamed_from, device_name):
            sync["old_crd_removed"] = False
            sync["old_crd_kept"] = renamed_from
            sync["old_crd_reason"] = "新旧名称在 K8s 中是同一对象，已跳过删除（避免把刚下发的设备删掉）"
        elif not (_applied_device_confirmed(res, device_name) or _cloud_device_exists(device_name, namespace)):
            sync["old_crd_removed"] = False
            sync["old_crd_kept"] = renamed_from
            sync["old_crd_reason"] = (
                f"云端未确认新设备「{device_name}」已生效，已保留旧设备「{renamed_from}」"
                "（避免改名后设备丢失）")
        elif _old_name_still_used(renamed_from, exclude=device_name):
            sync["old_crd_removed"] = False
            sync["old_crd_kept"] = renamed_from
            sync["old_crd_reason"] = f"旧名称「{renamed_from}」仍被其它设备引用，已保留其云端设备"
        else:
            del_r = _cloud_delete_crds("device", renamed_from, namespace)
            sync["old_crd_removed"] = bool(del_r.get("ok"))
            if not del_r.get("ok"):
                sync["old_crd_error"] = del_r.get("error") or del_r.get("stderr") or "旧 CRD 删除失败"
    return sync


def _cloud_delete_crds(kind: str, name: str, namespace: str) -> Dict[str, Any]:
    """调云端 agent 删除真实 CRD（agent 本地 kubectl delete device|devicemodel，HTTP POST /api/delete）。

    --ignore-not-found 保证幂等（云端对象不存在不报错）；对象名按 k8s 命名规则校验防注入。
    """
    if not _K8S_NAME_RE.fullmatch(name):
        return {"ok": False, "error": f"云端对象名不合法：{name}"}
    if namespace and not _K8S_NAME_RE.fullmatch(namespace):
        return {"ok": False, "error": f"命名空间不合法：{namespace}"}
    if kind not in ("device", "model", "both"):
        return {"ok": False, "error": f"kind 不合法：{kind}"}
    return cloud_agent.delete(kind, name, namespace)
