"""中间件管理 API（HTTP JSON，零第三方依赖）。

平台通过本 API 完成「外部数据源注册到中间件」的全部操作，并通过 /api/health
判断中间件与内置 Broker 是否可用：

  GET    /api/health              中间件 + 内置 Broker + 输出桥状态
  GET    /api/types               可用数据源类型与参数 schema（前端表单渲染）
  GET    /api/sources             数据源列表（含运行状态）
  POST   /api/sources             注册数据源
  GET    /api/sources/{id}        单条数据源
  PUT    /api/sources/{id}        修改数据源
  DELETE /api/sources/{id}        注销数据源
  POST   /api/sources/{id}/toggle 启停数据源 {enabled}
  POST   /api/sources/test        连通性测试（不落盘）

认证：config.server.token 非空时，所有请求须带 `Authorization: Bearer <token>`。
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

_MW_VERSION = "2.0.0"


class ApiError(Exception):
    def __init__(self, status: int, message: str, **extra):
        super().__init__(message)
        self.status = status
        self.payload = {"ok": False, "error": message, **extra}


def _json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


class _Handler(BaseHTTPRequestHandler):
    server_version = "CarbonMiddleware/2.0"
    protocol_version = "HTTP/1.1"

    # ---------------- 基础 ----------------
    def log_message(self, fmt: str, *args) -> None:  # 静默访问日志（自有 logger 输出）
        pass

    def _send(self, status: int, body: bytes, ctype: str = "application/json; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:  # noqa: BLE001
            pass

    def _ok(self, obj: Any = None, status: int = 200) -> None:
        payload = obj if isinstance(obj, dict) else {"ok": True, "data": obj}
        self._send(status, _json_bytes(payload))

    def _fail(self, err: "ApiError | Exception") -> None:
        if isinstance(err, ApiError):
            self._send(err.status, _json_bytes(err.payload))
        else:
            self._send(500, _json_bytes({"ok": False, "error": f"内部错误：{err}"}))

    def _body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            raw = self.rfile.read(length)
            obj = json.loads(raw.decode("utf-8"))
            return obj if isinstance(obj, dict) else {}
        except Exception as e:  # noqa: BLE001
            raise ApiError(400, f"请求体不是合法 JSON 对象：{e}") from e

    # ---------------- 路由 ----------------
    def do_GET(self) -> None:
        self._route("GET")

    def do_POST(self) -> None:
        self._route("POST")

    def do_PUT(self) -> None:
        self._route("PUT")

    def do_DELETE(self) -> None:
        self._route("DELETE")

    def do_OPTIONS(self) -> None:
        self._send(204, b"")

    def _route(self, method: str) -> None:
        try:
            srv = self.server  # type: ignore[attr-defined]
            srv._check_auth(self.headers.get("Authorization"))
            path = urlparse(self.path).path.rstrip("/") or "/"
            parts = [p for p in path.split("/") if p]

            if path == "/api/health":
                self._ok(srv._health())
            elif path == "/api/types":
                self._ok({"ok": True, "types": srv.registry.types()})
            elif path == "/api/sources" and method == "GET":
                self._ok({"ok": True, "sources": srv.registry.list()})
            elif path == "/api/sources" and method == "POST":
                cfg = self._body()
                self._ok({"ok": True, "source": srv.registry.add(cfg)}, status=201)
            elif path == "/api/sources/test" and method == "POST":
                self._ok(srv.registry.test(self._body()))
            elif len(parts) == 3 and parts[0] == "api" and parts[1] == "sources":
                sid = parts[2]
                if method == "GET":
                    src = srv.registry.get(sid)
                    if src is None:
                        raise ApiError(404, f"数据源不存在：{sid}")
                    self._ok({"ok": True, "source": src})
                elif method == "PUT":
                    self._ok({"ok": True, "source": srv.registry.update(sid, self._body())})
                elif method == "DELETE":
                    srv.registry.remove(sid)
                    self._ok({"ok": True, "note": f"已注销数据源 {sid}"})
                else:
                    raise ApiError(405, "方法不允许")
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "sources" \
                    and parts[3] == "toggle" and method == "POST":
                enabled = bool(self._body().get("enabled"))
                self._ok({"ok": True, "source": srv.registry.set_enabled(parts[2], enabled)})
            else:
                raise ApiError(404, f"未知接口：{method} {path}")
        except ApiError as e:
            self._fail(e)
        except ValueError as e:
            self._fail(ApiError(400, str(e)))
        except Exception as e:  # noqa: BLE001
            self._fail(e)


class ManagementApi(ThreadingHTTPServer):
    """管理 API 服务。daemon_threads=True 保证进程可随时退出。"""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, registry: Any, broker: Any, bridge: Any,
                 host: str = "0.0.0.0", port: int = 42084, token: str = "",
                 logger: Any = None):
        super().__init__((host, int(port)), _Handler)
        self.registry = registry
        self.broker = broker
        self.bridge = bridge
        self.token = str(token or "")
        self.log = logger or (lambda *a: None)
        self.started_at = time.time()
        self._thread: Any = None
        self.running = False

    def _check_auth(self, header: Optional[str]) -> None:
        if not self.token:
            return
        if not header or not header.lower().startswith("bearer "):
            raise ApiError(401, "缺少 Bearer Token")
        if header.split(" ", 1)[1].strip() != self.token:
            raise ApiError(403, "Token 无效")

    def _health(self) -> Dict[str, Any]:
        if self.broker is not None:
            bkr = self.broker.status()
        else:
            # external 模式：未启内置 Broker，数据直发外部 Broker（如云端 41883）
            bmode = "external"
            if self.bridge is not None:
                bmode = (self.bridge.status() or {}).get("mode") or bmode
            bkr = {"running": False, "enabled": False, "mode": bmode,
                   "note": "external 模式：转换后的数据直发外部 Broker（如云端 41883），"
                           "无内置 Broker，平台经云端端点订阅即可取数"}
        return {
            "ok": True,
            "service": "carbon-middleware",
            "version": _MW_VERSION,
            "uptime": int(time.time() - self.started_at),
            "broker": bkr,
            "bridge": self.bridge.status() if self.bridge else {},
            "sources": len(self.registry.list()),
            "types": [t["type"] for t in self.registry.types()],
        }

    # ---------------- 生命周期 ----------------
    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self.serve_forever, daemon=True,
                                        name="mw-api")
        self._thread.start()
        self.log("info", f"管理 API 已启动 http://{self.server_address[0]}:{self.server_address[1]}")

    def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        try:
            self.shutdown()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.server_close()
        except Exception:  # noqa: BLE001
            pass
