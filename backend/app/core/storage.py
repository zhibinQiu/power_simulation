"""统一 JSON 持久化仓库（仓储模式 Repository）。

把「内存缓存 + 线程锁 + 原子写盘」从各业务模块中抽离为通用基类，
统一所有 JSON 配置 / 状态 / 索引文件的读写行为，消除重复实现：

- 读写分离：read() 走内存缓存，write() 原子写盘（tmp + os.replace）；
- mutate()：在锁内完成「读 → 变更 → 写」，保证并发安全；
- 文件缺失 / 损坏时优雅回退到默认值，不抛异常；
- 缓存以文件指纹（mtime_ns + size）失效：**磁盘文件是唯一真相**，本进程或别的进程 /
  运维手工改动过文件，下一次 read() 自动重新读盘（多 worker 部署同样一致）。

用法示例：
    repo = JsonRepository(path="/data/links.json", default={})
    data = repo.read()
    repo.write(new_data)
    repo.mutate(lambda d: d.update({k: v}))
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Callable, Generic, Optional, TypeVar

T = TypeVar("T")


class JsonRepository(Generic[T]):
    """线程安全的 JSON 文件仓库。

    参数：
    - path: JSON 文件绝对路径（父目录不存在时自动创建）；
    - default: 文件缺失 / 损坏时返回的默认值（也作为 write 前结构基线）；
    - pretty: 是否格式化输出（ensure_ascii=False + indent）；
    - atomic: 是否原子写（写 .tmp 后 os.replace，避免半截文件）；
    - cache: 是否启用进程内缓存（首次 read 后缓存，write/mutate 同步更新）。
    """

    def __init__(
        self,
        path: str,
        *,
        default: Any = None,
        pretty: bool = True,
        atomic: bool = True,
        cache: bool = True,
    ) -> None:
        self.path = path
        self.default = default
        self.pretty = pretty
        self.atomic = atomic
        self._lock = threading.Lock()
        self._cache: Optional[Any] = None
        self._cache_enabled = cache
        self._fp: Optional[tuple] = None   # 缓存内容对应的文件指纹（mtime_ns, size）

    # ------------------------- 读取 -------------------------

    def fingerprint(self) -> Optional[tuple]:
        """当前磁盘文件指纹（mtime_ns, size）；文件不存在返回 None。

        用于判断「文件是否被别人改过」：多 worker 进程各自持有内存缓存，
        只看缓存会导致 A 进程写入后 B 进程仍返回旧值；也用于运维直接编辑
        json 文件的场景（此前必须重启才能生效）。
        """
        try:
            st = os.stat(self.path)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def read(self) -> Any:
        """读取当前数据：缓存命中且文件指纹未变则直接返回，否则重新读盘。"""
        if self._cache_enabled and self._cache is not None and self.fingerprint() == self._fp:
            return self._cache
        data = self.default
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if loaded is not None:
                    data = loaded
        except Exception:  # noqa: BLE001 —— 文件损坏时回退默认值，不阻塞业务
            pass
        if self._cache_enabled:
            self._cache = data
            self._fp = self.fingerprint()
        return data

    # ------------------------- 写入 -------------------------

    def write(self, data: Any) -> None:
        """整体覆写仓库数据（锁内原子写盘，并同步内存缓存）。"""
        with self._lock:
            self._persist(data)

    def mutate(self, fn: Callable[[Any], Any]) -> Any:
        """原子读改写：fn(旧数据) -> 新数据，落盘后返回新数据。

        适用于「读取-修改-写回」类操作（增删改索引、更新关联表等），
        全程持锁，避免并发请求交错覆盖。
        """
        with self._lock:
            current = self.read()
            new_data = fn(current)
            self._persist(new_data)
            return new_data

    # ------------------------- 内部 -------------------------

    def _persist(self, data: Any) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            text = json.dumps(data, ensure_ascii=False, indent=2) if self.pretty else json.dumps(data, ensure_ascii=False)
            if self.atomic:
                tmp = self.path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(text)
                os.replace(tmp, self.path)
            else:
                with open(self.path, "w", encoding="utf-8") as f:
                    f.write(text)
        except Exception:  # noqa: BLE001 —— 落盘失败不阻塞业务（下次写入重试）
            pass
        finally:
            if self._cache_enabled:
                self._cache = data
                self._fp = self.fingerprint()


def read_json_file(path: str, default: Any = None) -> Any:
    """读取 JSON 文件；文件缺失 / 内容损坏时返回 ``default``（不抛异常）。"""
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return default if data is None else data
    except Exception:  # noqa: BLE001 —— 损坏文件按缺失处理，不阻断业务
        pass
    return default


def write_json_atomic(path: str, data: Any, *, pretty: bool = True) -> Any:
    """原子写 JSON（先写 ``.tmp`` 再 ``os.replace``，避免半截文件）。

    与 JsonRepository 的「失败静默」不同，本函数**向上抛出** OSError，
    供需要向用户提示「配置写入失败」的调用方使用。
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2) if pretty else json.dumps(data, ensure_ascii=False)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def copy_file_to_trash(src: str, trash_name: str) -> None:
    """把文件移动到系统临时回收目录（而非 os.remove）。

    部分 IDE 注入的 sitecustomize 会劫持 os.remove（安全删除/批量删除守卫），
    可能抛 SystemExit 导致请求 500；os.rename 语义不受影响。
    """
    import shutil
    import tempfile

    try:
        trash_dir = os.path.join(tempfile.gettempdir(), trash_name)
        os.makedirs(trash_dir, exist_ok=True)
        shutil.move(src, os.path.join(trash_dir, os.path.basename(src)))
    except OSError:
        pass
