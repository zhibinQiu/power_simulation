"""场景资源包统一接口层（平台「资源按场景加载」/「资源包文件装载」/「导出」）。

架构约定：平台前端壳只消费包结构，不针对企业写死——资源包 = 面向具体企业的
.ec 文件（行业仅为其内 industry 分类标签）：
  GET    /api/scenes                  -> 全部场景 meta（含 ready/package/method/enterprise）
  GET    /api/scene/{id}/resource     -> 场景资源包（meta + resources）
  POST   /api/scene/package           -> 打开资源包：上传 .ec 并安装
                                          （multipart: file；同名就绪场景须更高版本才能覆盖升级）
  DELETE /api/scene/package/{id}      -> 卸载资源包（内置包拒绝）
  POST   /api/scene/export            -> 「导出场景包」：当前场景资源（含可选覆盖
                                          templates 编排快照）打包为 .ec 下载
"""
from __future__ import annotations

import os

from typing import Any, Dict, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from ..domain.scene import scene_loader, scene_registry

router = APIRouter()


@router.get("/api/scenes")
def list_scenes():
    """返回平台已注册的仿真场景（含资源包就绪状态），驱动前端场景入口。"""
    return scene_registry.list_scenes()


@router.get("/api/scene/{scene_id}/resource")
def get_scene_resource(scene_id: str):
    """按场景加载其自带资源包（统一入口）。"""
    pkg = scene_loader.load_scene_package(scene_id)
    if pkg is None:
        raise HTTPException(status_code=404, detail="scene not found")
    return pkg


@router.post("/api/scene/package")
async def install_scene_package(file: UploadFile = File(...)):
    """「打开资源包」的后端承载：上传 .ec 并安装注册。

    资源包实际后缀 = .ec（标准 zip）：面向企业/组织的定制仿真包，内含 ec.json
    清单（format=ec）与 meta.json、该企业场景的全部配置（model/templates/
    factors/devices…）；仅接受 .ec 扩展名与完整清单形态。
    """
    try:
        data = await file.read()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"读取资源包文件失败：{e}"}
    if not data:
        return {"ok": False, "error": "资源包文件为空"}
    if (os.path.splitext(file.filename or "")[1].lower()) != ".ec":
        return {"ok": False, "error": f"仅支持 .ec 资源包文件（当前：{os.path.basename(file.filename or '(空)')}）"}
    return scene_registry.install_resource_package(data)


@router.delete("/api/scene/package/{scene_id}")
def uninstall_scene_package(scene_id: str):
    """卸载一个已安装的 .ec 资源包（平台内置包拒绝）。"""
    return scene_registry.uninstall_resource_package(scene_id)


@router.post("/api/scene/export")
def export_scene_package(payload: Dict[str, Any]):
    """「文件 → 导出场景包…(.ec)」：把某场景当前资源打包为可分发的 .ec 下载。

    支持把「当前编排方案快照」作为 templates 覆盖随包下发（meta 同步改
    defaultRoute），从而导出后重新加载即回到编排态；也可对内置官方包（钢铁 /
    机房温控）直接导出分发到未安装该行业的其它实例。
    """
    scene_id = (payload or {}).get("scene_id")
    if not scene_registry._valid_scene_id(str(scene_id or "")):  # noqa: SLF001 —— 同模块复用
        raise HTTPException(status_code=400, detail="场景标识非法")
    overrides: Optional[Dict[str, Any]] = {}
    if payload.get("templates") is not None:
        overrides["templates"] = payload["templates"]
    meta_patch: Dict[str, Any] = dict(payload.get("meta") or {})
    pkg = payload.get("package") or {}
    version = pkg.get("version") if isinstance(pkg, dict) else None
    vendor = pkg.get("vendor") if isinstance(pkg, dict) else None
    product = pkg.get("product") if isinstance(pkg, dict) else None
    # 导出版一律按「非内置分发包」标记（安装侧 scene_registry 也会强制回写 builtin=False）
    mpkg = dict((meta_patch.get("package") or {}))
    mpkg["builtin"] = False
    if vendor:
        mpkg["vendor"] = vendor
    if product:
        mpkg["product"] = product
    if version:
        mpkg["version"] = version
    meta_patch["package"] = mpkg
    try:
        raw = scene_loader.build_resource_package_bytes(
            scene_id,
            version=version,
            vendor=vendor,
            product=product,
            overrides=overrides or None,
            meta_patch=meta_patch or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return Response(
        content=raw,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{scene_id}.ec"'},
    )
