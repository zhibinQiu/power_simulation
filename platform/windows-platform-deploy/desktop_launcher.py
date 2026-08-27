"""桌面客户端启动器（PyInstaller 打包入口，Windows / macOS 通用）。

双击可执行文件：启动本地 FastAPI 服务，并通过 pywebview 打开「原生客户端窗口」
（macOS 使用 WKWebView，Windows 使用 WebView2），呈现独立桌面应用体验，
而非浏览器标签页。

关键处理：
- Windows 以 --windowed 打包时无控制台窗口，sys.stdout/stderr 可能为 None，先做兜底；
- 打开窗口前等待本地服务就绪，避免 WebView 加载到空白/错误页；
- 日志写入 <用户目录>/.steel_carbon_twin/launcher.log，便于排查；
- pywebview / WebView2 Runtime 不可用时，自动回退为「浏览器打开」并给出提示。
"""
from __future__ import annotations

import logging
import os
import platform
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

# ---- 无控制台（--windowed）模式下 stdout/stderr 可能为 None，先行兜底 ----
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# ---- 文件日志（windowed 无终端时排查问题靠它） ----
_LOG_DIR = Path.home() / ".steel_carbon_twin"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(_LOG_DIR / "launcher.log", encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("launcher")

# ---- 路径：本文件位于项目根/platform/windows-platform-deploy/，backend 包在项目根/backend/ ----
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
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
    try:
        uvicorn.run(app_main.app, host=HOST, port=port, log_level="info")
    except Exception:
        log.exception("后端服务启动失败")


def _wait_for_server(url: str, timeout: float = 20.0) -> bool:
    """阻塞等待本地服务可访问（/api/health），返回是否就绪。"""
    deadline = time.time() + timeout
    health = url + "/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health, timeout=1.0) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def _run_browser_fallback(url: str) -> None:
    """原生窗口不可用时回退：浏览器打开 + 主线程常驻保持服务。"""
    log.warning("改用浏览器打开: %s", url)
    webbrowser.open(url)
    while True:
        time.sleep(3600)


def _notify(title: str, msg: str) -> None:
    """跨平台弹窗提示（Windows MessageBox / macOS 通知）。失败静默。"""
    system = platform.system()
    try:
        if system == "Windows":
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, title, 0x40)
        elif system == "Darwin":
            escaped = msg.replace('"', '\\"')
            subprocess.Popen(
                ["osascript", "-e", f'display alert "{title}" message "{escaped}"'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        log.exception("系统提示弹窗失败")


def main() -> None:
    port = _pick_port()
    url = f"http://{HOST}:{port}"
    system = platform.system()
    label = "macOS" if system == "Darwin" else system

    print("=" * 56)
    print(f"  工业能碳智控平台 · {label} 桌面版")
    print(f"  本地服务: {url}")
    print("  正在打开客户端窗口，关闭窗口即退出应用")
    print("=" * 56)

    threading.Thread(target=_start_server, args=(port,), daemon=True).start()

    # 关键：等待服务就绪，避免 WebView 打开时加载到空白/错误页
    log.info("等待本地服务就绪: %s", url)
    ready = _wait_for_server(url)
    log.info("服务就绪: %s", ready)

    try:
        import webview  # 延迟导入：未安装时回退浏览器模式
    except Exception as exc:
        log.exception("pywebview 导入失败，回退浏览器模式")
        _notify("无法启动原生窗口", f"pywebview 加载失败：{exc}\n将改用浏览器打开。")
        _run_browser_fallback(url)
        return

    try:
        webview.create_window(
            "工业能碳智控平台",
            url,
            width=1440,
            height=900,
            min_size=(1100, 700),
            resizable=True,
        )
        webview.start(debug=False)
    except Exception as exc:
        log.exception("原生窗口启动失败，回退浏览器模式")
        tip = "Windows 请确认已安装 WebView2 运行时（微软官网免费下载）。\n" if system == "Windows" else ""
        _notify("无法启动原生窗口", f"原因：{exc}\n{tip}将改用浏览器打开。")
        _run_browser_fallback(url)
        return

    log.info("客户端窗口已关闭，退出应用")
    sys.exit(0)


if __name__ == "__main__":
    main()
