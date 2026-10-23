"""编排方案持久化（design_store）。

背景：流程编排方案（原 localStorage ``sim.scheme``）与 AI 群控编排
（原 localStorage ``nengtan.agc.designs.v1``）此前只存在浏览器本地，换机器 /
换实例打开就回到默认流程，开发机做好的编排推不到服务器。

本模块把这两类编排落到服务端文件 ``backend/data/designs/<bucket>.json``：
- 前端编辑时写入服务端（localStorage 仅作离线兜底）；
- 打开平台时以服务端版本为准，跨端一致；
- **该文件是运行期数据，绝不随代码推送同步**（platform/bs-deploy/update.sh 已永久排除
  backend/data/designs/***）：官网实例上的档案就是唯一真源，开发机不得覆盖。

写入采用**整档覆盖**：提交什么就存什么，删除即「不提交该项」，不做条目级合并、
不留删除墓碑（此前那套 removed / deleted / hidden 墓碑已移除）。

存储形态：``{ "<sceneId>": <payload> }``（按场景分档，切场景不串档）。
同目录 ``workspace.json`` 记录全局「最后打开的工程」（见 read/write_last_scene）。
"""
from __future__ import annotations

import os
import re
import shutil
import time
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


def _snapshot_prev(path: str) -> None:
    """写盘前把当前文件复制一份到 ``<path>.prev``（只留最近一版，不累积）。

    编排是整档覆盖写：一旦某端把「按模板重建的默认方案」提交上来，真实编排就被抹掉。
    留一份上一版可在事故后直接回滚（cp flow.json.prev flow.json 即可），
    比翻 designs_sync 的按次备份更快也更贴近「被覆盖前那一刻」。
    """
    try:
        if os.path.exists(path):
            shutil.copyfile(path, path + ".prev")
    except Exception:  # noqa: BLE001 —— 备份失败绝不阻断写入
        pass


def write_scene(bucket: str, scene: str, payload: Any) -> Dict[str, Any]:
    """写入某场景的编排数据，返回写入后的整桶内容。

    整档覆盖（last-writer-wins）：提交什么就存什么，不合并、不留删除墓碑。
    agc / flow 桶唯一的写入方是前端（后台运行器只读），故无需服务端做多端合并。
    """
    if bucket not in BUCKETS:
        raise ValueError(f"未知的编排桶：{bucket}（可选：{', '.join(BUCKETS)}）")
    scene = _norm_scene(scene)
    _snapshot_prev(design_path(bucket))

    def _fn(cur: Any) -> Dict[str, Any]:
        data = dict(cur) if isinstance(cur, dict) else {}
        data[scene] = payload
        return data

    return _repo(bucket).mutate(_fn)


def update_scene_fields(bucket: str, scene: str, fields: Dict[str, Any]) -> bool:
    """只改某场景存档里的指定字段（目前只用于 ``running``），**不动 designs**。

    手动提交模式下的分工：
    - ``designs`` 只在用户点「提交」时整档覆盖（write_scene）；
    - 启停策略只改运行态，属于操作而非编辑 —— 若沿用整档 PUT，
      会把本端内存里「尚未提交的清单」一起推上去覆盖别人。

    返回 False 表示该场景在服务端还没有存档（运行态无处可写，前端提示「先提交」）。
    """
    if bucket not in BUCKETS:
        raise ValueError(f"未知的编排桶：{bucket}（可选：{', '.join(BUCKETS)}）")
    scene = _norm_scene(scene)
    hit = {"ok": False}

    def _fn(cur: Any) -> Dict[str, Any]:
        data = dict(cur) if isinstance(cur, dict) else {}
        old = data.get(scene)
        if not isinstance(old, dict):
            return data
        merged = dict(old)
        merged.update(fields)
        data[scene] = merged
        hit["ok"] = True
        return data

    _repo(bucket).mutate(_fn)
    return hit["ok"]


def delete_scene(bucket: str, scene: str) -> Dict[str, Any]:
    """删除某场景的编排数据，返回删除后的整桶内容。"""
    scene = _norm_scene(scene)

    def _fn(cur: Any) -> Dict[str, Any]:
        data = dict(cur) if isinstance(cur, dict) else {}
        data.pop(scene, None)
        return data

    return _repo(bucket).mutate(_fn)


# ---------------------------------------------------------------- 最后打开的工程
# 平台没有用户体系：所有人在官网共用同一份工作区。此前「当前打开哪个工程」纯靠浏览器
# localStorage，换浏览器就落到默认钢包，于是「在机房温控建的策略，换个浏览器就看不到」。
_WORKSPACE_KEY = "__workspace__"


def _workspace_repo() -> JsonRepository:
    repo = _repos.get(_WORKSPACE_KEY)
    if repo is None:
        repo = JsonRepository(os.path.join(DESIGN_DIR, "workspace.json"), default={})
        _repos[_WORKSPACE_KEY] = repo
    return repo


def read_last_scene() -> Dict[str, Any]:
    """读取全局「最后打开的工程」{ scene, ts, label }；无记录返回 {}。"""
    data = _workspace_repo().read()
    return data if isinstance(data, dict) else {}


def write_last_scene(scene: str, label: str = "") -> Dict[str, Any]:
    """记下最后打开的工程（任何人在官网切换工程都会更新，所有人下一次进来都落到这里）。"""
    scene = _norm_scene(scene)

    def _fn(cur: Any) -> Dict[str, Any]:
        data = dict(cur) if isinstance(cur, dict) else {}
        data.update({"scene": scene, "label": label or scene, "ts": int(time.time() * 1000)})
        return data

    return _workspace_repo().mutate(_fn)
