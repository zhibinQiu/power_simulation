"""中间件服务客户端：平台 ⇄ 能碳数据中间件（注册/管理外部数据源）。

架构（用户诉求）：外部数据接入 = 平台向中间件**注册**一条数据源，中间件负责采集
并转换为标准 MQTT，以 **external 形态**直发云端 Broker（41883）——与一体机上报
同一 Broker，平台经唯一入口（云端 Broker 订阅）即可取数，无需第二个连接。
平台侧对外部数据源的增删改启停，本质都是对中间件管理 API 的调用 + 本地目录登记
（用于关联仿真设备与启停过滤）。

配置：config/middleware.json（enabled / base_url / token / timeout）。
中间件不可达时所有写操作返回明确错误，读操作降级为「仅本地登记」状态，不阻塞平台。

性能：
- HTTP 连接复用（模块级 httpx.Client，keep-alive；原先每次请求新建连接，外部数据源
  页面 6s 轮询下反复 TLS/TCP 握手）；
- 读接口分层缓存——types 60s、status 3s、sources_snapshot 8s（略大于前端轮询周期，
  使每轮轮询最多打一次中间件）；写操作/配置变更即时 reset_cache()。
"""
from __future__ import annotations

import copy
import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

from .core.storage import read_json_file, write_json_atomic

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "middleware.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "base_url": "http://127.0.0.1:42084",
    "token": "",
    "timeout": 6.0,
}

_lock = threading.RLock()
_current: Optional[Dict[str, Any]] = None

# 读接口缓存（写操作 / 配置变更后 reset_cache 失效）
_TYPES_TTL = 60.0
_STATUS_TTL = 3.0
_SNAPSHOT_TTL = 8.0
_types_ts = 0.0
_types_cache: List[Dict[str, Any]] = []
_status_ts = 0.0
_status_cache: Dict[str, Any] = {}
_snapshot_ts = 0.0
_snapshot: Dict[str, Any] = {}

_client: Any = None


# ----------------------------- 配置 -----------------------------

def load_config(force: bool = False) -> Dict[str, Any]:
    global _current
    with _lock:
        if _current is not None and not force:
            return copy.deepcopy(_current)
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        saved = read_json_file(CONFIG_PATH, {})
        if isinstance(saved, dict) and saved:
            for k in ("enabled", "base_url", "token", "timeout"):
                if k in saved:
                    cfg[k] = saved[k]
        elif not os.path.exists(CONFIG_PATH):
            try:  # 首次运行：落盘默认配置，便于运维直接编辑
                write_json_atomic(CONFIG_PATH, cfg)
            except OSError:
                pass
        # 环境变量覆盖（如平台容器内经 docker 网关 CARBON_MIDDLEWARE_URL=http://172.18.0.1:42084
        # 访问宿主中间件，而仓库配置文件保持本地开发默认值，互不覆盖）
        _env_url = os.environ.get("CARBON_MIDDLEWARE_URL", "").strip()
        if _env_url:
            cfg["base_url"] = _env_url.rstrip("/")
        _current = cfg
        return copy.deepcopy(cfg)


def save_config(patch: Dict[str, Any]) -> Dict[str, Any]:
    """保存中间件连接配置（平台「中间件服务」设置），失败抛 ValueError。"""
    global _current
    if not isinstance(patch, dict):
        raise ValueError("配置必须是 JSON 对象")
    cfg = load_config()
    if "enabled" in patch:
        cfg["enabled"] = bool(patch["enabled"])
    if "base_url" in patch:
        url = str(patch["base_url"] or "").strip().rstrip("/")
        if not url:
            raise ValueError("中间件服务地址不能为空")
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("中间件服务地址必须以 http:// 或 https:// 开头")
        cfg["base_url"] = url
    if "token" in patch:
        cfg["token"] = str(patch["token"] or "").strip()
    if "timeout" in patch:
        try:
            cfg["timeout"] = max(1.0, min(30.0, float(patch["timeout"])))
        except (TypeError, ValueError):
            raise ValueError("超时时间必须为数字（秒）")
    with _lock:
        _current = cfg
    reset_cache()
    try:
        write_json_atomic(CONFIG_PATH, cfg)
    except OSError as e:
        raise ValueError(f"中间件配置写入失败：{e}") from e
    return public_config()


