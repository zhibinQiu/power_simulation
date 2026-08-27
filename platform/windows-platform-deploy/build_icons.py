"""从项目根 icon.png 生成 Windows 打包所需的 .ico 图标。

依赖：Pillow（pip install Pillow）
用法：
    python platform/windows-platform-deploy/build_icons.py

设计稿源：项目根 icon.png（任意尺寸方形 PNG，最佳 1024×1024）
输出：platform/windows-platform-deploy/icon.ico
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "icon.png"
ICO_OUT = ROOT / "platform" / "windows-platform-deploy" / "icon.ico"

WIN_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _load():
    from PIL import Image

    if not SRC.exists():
        sys.exit(f"未找到源图: {SRC}")
    return Image.open(SRC).convert("RGBA")


def build_ico() -> None:
    from PIL import Image

    img = _load()
    ICO_OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(ICO_OUT, format="ICO", sizes=[(s, s) for s in WIN_SIZES])
    print(f"已生成 {ICO_OUT.relative_to(ROOT)} (Windows icon, {ICO_OUT.stat().st_size} B)")


def main() -> None:
    # 兼容 GitHub Actions Windows runner：默认控制台编码(cp1252)无法输出中文，
    # 强制将 stdout/stderr 切到 UTF-8，避免 'charmap' codec can't encode 报错。
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--ico", action="store_true", help="仅生成 Windows .ico")
    args = parser.parse_args()

    try:
        build_ico()
    except Exception as exc:
        sys.exit(f".ico 生成失败: {exc}")


if __name__ == "__main__":
    main()
