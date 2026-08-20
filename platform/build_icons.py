"""从项目根 icon.png 生成打包所需的 .icns（macOS）和 .ico（Windows）图标。

依赖：Pillow（pip install Pillow）
用法：
    python platform/build_icons.py            # 两种都生成
    python platform/build_icons.py --icns     # 仅 macOS
    python platform/build_icons.py --ico      # 仅 Windows

设计稿源：项目根 icon.png（任意尺寸方形 PNG，最佳 1024×1024）
输出：platform/icon.icns、platform/icon.ico
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "icon.png"
ICNS_OUT = ROOT / "platform" / "icon.icns"
ICO_OUT = ROOT / "platform" / "icon.ico"

MAC_SIZES = (16, 32, 64, 128, 256, 512, 1024)
WIN_SIZES = (16, 24, 32, 48, 64, 128, 256)


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


def build_ico() -> None:
    img = _load()
    ICO_OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(ICO_OUT, format="ICO", sizes=[(s, s) for s in WIN_SIZES])
    print(f"已生成 {ICO_OUT.relative_to(ROOT)} (Windows icon, {ICO_OUT.stat().st_size} B)")


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--icns", action="store_true", help="仅生成 macOS .icns")
    group.add_argument("--ico", action="store_true", help="仅生成 Windows .ico")
    args = parser.parse_args()

    do_icns = args.icns or not args.ico
    do_ico = args.ico or not args.icns

    if do_icns:
        try:
            build_icns()
        except Exception as exc:
            sys.exit(f".icns 生成失败: {exc}")
    if do_ico:
        try:
            build_ico()
        except Exception as exc:
            sys.exit(f".ico 生成失败: {exc}")


if __name__ == "__main__":
    main()
