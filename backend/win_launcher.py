"""Windows 桌面版启动器（PyInstaller 打包入口）。

双击 exe：启动 FastAPI 服务 → 1.5 秒后自动打开浏览器。
关闭本控制台窗口即退出服务。
"""
import threading
import webbrowser

import uvicorn

from app import main as app_main

PORT = 8010
HOST = "127.0.0.1"


def _open_browser() -> None:
    webbrowser.open(f"http://{HOST}:{PORT}")


if __name__ == "__main__":
    print("=" * 56)
    print("  行业能碳仿真平台 · Windows 版")
    print(f"  访问地址: http://{HOST}:{PORT}")
    print("  浏览器即将自动打开，关闭本窗口即退出服务")
    print("=" * 56)
    threading.Timer(1.5, _open_browser).start()
    uvicorn.run(app_main.app, host=HOST, port=PORT, log_level="info")
