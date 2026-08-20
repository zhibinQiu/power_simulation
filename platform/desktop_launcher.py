"""桌面客户端启动器（PyInstaller 打包入口，Windows / macOS 通用）。

双击可执行文件：启动本地 FastAPI 服务，并通过 pywebview 打开「原生客户端窗口」
（macOS 使用 WKWebView，Windows 使用 WebView2），呈现独立桌面应用体验，
而非浏览器标签页。

若运行环境未安装 pywebview，自动回退为「浏览器打开」模式。
关闭客户端窗口即退出应用。
"""
import os
import platform
import socket
import sys
import threading
import time
import webbrowser

# 本文件位于项目根/platform/，backend 包在项目根/backend/ 下。
# 开发环境直接 `python platform/desktop_launcher.py` 运行时可找到 app 包；
# PyInstaller 打包时由 --paths backend 保证分析阶段可解析。
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_BACKEND = os.path.join(_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import uvicorn  # noqa: E402

from app import main as app_main  # noqa: E402

HOST = os.environ.get("TWIN_HOST", "127.0.0.1")
PORT = int(os.environ.get("TWIN_PORT", "0"))  # 0 => 自动选择空闲端口


def _pick_port() -> int:
    """端口 0 时让系统分配一个空闲端口，避免与已有服务冲突。"""
    if PORT:
        return PORT
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _start_server(port: int) -> None:
    uvicorn.run(app_main.app, host=HOST, port=port, log_level="warning")


def _run_browser_fallback(url: str) -> None:
    """未安装 pywebview 时回退：浏览器打开 + 主线程常驻保持服务。"""
    print("[提示] 未检测到 pywebview，改用浏览器打开。")
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    while True:
        time.sleep(3600)


def main() -> None:
    port = _pick_port()
    url = f"http://{HOST}:{port}"
    system = platform.system()
    label = "macOS" if system == "Darwin" else system

    print("=" * 56)
    print(f"  行业能碳仿真平台 · {label} 桌面版")
    print(f"  本地服务: {url}")
    print("  正在打开客户端窗口，关闭窗口即退出应用")
    print("=" * 56)

    threading.Thread(target=_start_server, args=(port,), daemon=True).start()

    try:
        import webview  # 延迟导入：未安装时回退浏览器模式
    except Exception:
        _run_browser_fallback(url)
        return

    webview.create_window(
        "行业能碳仿真平台",
        url,
        width=1440,
        height=900,
        min_size=(1100, 700),
        resizable=True,
    )
    webview.start(debug=False)
    # 窗口关闭后退出进程（uvicorn 运行于 daemon 线程，随进程一并结束）
    sys.exit(0)


if __name__ == "__main__":
    main()
