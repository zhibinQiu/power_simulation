#!/usr/bin/env bash
# ============================================================
#  行业能碳仿真平台 - macOS .app 一键打包脚本（统一位于 platform/）
#  用法：
#    ./platform/build_mac.sh             # 打包为 SteelCarbonTwin.app（原生客户端窗口）
#    ./platform/build_mac.sh console     # 打包为终端运行的 onedir 版本（可见日志，Ctrl+C 退出）
#    ./platform/build_mac.sh universal   # 额外构建 universal2（兼容 Intel + Apple Silicon）
#
#  产物（位于项目根 dist/）：
#    dist/SteelCarbonTwin.app        （app 模式）
#    dist/SteelCarbonTwin/           （console / universal 模式）
#
#  说明：
#    - 架构默认与本机一致；如需分发给 Intel Mac，用 universal 模式。
#    - 分发到其他 Mac 时，首次打开若被 Gatekeeper 拦截：右键 → 打开。
#      若需免提示分发，需 Apple Developer 账号签名 + 公证。
# ============================================================
set -euo pipefail
# 定位到项目根目录（platform/ 的上级）
cd "$(dirname "$0")/.."

PY=python3
if [ -x backend/.venv/bin/python ]; then PY="$(pwd)/backend/.venv/bin/python"; fi
echo "使用 Python: $($PY --version)"

# CodeBuddy 会向环境注入 PYTHONPATH（含删除保护 shim），会拦截 pip 安装时的文件覆盖，
# 这里统一清除后执行 pip / PyInstaller。
RUNPY=(env -u PYTHONPATH -u PYTHONHOME "$PY")

echo "[1/4] 安装 Python 依赖 + PyInstaller + pywebview + Pillow..."
"${RUNPY[@]}" -m pip install --upgrade pip -q
"${RUNPY[@]}" -m pip install -r backend/config/requirements.txt -q
"${RUNPY[@]}" -m pip install pyinstaller pywebview Pillow -q

echo "[1.5/4] 生成 macOS 图标 (.icns)..."
"${RUNPY[@]}" platform/build_icons.py --icns

echo "[2/4] 构建前端静态资源..."
(cd frontend && npm install --silent && npm run build 2>&1 | tail -3)

MODE="${1:-app}"
EXTRA_ARGS=()
case "$MODE" in
  app)
    echo "[3/4] 打包 .app 版（原生客户端窗口）..."
    EXTRA_ARGS=(--windowed --osx-bundle-identifier com.steelcarbon.twin)
    ;;
  console)
    echo "[3/4] 打包 console 版（终端运行）..."
    ;;
  universal)
    echo "[3/4] 打包 universal2 版（Intel + Apple Silicon）..."
    EXTRA_ARGS=(--target-arch universal2)
    ;;
  *)
    echo "未知模式: $MODE （可用: app / console / universal）" >&2
    exit 1
    ;;
esac

"${RUNPY[@]}" -m PyInstaller --noconfirm --clean --onedir \
  --name SteelCarbonTwin \
  --icon "$(pwd)/platform/icon.icns" \
  --collect-all uvicorn --collect-all websockets --collect-all webview \
  --add-data "$(pwd)/frontend/dist:frontend/dist" \
  --paths backend \
  --specpath platform \
  "${EXTRA_ARGS[@]}" \
  platform/desktop_launcher.py

echo "[4/4] 完成！"
case "$MODE" in
  app)       echo "  产物: dist/SteelCarbonTwin.app  —— 双击运行，打开原生客户端窗口" ;;
  console)   echo "  产物: dist/SteelCarbonTwin/SteelCarbonTwin —— 终端运行，Ctrl+C 退出" ;;
  universal) echo "  产物: dist/SteelCarbonTwin/SteelCarbonTwin —— universal2 通用版" ;;
esac
