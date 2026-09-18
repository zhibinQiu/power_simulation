"""data_sources 包：外部数据源（注册到数据中间件，转换后直发云端 Broker）。

架构（用户诉求：外部数据接入 = 注册到中间件服务，由中间件转换后进入平台订阅通道）：
- 平台不直接对接外部协议、不做协议转换；外部数据统一由独立「数据中间件」
  （platform/cloud-deploy/middleware/）采集并转换为标准 MQTT，直发**云端 Broker**，
  与一体机数据同 Broker 按前缀区分——平台经唯一入口（云端 Broker 订阅）取数。
- 平台 external 条目 = 一条「已注册到中间件的数据源」：
    config.box     发布前缀（平台按此前缀识别归属、启停过滤；中间件 adapter 同前缀）
    config.adapter 中间件适配器类型（当前：mqtt）
    config.params  该类型专属参数（如 broker/topics）
    （历史 config.target「自动关联仿真设备」已取消：设备与仿真工序的关联一律由用户
      在平台手动建立，自动关联会在改绑后反复抢占，语义不可控）
- 生命周期操作（新增/修改/启停/删除）全部转发到中间件管理 API（middleware_client），
  平台本地仅保留目录登记（用于归属识别与关联仿真）。
- 运行状态 = 中间件适配器运行状态（running/readings/errors）+ 平台摄取侧统计
  （received/last_at/cloud_devices），二者合并后回传给前端。
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, Optional

from .. import middleware_client
from ..mqtt_source import _shared as mqtt_shared
from .config import ADAPTERS

# box 前缀约定（与 mqtt_source 识别/盒子分组共用）：ext- 开头便于从盒子卡片区分
_PREFIX_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")
# 保留名（历史内置模拟源 sim 已移除，不再保留）
RESERVED = ("box", "platform", "local", "data", "cloud", "state", "cmd", "$sys")

# 外部源「活跃」判定窗口：最近收到消息距今超过该秒数视为静默（中间件可能未运行）
ACTIVE_WINDOW = 60.0


def validate_external_config(cfg: Dict[str, Any], source_id: str = "",
                             sources: Optional[list] = None) -> None:
    """校验外部源登记配置；非法抛 ValueError。"""
    if not isinstance(cfg, dict):
        raise ValueError("外部源配置必须是 JSON 对象")
    box = str(cfg.get("box") or "").strip().lower().replace(" ", "-")
    if not box:
        raise ValueError("发布前缀（box，如 ext-weigh）不能为空")
    if box in RESERVED:
        raise ValueError(f"前缀「{box}」为平台保留名，请用 ext- 开头的前缀（如 ext-weigh）")
    if not _PREFIX_RE.match(box):
        raise ValueError("前缀仅允许小写字母/数字/连字符（如 ext-weigh）")
    adapter = str(cfg.get("adapter") or "mqtt").strip().lower()
    if adapter not in ADAPTERS:
        raise ValueError(f"不支持的接入类型「{adapter}」（可用：{'、'.join(ADAPTERS)}）")
    params = cfg.get("params")
    if params is not None and not isinstance(params, dict):
        raise ValueError("接入参数（params）必须是 JSON 对象")
    # 唯一性：不同外部源不能共用同一前缀（否则平台无法区分归属与启停过滤）
    for s in (sources or []):
        if not isinstance(s, dict):
            continue
        if s.get("id") == source_id:
            continue
        if str((s.get("config") or {}).get("box") or "").lower() == box:
            raise ValueError(f"前缀「{box}」已被数据源「{s.get('name')}」登记，请换一个")
    return None


def normalize_external_config(cfg: Dict[str, Any], source_id: str,
                              sources: Optional[list] = None) -> Dict[str, Any]:
    """规范化并校验外部源登记结构；返回清洗后的 config。"""
    if not isinstance(cfg, dict):
        cfg = {}
    box = str(cfg.get("box") or "").strip().lower().replace(" ", "-")
    if not box:
        box = str(source_id).replace("_", "-")
    params = cfg.get("params")
    if not isinstance(params, dict):
        params = {}
    base = {
        "box": box,
        "adapter": str(cfg.get("adapter") or "mqtt").strip().lower(),
        "params": params,
        "desc": str(cfg.get("desc") or "").strip()[:200],
    }
    validate_external_config(base, source_id, sources=sources)
    return base


def middleware_payload(source: Dict[str, Any]) -> Dict[str, Any]:
    """目录条目 → 中间件注册请求体（id/type/name/box/enabled + 类型专属参数）。"""
    cfg = source.get("config") or {}
    params = cfg.get("params") if isinstance(cfg.get("params"), dict) else {}
    return {
        "id": source.get("id"),
        "type": str(cfg.get("adapter") or "mqtt"),
        "name": source.get("name") or source.get("id"),
        "box": str(cfg.get("box") or ""),
        "enabled": bool(source.get("enabled") is not False),
        **params,
    }


# ---------------------------------------------------------------------------
# 状态（摄取侧统计 + 中间件运行状态）
# ---------------------------------------------------------------------------

def _status_snapshot(prefix: str, enabled: bool,
                     mw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """把「平台摄取侧统计」与「中间件适配器运行状态」合并为数据源状态视图。

    mw 为中间件侧该数据源的实时状态（不可达时为 None）。
    """
    now = time.time()
    with mqtt_shared._LOCK:
        stats = dict(mqtt_shared._EXT_STATS.get(prefix) or {})
        cloud_devices = sum(1 for i in mqtt_shared.CLOUD_DEVICES.values()
                            if str(i.get("box") or "") == prefix)
    received = int(stats.get("received") or 0)
    last_at = stats.get("last_at")
    active = bool(received and last_at and (now - float(last_at)) <= ACTIVE_WINDOW)
    stale = bool(received and last_at and not active)

    mw_status = (mw or {}).get("status") or {}
    mw_running = bool(mw_status.get("running"))
    mw_missing = mw is None           # 中间件不可达，无法判断
    mw_absent = mw is not None and not mw  # 中间件可达但无此源

    # 总体健康：先看中间件侧是否真在跑，再看平台是否真收到数据
    if mw_absent:
        note = "中间件未注册该数据源（可能已被清理，可重新保存以同步）"
    elif mw_missing:
        note = "中间件服务不可达，无法确认采集状态"
    elif not enabled:
        note = "已停用（中间件已停止采集）"
    elif mw_running and active:
        note = ""
    elif mw_running and not received:
        note = "中间件采集已启动，等待首条数据…"
    elif mw_running and stale:
        note = "中间件采集运行中，但平台最近未收到数据（检查中间件输出/平台订阅）"
    else:
        note = "中间件未运行该数据源（检查中间件服务与适配器状态）"

    return {
        "kind": "external",
        "label": "外部数据源（注册到数据中间件，转换后经平台订阅通道按前缀识别）",
        "enabled": enabled,
        "running": mw_running,
        "active": active,
        "connected": bool(mw_running or active),
        "mw_online": not mw_missing and not mw_absent,
        "mw_status": mw_status,
        "received": received,
        "last_at": last_at,
        "last_msg": stats.get("last_msg"),
        "last_topic": stats.get("last_topic"),
        "cloud_devices": cloud_devices,
        "note": note,
    }


def status_of(source_id: str, mw_map: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """外部源运行状态（摄取侧统计 + 中间件运行状态）。

    mw_map：{source_id: 中间件数据源}；为 None 时内部自行查询（批量场景请传入以避免
    逐条 HTTP 请求）。
    """
    from . import config as _config  # 延迟避免循环
    src = _config.entry(source_id)          # 只读查找（零拷贝）
    if src is None:
        return {"running": False, "connected": False, "received": 0,
                "last_error": "未登记", "active": False,
                "cloud_devices": 0, "last_msg": None}
    enabled = bool(src.get("enabled") is not False)
    prefix = str((src.get("config") or {}).get("box") or "") or ""
    if mw_map is None:
        try:
            mw = middleware_client.get_source(source_id)
        except Exception:  # noqa: BLE001
            mw = None
    else:
        mw = mw_map.get(source_id)
    st = _status_snapshot(prefix, enabled, mw)
    st["box"] = prefix
    return st
