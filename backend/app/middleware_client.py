"""中间件服务客户端：平台 ⇄ 能碳数据中间件（注册/管理外部数据源）。

架构（用户诉求）：外部数据接入 = 平台向中间件**注册**一条数据源，中间件负责采集
并转换为标准 MQTT 输出。输出形态两种（config 说明）：
  · local（默认）：中间件内置 Broker，平台单独订阅中间件端口取数；
  · external：中间件直发外部 Broker（与云端 41883 同一 Broker），平台经
    **云端端点**订阅即可取数，无需再单独订阅中间件端口（subscribe=false）。
平台侧对外部数据源的增删改启停，本质都是对中间件管理 API 的调用 + 本地目录登记
（用于关联仿真设备与启停过滤）。

配置：config/middleware.json（enabled / subscribe / base_url / token / broker / timeout）。
  - enabled   ：是否接入中间件服务（管理能力开关）；
  - subscribe ：是否单独订阅中间件数据端口（external 形态为 false，数据走云端端点）。
中间件不可达时所有写操作返回明确错误，读操作降级为「仅本地登记」状态，不阻塞平台。
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "middleware.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    # 是否单独订阅中间件数据端口（默认 true=local 形态；external 形态设 false，
    # 数据已直发云端 Broker(41883)，平台经云端端点订阅即可）
    "subscribe": True,
    "base_url": "http://127.0.0.1:42084",
    "token": "",
    # 中间件数据端口（local 形态平台订阅目标；external 形态仅作展示）
    "broker": {"host": "127.0.0.1", "port": 41884, "username": "", "password": ""},
    "timeout": 6.0,
}

_lock = threading.RLock()
_current: Optional[Dict[str, Any]] = None

# 状态缓存：health/types 等低频查询，避免前端每次刷新都打中间件
_status_ts = 0.0
_status_cache: Dict[str, Any] = {}
_TYPES_TTL = 60.0
_STATUS_TTL = 3.0
_types_ts = 0.0
_types_cache: List[Dict[str, Any]] = []


# ----------------------------- 配置 -----------------------------

def load_config(force: bool = False) -> Dict[str, Any]:
    global _current
    with _lock:
        if _current is not None and not force:
            return json.loads(json.dumps(_current))
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f) or {}
            if isinstance(saved, dict):
                for k in ("enabled", "subscribe", "base_url", "token", "timeout"):
                    if k in saved:
                        cfg[k] = saved[k]
                if isinstance(saved.get("broker"), dict):
                    cfg["broker"].update(saved["broker"])
        except FileNotFoundError:
            try:
                os.makedirs(CONFIG_DIR, exist_ok=True)
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
            except OSError:
                pass
        except Exception:
            cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        # 环境变量覆盖（如平台容器内经 docker 网关 CARBON_MIDDLEWARE_URL=http://172.18.0.1:42084
        # 访问宿主中间件，而仓库配置文件保持本地开发默认值，互不覆盖）
        _env_url = os.environ.get("CARBON_MIDDLEWARE_URL", "").strip()
        if _env_url:
            cfg["base_url"] = _env_url.rstrip("/")
        _current = cfg
        return json.loads(json.dumps(cfg))


def save_config(patch: Dict[str, Any]) -> Dict[str, Any]:
    """保存中间件连接配置（平台「中间件服务」设置），失败抛 ValueError。"""
    global _current, _status_ts
    if not isinstance(patch, dict):
        raise ValueError("配置必须是 JSON 对象")
    cfg = load_config()
    if "enabled" in patch:
        cfg["enabled"] = bool(patch["enabled"])
    if "subscribe" in patch:
        cfg["subscribe"] = bool(patch["subscribe"])
    if "base_url" in patch:
        url = str(patch["base_url"] or "").strip().rstrip("/")
        if not url:
            raise ValueError("中间件服务地址不能为空")
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("中间件服务地址必须以 http:// 或 https:// 开头")
        cfg["base_url"] = url
    if "token" in patch:
        cfg["token"] = str(patch["token"] or "").strip()
    if isinstance(patch.get("broker"), dict):
        b = patch["broker"]
        if "host" in b:
            cfg["broker"]["host"] = str(b["host"] or "").strip()
        if "port" in b:
            try:
                port = int(b["port"])
            except (TypeError, ValueError):
                raise ValueError("中间件 Broker 端口必须为数字")
            if port <= 0 or port > 65535:
                raise ValueError("中间件 Broker 端口非法")
            cfg["broker"]["port"] = port
        for k in ("username", "password"):
            if k in b:
                cfg["broker"][k] = str(b[k] or "")
    if "timeout" in patch:
        try:
            cfg["timeout"] = max(1.0, min(30.0, float(patch["timeout"])))
        except (TypeError, ValueError):
            raise ValueError("超时时间必须为数字（秒）")
    with _lock:
        _current = cfg
        _status_ts = 0.0
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_PATH)
    except OSError as e:
        raise ValueError(f"中间件配置写入失败：{e}") from e
    return public_config()


def public_config() -> Dict[str, Any]:
    """前端展示用配置（隐藏 token 明文，仅给是否已设置）。"""
    cfg = load_config()
    return {
        "enabled": bool(cfg.get("enabled")),
        "subscribe": bool(cfg.get("subscribe", True)),
        "base_url": cfg.get("base_url"),
        "token_set": bool(cfg.get("token")),
        "broker": cfg.get("broker"),
        "timeout": cfg.get("timeout"),
    }


# ----------------------------- HTTP -----------------------------

class MiddlewareError(ValueError):
    """中间件调用失败（不可达/鉴权失败/业务校验不通过）。"""


def _headers(cfg: Dict[str, Any]) -> Dict[str, str]:
    h = {"Content-Type": "application/json"}
    if cfg.get("token"):
        h["Authorization"] = f"Bearer {cfg['token']}"
    return h


def _request(method: str, path: str, body: Any = None,
             timeout: Optional[float] = None) -> Dict[str, Any]:
    cfg = load_config()
    if httpx is None:
        raise MiddlewareError("平台缺少 httpx 依赖，无法访问中间件服务")
    url = f"{cfg['base_url']}{path}"
    try:
        with httpx.Client(timeout=float(timeout or cfg.get("timeout") or 6.0)) as cli:
            resp = cli.request(method, url, headers=_headers(cfg),
                               json=body if body is not None else None)
    except Exception as e:  # noqa: BLE001
        raise MiddlewareError(f"无法连接中间件服务 {cfg['base_url']}（{e}）") from e
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        data = {"ok": False, "error": f"中间件返回非 JSON（HTTP {resp.status_code}）"}
    if resp.status_code >= 400 or data.get("ok") is False:
        raise MiddlewareError(data.get("error") or f"中间件返回 HTTP {resp.status_code}")
    return data


# ----------------------------- 接口 -----------------------------

def health(force: bool = True) -> Dict[str, Any]:
    """中间件健康状态（含内置 Broker 与输出桥）。"""
    return _request("GET", "/api/health", timeout=4.0)


def types(force: bool = False) -> List[Dict[str, Any]]:
    """可用数据源类型与参数 schema（分钟级缓存）。"""
    global _types_ts, _types_cache
    now = time.time()
    with _lock:
        if not force and now - _types_ts < _TYPES_TTL and _types_cache:
            return json.loads(json.dumps(_types_cache))
    data = _request("GET", "/api/types")
    out = data.get("types") or []
    with _lock:
        _types_cache = out
        _types_ts = now
    return json.loads(json.dumps(out))


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

def status(force: bool = False) -> Dict[str, Any]:
    """平台视角的中间件服务状态（供数据源页面顶部展示）。

    返回 online/detail(broker+bridge)/sources 计数/类型清单；中间件不可达时
    online=False 并带 error 文案，供前端给出「未连接中间件」提示。
    """
    global _status_ts, _status_cache
    now = time.time()
    with _lock:
        if not force and now - _status_ts < _STATUS_TTL and _status_cache:
            return json.loads(json.dumps(_status_cache))
    cfg = load_config()
    out: Dict[str, Any] = {
        "enabled": bool(cfg.get("enabled")),
        "subscribe": bool(cfg.get("subscribe", True)),
        "base_url": cfg.get("base_url"),
        "broker": cfg.get("broker"),
        "online": False, "error": "", "detail": {}, "sources": 0, "types": [],
    }
    if not cfg.get("enabled"):
        out["error"] = "中间件服务接入已停用"
        with _lock:
            _status_cache, _status_ts = out, now
        return out
    try:
        h = health()
        out["online"] = True
        out["detail"] = {"broker": h.get("broker") or {}, "bridge": h.get("bridge") or {},
                         "version": h.get("version"), "uptime": h.get("uptime")}
        out["sources"] = int(h.get("sources") or 0)
        out["types"] = h.get("types") or []
        bkr = out["detail"].get("broker") or {}
        if bkr.get("mode") == "external":
            # external 形态：数据直发云端 Broker(41883)，平台经云端端点订阅即可，无内置 Broker
            out["detail"]["external_mode"] = True
        elif not bkr.get("running"):
            out["error"] = f"中间件内置 Broker 未运行：{bkr.get('last_error') or '未知原因'}"
    except MiddlewareError as e:
        out["error"] = str(e)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"查询中间件状态失败：{e}"
    with _lock:
        _status_cache = out
        _status_ts = now
    return json.loads(json.dumps(out))
