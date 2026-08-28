"""平台激活（License）模块。

激活码格式：NENG-XXXX-XXXX-XXXX-XXXX（16 位十六进制，分 4 组）。
激活码由厂商侧使用 gen_license()（或 backend/tools/gen_license.py）生成，
与目标机器指纹（主机名 + MAC 地址哈希）绑定，仅在该机器上有效。

平台侧流程：
    1. 前端打开「激活」弹窗，输入激活码；
    2. 后端 POST /api/license/activate 校验签名并持久化到 data/license.json；
    3. 前端查询 /api/license/status 展示激活状态；未激活时状态栏提示「产品未激活」。

厂商生成激活码（在 backend/ 目录下执行）：
    python -m app.license --gen                       # 为本机生成
    python -m tools.gen_license --machine=<指纹>      # 为目标机器生成
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import json
import os
import re
import socket
import sys
import uuid

# 厂商签名密钥（模拟：正式产品应置于安全配置，不在代码库明文分发）
_SECRET = b"nengtan-carbon-platform-2026#X7kQ"
_APP_VERSION = "v1"

_LICENSE_RE = re.compile(r"^NENG-[0-9a-fA-F]{4}(?:-[0-9a-fA-F]{4}){3}$")

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
_LICENSE_PATH = os.path.join(_DATA_DIR, "license.json")


# ------------------------- 机器指纹 -------------------------

def _platform_uuid() -> str | None:
    """读取系统级机器 ID（跨进程稳定，避免 uuid.getnode() 因 ifconfig 解析差异不稳定）。

    优先级：Linux /etc/machine-id → macOS IOPlatformUUID → Windows MachineGuid。
    """
    for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                v = f.read().strip()
            if v and len(v) >= 8:
                return v
        except Exception:
            continue
    try:
        import subprocess
        out = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        for line in out.splitlines():
            line = line.strip()
            if line.startswith('"IOPlatformUUID"'):
                m = re.search(r'=\s*"([^"]+)"', line)
                if m:
                    return m.group(1)
    except Exception:
        pass
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Microsoft\Cryptography") as k:
                return winreg.QueryValueEx(k, "MachineGuid")[0]
        except Exception:
            pass
    return None


def machine_id() -> str:
    """机器指纹：系统机器 ID + 主机名的 SHA256 前 16 位 hex（跨进程稳定、免管理员权限）。

    不同进程（CLI / uvicorn worker）计算结果一致，保证激活码在服务端校验通过。
    """
    uid = _platform_uuid() or f"{uuid.getnode():012x}"
    raw = f"{uid}|{socket.gethostname()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# ------------------------- 激活码生成 / 校验 -------------------------

def _sign(mid: str) -> str:
    return hmac.new(_SECRET, f"{mid}|{_APP_VERSION}".encode("utf-8"),
                    hashlib.sha256).hexdigest()[:16]


def gen_license(machine: str | None = None) -> str:
    """为指定机器指纹（缺省为本机）生成激活码，返回 NENG-XXXX-XXXX-XXXX-XXXX。"""
    mid = (machine or machine_id()).lower()
    sig = _sign(mid)
    return "NENG-" + "-".join(sig[i:i + 4] for i in range(0, 16, 4))


def verify(code: str, machine: str | None = None) -> bool:
    """校验激活码是否与目标机器匹配（格式 + HMAC 签名恒定时间比对）。"""
    code = (code or "").strip().upper()
    if not _LICENSE_RE.match(code):
        return False
    mid = (machine or machine_id()).lower()
    expected = "NENG-" + "-".join(_sign(mid)[i:i + 4] for i in range(0, 16, 4))
    return hmac.compare_digest(code, expected.upper())


# ------------------------- 激活状态持久化 -------------------------

def _load() -> dict:
    try:
        with open(_LICENSE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(state: dict) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_LICENSE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_status() -> dict:
    """返回当前激活状态（激活与否 / 绑定指纹 / 激活时间 / 本机指纹）。"""
    st = _load()
    activated = bool(st.get("activated"))
    return {
        "activated": activated,
        "machine_id": machine_id(),
        "bound_machine": st.get("machine_id", ""),
        "activated_at": st.get("activated_at", ""),
        "version": _APP_VERSION,
    }


def activate(code: str) -> tuple[bool, str, dict]:
    """尝试用激活码激活平台。

    返回 (ok, message, status)：
      - ok=False：激活码无效 / 与当前机器不匹配 / 已激活相同机器
      - ok=True：写入持久化文件成功
    """
    code = (code or "").strip()
    if not code:
        return False, "请输入激活码", get_status()

    mid = machine_id()
    if not verify(code, mid):
        return False, "激活码无效或与当前机器不匹配", get_status()

    st = _load()
    if st.get("activated") and st.get("machine_id") == mid:
        return False, "当前机器已激活，无需重复激活", get_status()

    _save({
        "activated": True,
        "machine_id": mid,
        "activated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "code": code.upper(),
    })
    return True, "激活成功", get_status()


# ------------------------- CLI（厂商生成激活码） -------------------------

def _main() -> int:
    machine = None
    for arg in sys.argv[1:]:
        if arg.startswith("--machine="):
            machine = arg.split("=", 1)[1]
        elif arg in ("--gen", "-g"):
            pass
        else:
            print(f"未知参数：{arg}", file=sys.stderr)
            return 2
    mid = machine or machine_id()
    print(f"机器指纹: {mid}")
    print(f"激活码  : {gen_license(mid)}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
