#!/usr/bin/env python3
"""厂商激活码生成工具（配合 app/license.py 使用）。

用法（在 backend/ 目录下执行）：
    python -m tools.gen_license                  # 为本机生成激活码
    python -m tools.gen_license --machine=<指纹> # 为目标机器指纹生成激活码
    python -m app.license --gen                  # 等价于本机生成

输出：
    机器指纹: xxxxxxxxxxxxxxxx
    激活码  : NENG-XXXX-XXXX-XXXX-XXXX
"""
from __future__ import annotations

import sys

from app import license as license_mod


def main() -> int:
    machine = None
    for arg in sys.argv[1:]:
        if arg.startswith("--machine="):
            machine = arg.split("=", 1)[1]
        else:
            print(f"未知参数：{arg}", file=sys.stderr)
            print("用法：python -m tools.gen_license [--machine=<机器指纹>]", file=sys.stderr)
            return 2
    mid = machine or license_mod.machine_id()
    print(f"机器指纹: {mid}")
    print(f"激活码  : {license_mod.gen_license(mid)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
