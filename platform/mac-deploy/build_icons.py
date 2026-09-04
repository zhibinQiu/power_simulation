"""从本目录 icon.png 生成 macOS 打包所需的 .icns 图标。

依赖：Pillow（pip install Pillow）
用法：
    python platform/mac-deploy/build_icons.py

设计稿源：本目录 icon.png（任意尺寸方形 PNG，最佳 1024×1024，随打包资源自包含入库）
输出：platform/mac-deploy/icon.icns
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SRC = HERE / "icon.png"
ICNS_OUT = HERE / "icon.icns"

MAC_SIZES = (16, 32, 64, 128, 256, 512, 1024)


def _load():
    from PIL import Image

    if not SRC.exists():
        sys.exit(f"未找到源图: {SRC}")
    return Image.open(SRC).convert("RGBA")


def build_icns() -> None:
    from PIL import Image

    img = _load()
    ICNS_OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(ICNS_OUT, format="ICNS", sizes=[(s, s) for s in MAC_SIZES])
    print(f"已生成 {ICNS_OUT.relative_to(ROOT)} (macOS icon, {ICNS_OUT.stat().st_size} B)")


def main() -> None:
    # 兼容 GitHub Actions runner：默认控制台编码无法输出中文，
    # 强制将 stdout/stderr 切到 UTF-8，避免 'charmap' codec can't encode 报错。
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--icns", action="store_true", help="仅生成 macOS .icns")
    args = parser.parse_args()

    try:
        build_icns()
    except Exception as exc:
        sys.exit(f".icns 生成失败: {exc}")


if __name__ == "__main__":
    main()