def public_config() -> Dict[str, Any]:
    """前端展示用配置（隐藏 token 明文，仅给是否已设置）。"""
    cfg = load_config()
    return {
        "enabled": bool(cfg.get("enabled")),
        "base_url": cfg.get("base_url"),
        "token_set": bool(cfg.get("token")),
        "timeout": cfg.get("timeout"),
    }


def reset_cache() -> None:
    """清空读接口缓存（写操作、配置变更、测试复位时调用）。"""
    global _status_ts, _types_ts, _snapshot_ts
    with _lock:
        _status_ts = 0.0
        _types_ts = 0.0
        _snapshot_ts = 0.0


# ----------------------------- HTTP -----------------------------

class MiddlewareError(ValueError):
    """中间件调用失败（不可达/鉴权失败/业务校验不通过）。"""


def _headers(cfg: Dict[str, Any]) -> Dict[str, str]:
    h = {"Content-Type": "application/json"}
    if cfg.get("token"):
        h["Authorization"] = f"Bearer {cfg['token']}"
    return h


def _http() -> Any:
    """模块级复用的 HTTP 客户端（keep-alive；线程安全，可跨 FastAPI 线程池共享）。"""
    global _client
    with _lock:
        if _client is None:
            _client = httpx.Client(limits=httpx.Limits(max_keepalive_connections=8,
                                                       max_connections=16))
        return _client


def _do(method: str, url: str, headers: Dict[str, str], body: Any,
        timeout: float) -> Dict[str, Any]:
    """发起一次请求并返回校验过的 JSON（HTTP 层错误抛 MiddlewareError）。"""
    if httpx is None:
        raise MiddlewareError("平台缺少 httpx 依赖，无法访问中间件服务")
    try:
        resp = _http().request(method, url, headers=headers,
                               json=body if body is not None else None, timeout=timeout)
    except Exception as e:  # noqa: BLE001
        raise MiddlewareError(f"无法连接中间件服务 {url.split('/api/')[0]}（{e}）") from e
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        data = {"ok": False, "error": f"中间件返回非 JSON（HTTP {resp.status_code}）"}
    if resp.status_code >= 400 or data.get("ok") is False:
        raise MiddlewareError(data.get("error") or f"中间件返回 HTTP {resp.status_code}")
    return data


def _request(method: str, path: str, body: Any = None,
             timeout: Optional[float] = None) -> Dict[str, Any]:
    cfg = load_config()
    return _do(method, f"{cfg['base_url']}{path}", _headers(cfg), body,
               float(timeout or cfg.get("timeout") or 6.0))


def probe(base_url: str = "", token: str = "") -> Dict[str, Any]:
    """用（可选的）临时地址/Token 探测中间件连通性：不落盘、不走缓存。

    统一收口 /api/middleware/test 的探测逻辑（原先在路由里另行手写一份 HTTP 调用）。
    """
    cfg = load_config()
    url = str(base_url or cfg.get("base_url") or "").rstrip("/")
    if not url:
        raise MiddlewareError("中间件服务地址为空")
    tok = cfg.get("token") if not token else token
    return _do("GET", f"{url}/api/health", _headers({"token": tok}), None, 6.0)


# ----------------------------- 接口 -----------------------------

def health() -> Dict[str, Any]:
    """中间件健康状态（含运行形态与适配器统计）。"""
    return _request("GET", "/api/health", timeout=4.0)


def types(force: bool = False) -> List[Dict[str, Any]]:
    """可用数据源类型与参数 schema（分钟级缓存）。"""
    global _types_ts, _types_cache
    now = time.time()
    with _lock:
        if not force and now - _types_ts < _TYPES_TTL and _types_cache:
            return copy.deepcopy(_types_cache)
    out = _request("GET", "/api/types").get("types") or []
    with _lock:
        _types_cache, _types_ts = out, now
    return copy.deepcopy(out)


