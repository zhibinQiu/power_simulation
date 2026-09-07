"""data_sources 包：统一数据源接入管理（门面 Facade）。

统一概念（用户诉求：能碳一体机接入 / 外部数据源 都是「一种数据源接入」）：
平台把每个向它提供实时数据的来源登记为一条数据源（id/type/name/enabled），统一列表、
统一启停、统一状态；所有源最终都汇入同一条摄取管道（订阅 → CLOUD_DEVICES/READINGS
→ links 关联 → 驱动仿真）：
- box       能碳一体机（KubeEdge 盒子）：数据经**云端 Broker** 主动上报，平台无独立
            运行线程；enabled 控制摄取侧是否采纳真实盒子消息。
- external  外部数据源：注册到**数据中间件**（platform/cloud-deploy/middleware/），
            由中间件采集并转换为标准 MQTT 发布到云端 Broker，平台按 box 前缀识别归属。
            模拟数据也是一种外部源：由独立服务（platform/cloud-deploy/sim-source/）
            生成后经中间件 mqtt 适配器接入——**平台与中间件自身都不产生模拟数据**。

平台订阅入口（见 mqtt_source.client）：cloud（云端 Broker：一体机 + external 形态下的
外部数据）+ middleware（可选：local 形态下单独订阅中间件端口，external 形态停用），
共享同一条摄取管道，按 box 前缀归属到具体数据源条目。

生命周期：main.py lifespan 调 start()（登记默认源 + 与中间件对账同步）与退出调 stop()；
REST（/api/data-sources/*）热增删改启停。
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List

from . import config as _config
from . import external as _external
from .. import middleware_client

_lock = threading.RLock()

TYPE_LABELS = {
    "box": "能碳一体机",
    "external": "外部数据源",
}
TYPE_DESC = {
    "box": "能碳一体机云端（默认接入）：KubeEdge 盒子/传感器经云端 Broker 主动上报，平台订阅摄取后经关联驱动仿真",
    "external": "外部数据源注册到数据中间件，由中间件采集并转换为标准 MQTT 发布到云端 Broker，平台按 box 前缀识别归属（模拟数据由独立服务生成后经中间件接入）",
}

def sync_with_middleware() -> Dict[str, Any]:
    """与中间件对账：把本地已登记但中间件缺失的外部源补注册（中间件重建后恢复）。

    返回 {ok, checked, registered, errors, online}。中间件不可达时不报错，仅标记。
    """
    from .. import mqtt_source
    out: Dict[str, Any] = {"ok": True, "checked": 0, "registered": 0, "errors": [],
                           "online": False}
    st = middleware_client.status(force=True)
    out["online"] = bool(st.get("online"))
    if not out["online"]:
        out["ok"] = False
        out["errors"].append(st.get("error") or "中间件服务不可达")
        return out
    try:
        mw_ids = {str(s.get("id")) for s in middleware_client.list_sources()}
    except Exception as e:  # noqa: BLE001
        out["ok"] = False
        out["errors"].append(str(e))
        return out
    for src in _config.external_configs():
        out["checked"] += 1
        sid = str(src.get("id"))
        if sid in mw_ids:
            continue
        try:
            middleware_client.add_source(_external.middleware_payload(src))
            out["registered"] += 1
        except Exception as e:  # noqa: BLE001
            out["errors"].append(f"{src.get('name')}: {e}")
            out["ok"] = False
    # 中间件地址可能刚变更：刷新订阅端点使新配置生效
    try:
        mqtt_source.restart_middleware()
    except Exception:  # noqa: BLE001
        pass
    return out


def start() -> Dict[str, Any]:
    """登记默认目录（box 缺失时补建）并与中间件对账补注册。"""
    try:
        cfg = _config.load_config(force=True)
        types = {s.get("type") for s in cfg.get("sources") or []}
        if "box" not in types:
            _config.upsert_source({"id": "box", "type": "box",
                                   "name": TYPE_LABELS["box"], "enabled": True})
    except Exception:  # noqa: BLE001
        pass
    sync = {"ok": False, "online": False, "errors": ["未执行"]}
    try:
        sync = sync_with_middleware()
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "sync": sync,
            "sources": [s.get("id") for s in _config.public_sources(force=True)]}


def stop() -> None:
    """平台退出：外部源采集在中间件进程内，平台无需停止（保留目录登记）。"""


# ------------------------- 状态 -------------------------

def _box_status() -> Dict[str, Any]:
    from ..mqtt_source import _shared as ms
    with ms._LOCK:
        st = dict(ms._STATE)
        try:
            from .config import external_configs
            ext_boxes = {str((c.get("config") or {}).get("box") or "").strip().lower()
                         for c in external_configs()}
        except Exception:
            ext_boxes = set()
        # 盒卡只统计一体机盒子设备：外部源（登记前缀 ext-*）设备不混入「云端设备数」
        st["cloud_devices"] = sum(1 for d in ms.CLOUD_DEVICES.values()
                                  if str(d.get("box") or "").strip().lower() not in ext_boxes)
        st["readings"] = len(ms.READINGS)
        st["links"] = len(dict(ms._LINKS))
        st["broker_host"] = ms._BROKER.get("host")
        st["broker_port"] = ms._BROKER.get("port")
        st["topics"] = list(ms._TOPICS)
        st["endpoints"] = ms.endpoint_states()
        # 最近消息只反映一体机（box）数据：外部源（含已停用的模拟源）消息不计入盒卡
        last = None
        for m in reversed(ms.MESSAGE_LOG):
            parts = str(m.get("topic") or "").split("/")
            if len(parts) > 1 and parts[1].strip().lower() in ext_boxes:
                continue
            last = m
            break
    st.pop("recent_messages", None)
    st["last_msg"] = last
    return st


def _status_for(source: Dict[str, Any], mw_map: Dict[str, Any]) -> Dict[str, Any]:
    t = source.get("type")
    if t == "box":
        return _box_status()
    if t == "external":
        st = _external.status_of(str(source.get("id") or ""), mw_map=mw_map)
        st["enabled"] = bool(source.get("enabled") is not False)
        return st
    return {}


def list_sources(force: bool = False) -> Dict[str, Any]:
    """统一数据源列表：目录条目 + 类型文案 + 运行时状态（含中间件服务状态）。"""
    out: List[Dict[str, Any]] = []
    mw_map = _external.mw_sources_map() if _config.external_configs() else {}
    for raw in _config.public_sources(force):
        view = _config.source_public_view(raw)
        t = view.get("type")
        view["label"] = TYPE_LABELS.get(t, t)
        view["desc"] = TYPE_DESC.get(t, "")
        view["status"] = _status_for(raw, mw_map)
        out.append(view)
    return {"ok": True, "sources": out, "middleware": middleware_client.status()}


# ------------------------- 启停 / 保存 / 增删 -------------------------

def _require(source_id: str) -> Dict[str, Any]:
    src = _config.find_source(source_id, force=True)
    if src is None:
        raise ValueError(f"数据源不存在：{source_id}")
    return src


def toggle(source_id: str, enabled: bool) -> Dict[str, Any]:
    """启停某数据源（box 影响摄取过滤；external 同时启停中间件适配器）。"""
    with _lock:
        src = _require(source_id)
        t = src.get("type")
        enabled = bool(enabled)
        if t == "box":
            src["enabled"] = enabled
            _config.upsert_source(src)
            return {"ok": True,
                    "note": f"「能碳一体机」数据源已{'启用' if enabled else '停用'}"
                            f"（{'盒子实时数据恢复驱动仿真' if enabled else '盒子实时数据不再驱动仿真；外部数据源不受影响'}）"}
        if t == "external":
            # 先改中间件（采集实际执行方），成功再落本地目录
            middleware_client.set_enabled(source_id, enabled)
            src["enabled"] = enabled
            _config.upsert_source(src)
            return {"ok": True,
                    "note": f"外部数据源「{src.get('name')}」已{'启用' if enabled else '停用'}"
                            f"（中间件已{'开始' if enabled else '停止'}采集）",
                    "sources": list_sources(force=True)["sources"]}
        raise ValueError(f"不支持的数据源类型：{t}")


def save(source_id: str, name: str | None = None,
         config: Dict[str, Any] | None = None,
         enabled: bool | None = None) -> Dict[str, Any]:
    """保存数据源配置并热应用（external 同步到中间件；box 无手工配置）。"""
    with _lock:
        src = _require(source_id)
        t = src.get("type")
        if t == "box":
            return {"ok": True, "note": "「能碳一体机」数据源无需手工配置（Broker 在「系统连接图 → 云端配置」中设置）",
                    "sources": list_sources(force=True)["sources"]}
        if t == "external":
            cfg = _external.normalize_external_config(
                config if config is not None else (src.get("config") or {}), source_id,
                sources=_config.external_configs())
            updated = dict(src)
            updated["config"] = cfg
            if name:
                updated["name"] = str(name).strip() or updated.get("name", "外部数据源")
            if enabled is not None:
                updated["enabled"] = bool(enabled)
            # 先同步中间件（参数非法在此抛出，本地不落盘）
            middleware_client.update_source(source_id, _external.middleware_payload(updated))
            _config.upsert_source(updated)
            return {"ok": True, "note": f"外部数据源「{updated.get('name')}」已保存并同步到中间件",
                    "sources": list_sources(force=True)["sources"]}
        raise ValueError(f"不支持的数据源类型：{t}")


def add_external(name: str | None = None,
                 config: Dict[str, Any] | None = None,
                 enabled: bool = False) -> Dict[str, Any]:
    """新增一条外部数据源：本地登记 + 注册到中间件（默认停用，保存后再启用）。"""
    with _lock:
        adapter = "mqtt"
        if isinstance(config, dict):
            adapter = str(config.get("adapter") or config.get("type") or "mqtt").strip().lower()
        src = _config.default_external(name or "", adapter)
        cfg = _external.normalize_external_config(
            config if config is not None else (src.get("config") or {}), src["id"],
            sources=_config.external_configs())
        src["config"] = cfg
        src["enabled"] = bool(enabled)
        # 先注册到中间件（校验/连通在中间件侧完成），成功再落本地目录
        middleware_client.add_source(_external.middleware_payload(src))
        _config.upsert_source(src)
        return {"ok": True, "note": f"已注册外部数据源「{src.get('name')}」到数据中间件",
                "sources": list_sources(force=True)["sources"]}


def remove(source_id: str) -> Dict[str, Any]:
    """删除数据源（仅外部源可删；box 为平台内置不可删除）。"""
    with _lock:
        src = _require(source_id)
        if src.get("type") != "external":
            raise ValueError("平台内置数据源（能碳一体机）不可删除")
        name = src.get("name")
        box = str((src.get("config") or {}).get("box") or "")
        # 先注销中间件侧，再删本地目录（中间件不可达且确为 404 时仍允许清理本地）
        middleware_client.remove_source(source_id)
        _config.remove_source(source_id)
        if box:
            try:
                from ..mqtt_source import _shared as ms
                with ms._LOCK:
                    ms._EXT_STATS.pop(box, None)
            except Exception:  # noqa: BLE001
                pass
        return {"ok": True, "note": f"已删除外部数据源「{name}」（中间件同步注销）",
                "sources": list_sources(force=True)["sources"]}


# ------------------------- 测试连接 / 类型清单 -------------------------

def test_config(config: Dict[str, Any], source_id: str = "") -> Dict[str, Any]:
    """测试外部源接入配置（转发中间件做真实连通性探测，不落盘）。"""
    if not isinstance(config, dict):
        raise ValueError("测试内容必须是 JSON 对象")
    sid = source_id or "probe"
    try:
        cfg = _external.normalize_external_config(config, sid,
                                                  sources=_config.external_configs())
    except ValueError:
        raise
    payload = {
        "id": sid,
        "type": cfg["adapter"],
        "name": "连通性测试",
        "box": cfg["box"],
        "enabled": True,
        **(cfg.get("params") or {}),
    }
    return middleware_client.test_source(payload)


def adapter_types() -> List[Dict[str, Any]]:
    """可用接入类型（取中间件注册表；不可达时回退本地已知类型）。"""
    try:
        types = middleware_client.types()
        if types:
            return types
    except Exception:  # noqa: BLE001
        pass
    return [{"type": "mqtt", "label": "外部 MQTT",
             "desc": "订阅外部 MQTT Broker 的主题（中间件不可达，参数需手工填写）",
             "fields": []},
            {"type": "sim", "label": "模拟数据",
             "desc": "中间件内置生成模拟读数（中间件不可达，参数需手工填写）",
             "fields": []}]
