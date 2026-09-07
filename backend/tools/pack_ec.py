#!/usr/bin/env python3
"""打包 .ec 行业资源包（ec = 行业能碳仿真资源包，标准 zip 容器）。

平台 ⇄ 行业抽离的可分发产物：一个 .ec = 一个行业（该行业全部配置/属性 +
能碳核算方法学），由平台「文件 → 打开资源包…」装载。

包内容（资源序列化与运行时 scene_loader 输出共用同一真源，构建器见
app/scene_loader.build_resource_package_bytes，本脚本仅保留 CLI 入口）：
  ec.json          清单（format=ec / formatVersion / id / engines /
                   package:{vendor, product, version}）
  meta.json        场景元数据（method 方法学摘要 / package / ready / routes…）
  model.json       默认工艺模型快照（工艺包直读形态必需，有它才视为完整包）
  strategies.json / factors.json / param-schema.json / devices.json /
  methods.json / templates.json / dictionary.json / config.json
                  （随该场景资源就绪情况写入）

用法（backend 目录内执行，运行时依赖 = 后端环境）：
  python tools/pack_ec.py steel --out /tmp/steel.ec
  python tools/pack_ec.py dc-thermal --out /tmp/dc-thermal.ec
  python tools/pack_ec.py steel --version 2.0.0 --vendor "某某咨询" \
         --product "钢铁包 · 定制版" --out ./steel-v2.ec
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import scene_loader  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="打包 .ec 行业资源包")
    ap.add_argument("scene", help="场景 id（如 steel / dc-thermal / cement），须已就绪")
    ap.add_argument("--out", "-o", default=None, help="输出文件路径（默认 ./{id}.ec）")
    ap.add_argument("--version", default=None, help="包版本（默认取 meta.package.version）")
    ap.add_argument("--vendor", default=None, help="厂商名（默认取 meta.package.vendor）")
    ap.add_argument("--product", default=None, help="产品名（默认取 meta.package.product）")
    args = ap.parse_args()

    out = args.out or os.path.join(os.getcwd(), f"{args.scene}.ec")
    raw = scene_loader.build_resource_package_bytes(
        args.scene,
        version=args.version,
        vendor=args.vendor,
        product=args.product,
    )
    with open(out, "wb") as f:
        f.write(raw)
    print(f"[ok] 已打包 {args.scene} -> {out}（{len(raw)} 字节）")


if __name__ == "__main__":
    main()
