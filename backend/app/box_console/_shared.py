"""box_console 包共享内部状态：锁、twins 趋势缓冲、设备/模型/云端配置统一仓储、路径常量。

把原 box_console.py 上帝模块的模块级共享状态收敛到此模块，
子模块（overview/devices/cloud_ops/edge/realtime_data/onboard/broker_config）单向依赖本模块，
避免子模块间循环导入，实现「高内聚、单向依赖」。
"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.storage import JsonRepository

# __file__ = backend/app/box_console/_shared.py
# parents[0]=app/box_console  parents[1]=app  parents[2]=backend  parents[3]=project root
CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
DEVICES_FILE = CONFIG_DIR / "box_devices.json"
EDGECORE_TEMPLATE = CONFIG_DIR / "edgecore.template.yaml"
# 一键接入包输出目录与文件（平台侧生成，供下载 / 远程推送）
GENERATED_DIR = Path(__file__).resolve().parents[2] / "generated"
ONBOARD_SCRIPT_PATH = GENERATED_DIR / "onboard_box.sh"
# box-deploy 采集部署包（打包内嵌进一键接入脚本，免除现场手工上传）
BOX_DEPLOY_DIR = Path(__file__).resolve().parents[3] / "platform" / "box-deploy"

_LOCK = threading.Lock()
# 设备 twins 趋势历史：dev_id -> [(epoch, value)]
_TWIN_HISTORY: Dict[str, List[Dict[str, Any]]] = {}
_TWIN_HISTORY_MAX = 120

# 设备/模型/云端配置统一仓储（原子写盘 + 内存缓存，替代手工 json 读写）
_devices_repo = JsonRepository(str(DEVICES_FILE), default={"models": [], "devices": []})


def _load_devices() -> Dict[str, List[Dict[str, Any]]]:
    return _devices_repo.read()


def _save_devices(data: Dict[str, List[Dict[str, Any]]]) -> None:
    _devices_repo.write(data)


# ------------------------- 设备「数据在线」统一判定 -------------------------
# 语义：有实时数据推送才算在线（读不到数据就应显示离线）。双数据通道任一
# 在窗口内更新即在线：① 云端 Device CRD status.twins（边缘 Mapper 经 DMI 上报，
# timestamp 为采集/上报时间）；② 平台订阅的 MQTT data/#（mqtt_source.CLOUD_DEVICES.last_seen）。
# 设备「接入注册」（CRD state=online / edgecore 心跳）不代表有数据，不作为在线依据。
# 窗口与前端 DataOverview 原判定（120s）保持一致。
DATA_FRESH_SECONDS = 120


def parse_crd_ts(ts: Any) -> Optional[float]:
    """解析云端 CRD twins 的 timestamp 为 epoch 秒，失败返回 None。

    实测云端 Device.status.twins 的 timestamp 是「毫秒 epoch 字符串」（如 "1787643075724"），
    同时兼容 ISO 字符串（2026-08-25T07:14:43Z / +08:00）与秒级 epoch。
    """
    if not ts:
        return None
    s = str(ts).strip()
    # 数字：毫秒(13 位)/秒(10 位) epoch
    if s.isdigit():
        try:
            n = int(s)
            return n / 1000.0 if len(s) >= 12 else float(n)
        except Exception:  # noqa: BLE001
            return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s, fmt).timestamp()
        except Exception:  # noqa: BLE001
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:  # noqa: BLE001
        return None


def last_data_ts(twins: List[Dict[str, Any]] = None,
                 cd: Optional[Dict[str, Any]] = None) -> Optional[float]:
    """设备「最后数据时间 = 最后在线时间」（epoch 秒）：CRD twins 各属性最新上报时间戳
    与平台 MQTT data/# last_seen 取最大；两通道均无上报返回 None。"""
    ts_list: List[float] = []
    for t in (twins or []):
        ts = parse_crd_ts(t.get("timestamp", ""))
        if ts:
            ts_list.append(ts)
    if cd:
        ls = cd.get("last_seen")
        if ls:
            try:
                ts_list.append(float(ls))
            except (TypeError, ValueError):
                pass
    return max(ts_list) if ts_list else None


def data_fresh(twins: List[Dict[str, Any]] = None,
               cd: Optional[Dict[str, Any]] = None,
               now: Optional[float] = None):
    """设备是否「在线（有实时数据推送）」：返回 (fresh, last_ts)。

    fresh = 最后数据时间在 DATA_FRESH_SECONDS 窗口内；last_ts 为最后数据/在线时间。
    """
    now = time.time() if now is None else now
    last = last_data_ts(twins, cd)
    return (bool(last) and (now - float(last)) <= DATA_FRESH_SECONDS), last
