"""场景注册表：平台支持的仿真场景及其「资源包」元数据与生命周期。

架构约定（平台 ⇄ 资源包彻底抽离）：
- 平台 = 通用壳：渲染/仿真运行时、通用算法（PID/EKF/PPO 等，只对接数据）、
  核算执行框架——不针对任何企业/行业写死；
- 资源包 = .ec 文件（标准 zip）：面向【具体企业/组织】的仿真包，内含该企业
  场景的全部配置/属性与核算方法学（meta.json + model/strategies/factors/
  param-schema/devices/methods…）。行业只是包内标签分类（industry 字段），
  资源包本身是企业实体——不同企业各自独立装包、注册表并存。
  打开资源包 = 安装到 backend/data/scenes/{id}/，注册表即自动发现。
- 平台预置包（builtin）亦以同一形态注册，内置字段标识、禁止卸载；
  允许用更高版本（package.version）的同名 .ec 覆盖升级（官方/企业包演进），
  覆盖后保留内置属性、仍禁止卸载。

meta.json 通用字段：
- id: 场景标识（与目录同名；企业包建议用企业/项目标识，如 jt-steel-01）
- label: 展示名
- enterprise: 本资源包面向的企业/组织名（资源包=企业级实体，非行业模板）
- industry: 行业分类标签（钢铁/机房温控/水泥…，仅作展示分类，非包粒度）
- kind: 场景域（process=控排工艺仿真，thermal=热工孪生等）
- order: 展示排序
- ready: 资源包是否齐备（工艺模板/物料/系数/引擎齐全后可交付仿真）
- icon/color: 展示辅助
- engines: 引擎插件注册表（核算引擎模块 id，新场景挂接新引擎时在此登记）
- package: 包分发元信息 {vendor, product, version, builtin}
- method: 核算方法学摘要 {name, engine, standard}
- resources: 该场景资源清单（preset-model/strategy/factor/param-schema/device/methods…）
- shortDesc/intro: 场景简介
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import time
import zipfile
from typing import Any, Dict, List, Optional

from ...core.config import DATA_DIR

# backend/data/scenes（统一走配置中心 core.config.DATA_DIR，与模块位置/CWD 无关）
# 注意：本模块曾在 2026-09-21 的 app 顶层模块下沉中从 backend/app/ 搬到这里，
# 旧写法 os.path.join(dirname(__file__), "..", "data", "scenes") 会随之漂移到
# backend/app/domain/data/scenes（不存在）→ list_scenes() 恒返回 [] → 资源包场景
# （如机房热控 dc-thermal）在平台上全部「消失」，且安装 .ec 会落到错误目录。
_SCENES_DIR = os.path.normpath(os.path.join(DATA_DIR, "scenes"))

# .ec 资源包上传体积上限：64MB（安全阀，防异常/恶意大包打满磁盘）
_MAX_PACK_BYTES = 64 * 1024 * 1024

# 场景 id 白名单：仅小写字母/数字/下划线/连字符（作为目录名，杜绝路径注入）
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")


def _valid_scene_id(scene_id: str) -> bool:
    return bool(scene_id and _ID_RE.match(scene_id))


def _parse_version(version) -> tuple:
    """宽松解析包版本（'v2.0.0' / '2.0' / '2'）为可比较元组；解析失败视为 0。"""
    s = re.sub(r"^[vV]", "", str(version or "").strip())
    nums = re.findall(r"\d+", s)
    return tuple(int(x) for x in nums[:4]) or (0,) if nums else (0,)


def _version_label(version) -> str:
    return str(version or "").strip() or "0"


def scene_dir(scene_id: str) -> str:
    """场景资源目录（绝对路径）。调用方需自行确保 id 合法后再拼路径。"""
    return os.path.join(_SCENES_DIR, scene_id)


def _read_meta(scene_id: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(_SCENES_DIR, scene_id, "meta.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict) or not meta.get("id"):
        return None
    return meta


def list_scenes() -> List[Dict[str, Any]]:
    """返回全部已注册场景的 meta（按 order 排序）。"""
    scenes: List[Dict[str, Any]] = []
    try:
        entries = sorted(os.listdir(_SCENES_DIR))
    except OSError:
        entries = []
    for name in entries:
        if not name or name.startswith(".") or not os.path.isdir(os.path.join(_SCENES_DIR, name)):
            continue
        meta = _read_meta(name)
        if meta:
            scenes.append(meta)
    scenes.sort(key=lambda m: m.get("order", 99))
    return scenes


def get_scene(scene_id: str) -> Optional[Dict[str, Any]]:
    """按 id 查询场景 meta（未注册返回 None）。"""
    if not scene_id:
        return None
    return _read_meta(scene_id)


def scene_is_ready(scene_id: str) -> bool:
    meta = get_scene(scene_id)
    return bool(meta and meta.get("ready"))


def engines_of(scene_id: str) -> List[str]:
    """该场景登记的核算引擎插件（引擎插件注册表挂点）。"""
    meta = get_scene(scene_id)
    return list((meta or {}).get("engines") or [])


# ---------------------------------------------------------------------------
# .ec 资源包 安装 / 卸载（文件 → 打开资源包… 的后端承载）
# ---------------------------------------------------------------------------

def _extract_zip_safe(zf: zipfile.ZipFile, dest: str) -> None:
    """安全解压：逐条校验相对路径，拒绝路径穿越 / 绝对路径 / 软链逃逸。"""
    base = os.path.normpath(dest)
    for member in zf.infolist():
        rel = member.filename.replace("\\", "/").lstrip("/")
        if not rel or rel.startswith("../") or "/../" in rel or rel == "..":
            continue
        target = os.path.normpath(os.path.join(base, rel))
        if target != base and not target.startswith(base + os.sep):
            continue  # 越界条目丢弃
        if member.is_dir():
            os.makedirs(target, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with zf.open(member) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)


def install_resource_package(data: bytes) -> Dict[str, Any]:
    """安装一个 .ec 资源包文件（标准 zip 容器）：校验 → 注册表冲突检查 → 解压到 scenes/{id}。

    .ec = 完整清单形态：根目录须含 ec.json 清单（format=ec，含 package.version 等
    分发元信息）与 meta.json、model.json 等资源；缺清单/格式不符一律拒绝（无宽松免清单形态）。

    返回 {ok, scene?, manifest?, replaced?, error?}；错误语义统一 error 文本。
    """
    if not data:
        return {"ok": False, "error": "资源包内容为空"}
    if len(data) > _MAX_PACK_BYTES:
        return {"ok": False, "error": f"资源包超过体积上限（{_MAX_PACK_BYTES // (1024 * 1024)}MB）"}
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        bad = zf.testzip()
        if bad:
            return {"ok": False, "error": f"资源包校验失败（文件损坏：{bad}）"}
    except zipfile.BadZipFile:
        return {"ok": False, "error": "不是有效的 .ec 资源包（应为标准 zip）"}

    # 1) 清单与元数据（先内存解析，全部通过后再落地，防恶意包半装）
    try:
        manifest = json.loads(zf.read("ec.json"))
    except KeyError:
        return {"ok": False, "error": "资源包缺少清单 ec.json（.ec 资源包须含 ec.json + meta.json）"}
    except ValueError:
        return {"ok": False, "error": "清单 ec.json 内容非法"}
    if not isinstance(manifest, dict) or manifest.get("format") != "ec":
        return {"ok": False, "error": "非 ec 格式的资源包（清单 format 须为 ec）"}
    if manifest.get("formatVersion", 1) != 1:
        return {"ok": False, "error": f"暂不支持该资源包版本（formatVersion={manifest.get('formatVersion')}）"}

    try:
        meta = json.loads(zf.read("meta.json"))
    except (KeyError, ValueError):
        return {"ok": False, "error": "资源包缺少 meta.json"}
    if not isinstance(meta, dict):
        return {"ok": False, "error": "meta.json 内容非法"}
    sid = meta.get("id")
    if not _valid_scene_id(sid):
        return {"ok": False, "error": f"资源包标识非法：{sid!r}"}
    mid = manifest.get("id")
    if mid and mid != sid:
        return {"ok": False, "error": f"清单 id({mid})与 meta id({sid})不一致"}

    # 2) 注册表冲突检查：已就绪场景（含平台内置包）允许用「更高版本」同名包覆盖升级
    #    ——资源包面向具体企业，官方/企业包会随模型迭代发新版；低于/等于现有版本拒绝，
    #    防旧包回滚或同名包顶替。仅占位/未就绪（ready=false）的目录不设门槛直接覆盖。
    existing = get_scene(sid)
    if existing and existing.get("ready"):
        cur_pkg = existing.get("package") or {}
        new_pkg = (manifest or {}).get("package") or (meta.get("package") or {})
        cur_v, new_v = _parse_version(cur_pkg.get("version")), _parse_version(new_pkg.get("version"))
        if not new_v or new_v <= cur_v:
            cur_lbl = existing.get("label") or sid
            cur_ver, new_ver = _version_label(cur_pkg.get("version")), _version_label(new_pkg.get("version"))
            return {"ok": False, "error": (
                f"「{cur_lbl}」资源包 v{cur_ver} 已就绪：新包 v{new_ver} 未高于现有版本，"
                f"覆盖安装被拒绝（资源包面向具体企业，请确认清单 package.version 后重试）"
            )}

    # 3) 落地：整目录替换（占位/旧版包先清空），保证注册表与磁盘一致
    dest = scene_dir(sid)
    replaced = existing is not None
    try:
        shutil.rmtree(dest, ignore_errors=True)
        os.makedirs(dest, exist_ok=True)
        _extract_zip_safe(zf, dest)
    except OSError as e:
        return {"ok": False, "error": f"资源包安装落盘失败：{e}"}

    # 4) 回写包分发元信息（vendor/product/version 取清单）
    #    - 覆盖既有场景（含内置包高版本升级）时保留 builtin 官方属性：禁止卸载；
    #    - 全新安装/第三方包 builtin=False，可卸载。
    was_builtin = bool(existing and (existing.get("package") or {}).get("builtin"))
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    pkg_meta = dict(meta)
    pkg_meta["package"] = {
        **(manifest.get("package") or {}),
        "vendor": (manifest.get("package") or {}).get("vendor") or "未知厂商",
        "product": (manifest.get("package") or {}).get("product") or pkg_meta.get("label", sid),
        "version": (manifest.get("package") or {}).get("version") or "1.0.0",
        "builtin": was_builtin,
        "updatedAt": ts if existing else pkg_meta.get("package", {}).get("installedAt") or ts,
    }
    if not existing and not pkg_meta["package"].get("installedAt"):
        pkg_meta["package"]["installedAt"] = ts
    pkg_meta["ready"] = bool(pkg_meta.get("ready"))
    try:
        with open(os.path.join(dest, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(pkg_meta, f, ensure_ascii=False, indent=2)
    except OSError as e:
        return {"ok": False, "error": f"资源包注册信息写入失败：{e}"}

    return {
        "ok": True,
        "scene": get_scene(sid),
        "manifest": manifest,
        "replaced": replaced,
    }


def uninstall_resource_package(scene_id: str) -> Dict[str, Any]:
    """卸载一个 .ec 资源包（删除场景目录）；平台内置包拒绝卸载。"""
    if not _valid_scene_id(scene_id):
        return {"ok": False, "error": f"资源包标识非法：{scene_id!r}"}
    meta = get_scene(scene_id)
    if meta is None:
        return {"ok": False, "error": f"资源包不存在：{scene_id}"}
    if (meta.get("package") or {}).get("builtin"):
        return {"ok": False, "error": f"「{meta.get('label', scene_id)}」为平台内置资源包，不可卸载"}
    try:
        shutil.rmtree(scene_dir(scene_id), ignore_errors=True)
    except OSError as e:
        return {"ok": False, "error": f"资源包卸载失败：{e}"}
    if get_scene(scene_id) is not None:
        return {"ok": False, "error": "资源包目录仍存在，卸载未生效"}
    return {"ok": True, "removed": scene_id}
