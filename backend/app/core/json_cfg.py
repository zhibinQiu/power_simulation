"""通用 JSON 配置存储：内存缓存 + 环境变量覆盖 + 原子落盘。

供 llm_settings / kb_settings 等「动态配置 > 环境变量 > 默认值」优先级模型复用。
高内聚：一个 store 实例封装某个配置的全部读写、内存缓存、环境变量同步逻辑；
低耦合：仅依赖标准库，业务模块持有各自实例即可，无共享全局状态。
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Dict, Optional


class JsonCfgStore:
    """单文件 JSON 配置存储（线程安全）。

    优先级（从高到低）：运行时动态配置（内存 + 落盘）> 环境变量 > 默认值。
    ``save()`` 同时更新内存、原子落盘并同步到 ``os.environ``；
    被 ``save()`` 覆盖过的环境变量由 ``reset()`` 恢复（还原为进程原始环境变量）。
    """

    def __init__(
        self,
        path: Path,
        env_map: Dict[str, str],
        defaults: Optional[Dict[str, str]] = None,
    ):
        self._path = Path(path)
        self._env_map = dict(env_map)  # 配置字段名 -> 环境变量名
        self._defaults = dict(defaults or {})
        self._lock = threading.Lock()
        self._dynamic: Dict[str, str] = {}
        self._overwritten: set = set()

    # ---- 落盘 ----

    def _load_from_disk(self) -> Dict[str, str]:
        """读取磁盘配置（只保留 env_map 中声明的字段，过滤脏数据）。"""
        try:
            if self._path.is_file():
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {
                        k: str(v).strip()
                        for k, v in data.items()
                        if k in self._env_map and str(v).strip()
                    }
        except Exception:  # noqa: BLE001 —— 配置损坏时回退空，不阻断请求
            pass
        return {}

    def _write_to_disk(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(self._dynamic, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self._path)  # 原子替换，避免写坏配置文件
        except Exception:  # noqa: BLE001
            pass

    # ---- 对外 API ----

    def get(self) -> Dict[str, str]:
        """返回合并后的配置：动态配置 > 环境变量 > 默认值。"""
        with self._lock:
            dynamic = dict(self._dynamic)
        if not dynamic:  # 首次访问：磁盘配置一次性载入内存缓存，避免重复读盘
            dynamic = self._load_from_disk()
            if dynamic:
                with self._lock:
                    self._dynamic.update(dynamic)
        cfg = dict(self._defaults)
        for field, env in self._env_map.items():
            env_val = os.getenv(env, "").strip()
            if env_val:
                cfg[field] = env_val
            if dynamic.get(field):
                cfg[field] = dynamic[field]
        return cfg

    def has_dynamic(self, field: str) -> bool:
        """判断某字段是否已被动态配置覆盖（用于 configured 状态展示）。"""
        with self._lock:
            return bool(self._dynamic.get(field))

    def save(self, updates: Dict[str, str]) -> Dict[str, str]:
        """合并保存：None / 空串表示保留当前值，仅更新非空字段。"""
        merged = dict(self.get())
        for k, v in updates.items():
            if k in self._env_map and v is not None and str(v).strip():
                merged[k] = str(v).strip()
        with self._lock:
            self._dynamic.clear()
            self._dynamic.update(merged)
            self._write_to_disk()
            for field, env in self._env_map.items():
                val = merged.get(field, "")
                if os.getenv(env) != val:
                    os.environ[env] = val
                    self._overwritten.add(env)
        return dict(merged)

    def reset(self) -> Dict[str, str]:
        """恢复全部默认：清空动态配置、删除落盘文件、还原覆盖过的环境变量。"""
        with self._lock:
            self._dynamic.clear()
            for env in self._overwritten:
                os.environ.pop(env, None)
            self._overwritten.clear()
        try:
            if self._path.is_file():
                self._path.unlink()
        except Exception:  # noqa: BLE001
            pass
        return self.get()
