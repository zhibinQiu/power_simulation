"""环境变量加载（基础设施层）。

本地直接运行（run.sh / uvicorn）时，docker-compose 注入的密钥类环境变量不会进入进程环境；
本模块从 ``backend/config/.env`` 与项目根 ``.env`` 读取并补进 ``os.environ``，
保证「本地启动」与「容器启动」配置来源一致。

约定：
- 仅补充**进程环境中尚不存在**的键，不覆盖已有环境变量（容器注入优先级最高）；
- 导入本模块即完成一次加载（幂等，重复导入无副作用）；
- 仅依赖标准库，供各业务模块共用，避免每个模块各自实现一份 .env 解析。
"""
from __future__ import annotations

import os

# 按优先级从高到低查找 .env：backend/config/.env > backend/.env > 仓库根 .env
# 本文件位于 backend/app/core/env.py，向上三级即 backend/
_APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CANDIDATES = (
    os.path.join(_APP_DIR, "config", ".env"),
    os.path.join(_APP_DIR, ".env"),
    os.path.join(os.path.dirname(_APP_DIR), ".env"),
)

_loaded = False


def load_dotenv(force: bool = False) -> bool:
    """把 .env 中的键值补进 ``os.environ``（已存在的键不覆盖）。

    返回是否成功读取到某个 .env 文件。默认只执行一次（幂等）。
    """
    global _loaded
    if _loaded and not force:
        return True
    _loaded = True
    for cand in _CANDIDATES:
        if not os.path.isfile(cand):
            continue
        try:
            with open(cand, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and k not in os.environ:
                        os.environ[k] = v
        except Exception:  # noqa: BLE001 —— .env 损坏不阻断启动
            pass
        return True
    return False


# 导入即加载：业务模块只需 ``from .core import env  # noqa: F401`` 即可拿到 .env 配置
load_dotenv()
