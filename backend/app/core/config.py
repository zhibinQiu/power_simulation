"""配置中心（core/config）：统一路径解析。

集中声明配置/数据目录路径，避免各业务模块各自拼接：
- config_path()：拼接 backend/config/ 下的文件路径；
- data 目录路径（DATA_DIR）供需要写数据文件的模块复用。
"""
from __future__ import annotations

import os

# ------------------------- 目录路径 -------------------------

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # backend/
CONFIG_DIR = os.path.join(APP_DIR, "config")                                    # backend/config/
DATA_DIR = os.path.join(APP_DIR, "data")                                        # backend/data/


def config_path(*parts: str) -> str:
    """拼接 config 目录下的文件绝对路径：config_path("mqtt.yaml") -> backend/config/mqtt.yaml"""
    return os.path.join(CONFIG_DIR, *parts)
