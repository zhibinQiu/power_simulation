"""配置中心（core/config）：唯一路径真相源。

全仓**禁止**再用 `Path(__file__).parent` / `dirname(__file__)` 自行拼接目录：
历史上有两次因模块下沉（app/ 顶层 → app/domain/*）导致相对层级变化、
路径静默漂移的事故（场景注册表读空、报告写进错位目录且被 try/except 吞掉）。
所有目录一律从本模块派生：

- APP_DIR / CONFIG_DIR / DATA_DIR：backend 根目录及其 config/、data/ 子目录；
- PROJECT_DIR：仓库根（backend/ 的上一级），仅用于确实要跨出 backend 的资源
  （如 platform/box-deploy 部署包）；
- config_path() / data_path() / project_path()：拼具体文件。

需要落盘的运行时产物优先放在 DATA_DIR 下（data/ 由运维备份），
config/ 只放配置（会被部署脚本同步覆盖）。
"""
from __future__ import annotations

import os

# ------------------------- 目录路径 -------------------------

# backend/ —— core/config.py 位于 backend/app/core/，需上溯三层到仓库中的 backend 根目录
APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = os.path.join(APP_DIR, "config")                                    # backend/config/
DATA_DIR = os.path.join(APP_DIR, "data")                                        # backend/data/
PROJECT_DIR = os.path.dirname(APP_DIR)                                          # 仓库根（含 platform/、frontend/）


def config_path(*parts: str) -> str:
    """拼接 config 目录下的文件绝对路径：config_path("box_config.json") -> backend/config/box_config.json"""
    return os.path.join(CONFIG_DIR, *parts)


def data_path(*parts: str) -> str:
    """拼接 data 目录下的文件绝对路径：data_path("reports", "index.json") -> backend/data/reports/index.json"""
    return os.path.join(DATA_DIR, *parts)


def project_path(*parts: str) -> str:
    """拼接仓库根下的路径（跨出 backend 时使用）：project_path("platform", "box-deploy")"""
    return os.path.join(PROJECT_DIR, *parts)
