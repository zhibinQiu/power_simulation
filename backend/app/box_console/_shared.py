"""box_console 包共享内部状态：锁、twins 趋势缓冲、设备/模型/云端配置统一仓储、路径常量。

把原 box_console.py 上帝模块的模块级共享状态收敛到此模块，
子模块（overview/devices/cloud_ops/edge/realtime_data/onboard/broker_config）单向依赖本模块，
避免子模块间循环导入，实现「高内聚、单向依赖」。
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, List

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