def list_sources() -> List[Dict[str, Any]]:
    """中间件侧已注册的数据源（含运行状态）。"""
    return _request("GET", "/api/sources").get("sources") or []


def get_source(source_id: str) -> Optional[Dict[str, Any]]:
    try:
        return _request("GET", f"/api/sources/{source_id}").get("source")
    except MiddlewareError as e:
        if "不存在" in str(e):
            return None
        raise


def add_source(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """在中间件注册一条数据源。"""
    return _request("POST", "/api/sources", cfg).get("source") or {}


def update_source(source_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    return _request("PUT", f"/api/sources/{source_id}", patch).get("source") or {}


def remove_source(source_id: str) -> None:
    try:
        _request("DELETE", f"/api/sources/{source_id}")
    except MiddlewareError as e:
        if "不存在" not in str(e):
            raise


def set_enabled(source_id: str, enabled: bool) -> Dict[str, Any]:
    return _request("POST", f"/api/sources/{source_id}/toggle",
                    {"enabled": bool(enabled)}).get("source") or {}


def test_source(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """连通性测试（不落盘）：转发到中间件，返回 {ok, message}。"""
    return _request("POST", "/api/sources/test", cfg, timeout=10.0)


# ----------------------------- 聚合状态 -----------------------------

def sources_snapshot(force: bool = False) -> Dict[str, Any]:
    """中间件数据源快照（含在线判定与错误文案），供数据源列表页高频轮询。

    只打一次 GET /api/sources，结果短期缓存（8s > 前端轮询周期），使「列表 + 每个
    外部源运行状态 + 中间件在线徽标」不再逐项发 HTTP。
    """
    global _snapshot_ts, _snapshot
    now = time.time()
    with _lock:
        if not force and _snapshot_ts and now - _snapshot_ts < _SNAPSHOT_TTL:
            return copy.deepcopy(_snapshot)
    cfg = load_config()
    # token_set：前端据此决定「留空=保持原 token」，无需再为配置面板单独请求 /api/health
    out: Dict[str, Any] = {"enabled": bool(cfg.get("enabled")),
                           "base_url": cfg.get("base_url"),
                           "token_set": bool(cfg.get("token")),
                           "online": False, "error": "", "sources": []}
    if not cfg.get("enabled"):
        out["error"] = "中间件服务接入已停用"
    else:
        try:
            out["sources"] = list_sources()
            out["online"] = True
        except MiddlewareError as e:
            out["error"] = str(e)
        except Exception as e:  # noqa: BLE001
            out["error"] = f"查询中间件数据源失败：{e}"
    with _lock:
        _snapshot, _snapshot_ts = out, now
    return copy.deepcopy(out)


def status(force: bool = False) -> Dict[str, Any]:
    """平台视角的中间件服务状态（供「中间件服务」面板展示）。

    返回 online/detail/sources 计数/类型清单；中间件不可达时 online=False 并带
    error 文案，供前端给出「未连接中间件」提示。
    """
    global _status_ts, _status_cache
    now = time.time()
    with _lock:
        if not force and now - _status_ts < _STATUS_TTL and _status_cache:
            return copy.deepcopy(_status_cache)
    cfg = load_config()
    out: Dict[str, Any] = {
        "enabled": bool(cfg.get("enabled")),
        "base_url": cfg.get("base_url"),
        "online": False, "error": "", "detail": {}, "sources": 0, "types": [],
    }
    if not cfg.get("enabled"):
        out["error"] = "中间件服务接入已停用"
    else:
        try:
            h = health()
            out["online"] = True
            out["detail"] = {"mode": h.get("mode") or "external",
                             "version": h.get("version"), "uptime": h.get("uptime"),
                             "output": h.get("output") or {}}
            out["sources"] = int(h.get("sources") or 0)
            out["types"] = h.get("types") or []
        except MiddlewareError as e:
            out["error"] = str(e)
        except Exception as e:  # noqa: BLE001
            out["error"] = f"查询中间件状态失败：{e}"
    with _lock:
        _status_cache, _status_ts = out, now
    return copy.deepcopy(out)
