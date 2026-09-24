"""编排方案持久化（design_store）。

背景：流程编排方案（原 localStorage ``sim.scheme``）与 AI 群控编排
（原 localStorage ``nengtan.agc.designs.v1``）此前只存在浏览器本地，换机器 /
换实例打开就回到默认流程，开发机做好的编排推不到服务器。

本模块把这两类编排落到服务端文件 ``backend/data/designs/<bucket>.json``：
- 前端编辑时写入服务端（localStorage 仅作离线兜底）；
- 打开平台时优先取服务端版本，跨端一致；
- 该文件随 ``platform/bs-deploy/update.sh`` 同步到服务器（本地为唯一真源）。

存储形态：``{ "<sceneId>": <payload> }``（按场景分档，切场景不串档）。
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict

from ...core.config import DATA_DIR
from ...core.storage import JsonRepository

# backend/data/designs/
DESIGN_DIR = os.path.join(DATA_DIR, "designs")

# 允许的桶（白名单，避免任意文件读写）
#   flow —— 流程编排方案（stores/sim.js 的 sim.scheme）
#   agc  —— AI 群控编排（PidControlView 的 nengtan.agc.designs.v1）
BUCKETS = ("flow", "agc")

# 场景 id：K8s 风格小写命名，防止被拼成路径
_SCENE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}$")

_repos: Dict[str, JsonRepository] = {}


def _repo(bucket: str) -> JsonRepository:
    repo = _repos.get(bucket)
    if repo is None:
        repo = JsonRepository(os.path.join(DESIGN_DIR, f"{bucket}.json"), default={})
        _repos[bucket] = repo
    return repo


def _norm_scene(scene: str) -> str:
    scene = (scene or "").strip()
    if not scene or not _SCENE_RE.match(scene):
        raise ValueError("场景标识非法（只允许小写字母/数字/._-，且非空）")
    return scene


def design_path(bucket: str) -> str:
    """桶对应的文件绝对路径（供运维/测试定位）。"""
    return os.path.join(DESIGN_DIR, f"{bucket}.json")


def read_bucket(bucket: str) -> Dict[str, Any]:
    """读取整个桶：{ sceneId: payload }；桶名非法 / 文件缺失返回空字典。"""
    if bucket not in BUCKETS:
        raise ValueError(f"未知的编排桶：{bucket}（可选：{', '.join(BUCKETS)}）")
    data = _repo(bucket).read()
    return data if isinstance(data, dict) else {}


def read_scene(bucket: str, scene: str) -> Any:
    """读取某场景下的编排数据；不存在返回 None。"""
    return read_bucket(bucket).get(_norm_scene(scene))


def write_scene(bucket: str, scene: str, payload: Any) -> Dict[str, Any]:
    """写入某场景的编排数据，返回写入后的整桶内容。"""
    if bucket not in BUCKETS:
        raise ValueError(f"未知的编排桶：{bucket}（可选：{', '.join(BUCKETS)}）")
    scene = _norm_scene(scene)

    def _fn(cur: Any) -> Dict[str, Any]:
        data = dict(cur) if isinstance(cur, dict) else {}
        data[scene] = payload
        return data

    return _repo(bucket).mutate(_fn)


def delete_scene(bucket: str, scene: str) -> Dict[str, Any]:
    """删除某场景的编排数据，返回删除后的整桶内容。"""
    scene = _norm_scene(scene)

    def _fn(cur: Any) -> Dict[str, Any]:
        data = dict(cur) if isinstance(cur, dict) else {}
        data.pop(scene, None)
        return data

    return _repo(bucket).mutate(_fn)
