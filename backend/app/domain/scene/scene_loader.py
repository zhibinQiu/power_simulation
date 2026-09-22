"""场景资源包统一加载器：把某个场景「自带的一套资源」聚合为一份资源包下发。

平台前端壳只消费本加载器返回的包结构：
  {
    meta:      场景元信息（含 engines / package / method / ready / routes …）
    ready:     是否齐备
    note:      未齐备时的说明
    resources: { model, strategies, factors, paramSchema, devices, methods }  # ready 场景
  }

资源形态（二选一，优先「包文件形态」，与 .ec 安装目录天然一致）：
1) 包文件形态：backend/data/scenes/{id}/ 目录内直接存放 model.json /
   strategies.json / factors.json / param-schema.json / devices.json / methods.json
   ——安装（打开）.ec 企业资源包后即为该形态，平台通用加载，不针对企业写死；
2) 平台内置引擎形态：目录只有 meta.json，走下方 _READY_AGGREGATORS
   （steel 复用核心仿真服务既有数据源，单一真源，向后兼容）。

方法学（methods）：核算方法学以声明式数据随包下发（方法名/依据标准/边界/
排放源/引擎 key），真实计算由平台核算引擎注册表按 meta.engines 分发执行。
"""
from __future__ import annotations

import io
import json
import os
import zipfile
from typing import Any, Dict, List, Optional

from . import scene_registry
from app.application.simulation_service import simulation_service

# 包文件形态：资源 key -> 目录内文件名
# templates.json = 行业预置方案模板快照（流程字典场景化：模板 = 包数据，不再写死在前端代码）；
# dictionary.json = 行业素材字典数据面（物料/产品/工艺/设备目录，供平台 UI 渲染该行业素材）；
# config.json  = 场景引擎默认配置（引擎参数出厂值，行业可选携带）；
# devices.json = 场景设备目录（设备类型/寄存器映射等）。
# 以上均属行业包资产：由 tools/pack_ec.py 收进 .ec、安装后由本加载器随包下发。
PACK_FILES = {
    "model": "model.json",
    "strategies": "strategies.json",
    "factors": "factors.json",
    "paramSchema": "param-schema.json",
    "devices": "devices.json",
    "methods": "methods.json",
    "templates": "templates.json",
    "dictionary": "dictionary.json",
    "config": "config.json",
}

# 兼容旧引用（外部按 _PACK_FILES 引用的打包器）
_PACK_FILES = PACK_FILES

# 钢铁核算方法学（随钢包下发；公式级物理模型在平台引擎插件 steel-carbon 内实现）
_STEEL_METHODS = [
    {
        "id": "method-steel-process",
        "name": "钢铁工序能碳核算方法学（工序物料/能量平衡 + 排放因子法）",
        "engine": "steel-carbon",
        "standard": ["GB/T 32151.5-2015", "GB 21256-2013", "GB/T 21370-2017"],
        "scope": [
            "范围一：燃料燃烧排放、石灰石等熔剂过程排放",
            "范围二：外购电力/热力间接排放",
            "扣减项：外销电力/固碳产品（如转炉煤气利用）",
        ],
        "sources": ["烧结/球团", "焦化", "高炉炼铁", "转炉/电炉炼钢", "连铸", "轧钢"],
    }
]


def _read_package_json(path: str) -> Optional[Any]:
    """读包文件 JSON：model/param-schema/factors 为对象，strategies/methods 为数组。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _package_dir_resources(scene_id: str) -> Optional[Dict[str, Any]]:
    """包文件形态加载：目录内含 model.json 或 config.json 即视为完整安装包；
    仅占位/纯聚合目录（内置 steel 只带 templates/dictionary 配套数据，走下方聚合器）
    或只有模板的目录返回 None，由调用方决定是否走聚合器。"""
    d = scene_registry.scene_dir(scene_id)
    if not os.path.isdir(d):
        return None
    if not any(os.path.isfile(os.path.join(d, f)) for f in ("model.json", "config.json")):
        return None
    resources: Dict[str, Any] = {}
    for key, fname in _PACK_FILES.items():
        val = _read_package_json(os.path.join(d, fname))
        if val is not None:
            resources[key] = val
    return resources


def _aggregate_steel_resources() -> Dict[str, Any]:
    """平台内置钢包资源聚合：复用核心仿真服务既有数据源（单一真源，legacy 路径）。

    预置方案模板（templates.json）与行业素材字典（dictionary.json）已迁移为钢包目录
    数据文件（backend/data/scenes/steel/，由前端 tools/export-scene-assets.mjs 从
    flowLibrary 冻结导出）——聚合时直接随包带上，与 .ec 安装包形态一致。
    """
    model = simulation_service.get_preset()
    resources = {
        "model": model.model_dump(mode="json") if hasattr(model, "model_dump") else model,
        "strategies": simulation_service.get_preset_strategies(),
        "factors": simulation_service.get_factors(),
        "paramSchema": simulation_service.get_param_schema(),
        "devices": simulation_service.get_devices(),
        "methods": _STEEL_METHODS,
    }
    steel_dir = scene_registry.scene_dir("steel")
    for key, fname in (("templates", "templates.json"), ("dictionary", "dictionary.json")):
        val = _read_package_json(os.path.join(steel_dir, fname))
        if val is not None:
            resources[key] = val
    return resources


# 场景 -> 平台内置资源聚合器（引擎插件注册表的「资源供给」侧挂点）。
# steel 使用现有碳引擎相关 service（工艺/系数/参数/设备）；新行业引擎在此注册，
# 或者直接以 .ec 包安装（包文件形态，无需注册任何代码）。
_READY_AGGREGATORS: Dict[str, Any] = {
    "steel": {
        "engine": "steel-carbon",
        "aggregate": _aggregate_steel_resources,
    },
}


def load_scene_package(scene_id: str) -> Optional[Dict[str, Any]]:
    """按场景 id 加载完整资源包；未注册场景返回 None（调用方 404）。"""
    meta = scene_registry.get_scene(scene_id)
    if meta is None:
        return None

    if not meta.get("ready"):
        return {
            "meta": meta,
            "ready": False,
            "note": "该行业资源包尚未安装：请通过 文件 → 打开资源包… 安装 .ec 资源包。",
            "resources": None,
        }

    # 1) 包文件形态（.ec 安装目录）
    resources = _package_dir_resources(scene_id)
    if resources is not None:
        return {"meta": meta, "ready": True, "note": None, "resources": resources}

    # 2) 平台内置引擎形态（legacy 聚合器）
    agg = _READY_AGGREGATORS.get(scene_id)
    if agg is None:
        return {
            "meta": meta,
            "ready": False,
            "note": "该资源包已注册但未提供可加载的资源实现（包文件缺失且无内置聚合器）。",
            "resources": None,
        }

    try:
        resources = agg["aggregate"]()
    except Exception as _e:  # noqa: BLE001 —— 聚合失败不让整个接口 500，降级为建设中
        return {
            "meta": meta,
            "ready": False,
            "note": f"该场景资源包加载失败：{_e}",
            "resources": None,
        }
    return {"meta": meta, "ready": True, "note": None, "resources": resources}


# ---------------------------------------------------------------------------
# .ec 构建（平台内置包打包 / 「另存为资源包…」导出 共用同一真源）
# ---------------------------------------------------------------------------

# .ec 包体积上限（与 scene_registry 安装侧一致；导出同样防空炸）
_MAX_PACK_BYTES = 64 * 1024 * 1024
# 导出覆盖模板条数上限（防御异常大 payload）
_MAX_TEMPLATES = 400


def build_resource_package_bytes(
    scene_id: str,
    version: Optional[str] = None,
    vendor: Optional[str] = None,
    product: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None,
    meta_patch: Optional[Dict[str, Any]] = None,
) -> bytes:
    """把某场景聚合的资源打包为 .ec 字节串。

    - overrides: 覆盖/注入资源（键须 ∈ PACK_FILES，如导出版把「当前编排方案快照」
      作为 templates 随包下发）；
    - meta_patch: 顶层 meta 字段覆盖（如导出定制包时改写 defaultRoute / package）。
    """
    meta = scene_registry.get_scene(scene_id)
    if not meta:
        raise ValueError(f"未找到场景 {scene_id}（backend/data/scenes/{scene_id}/meta.json）")
    pkg = load_scene_package(scene_id)
    if not pkg or not pkg.get("ready") or not pkg.get("resources"):
        raise ValueError(f"场景 {scene_id} 资源未就绪，无法打包（note={pkg and pkg.get('note')}）")

    resources: Dict[str, Any] = dict(pkg["resources"])
    if overrides:
        bad = [k for k in overrides if k not in _PACK_FILES]
        if bad:
            raise ValueError(f"不支持的导出资源键：{','.join(bad)}")
        tpls = overrides.get("templates")
        if tpls is not None:
            if not isinstance(tpls, list) or not tpls or len(tpls) > _MAX_TEMPLATES:
                raise ValueError(f"导出模板数量非法（1~{_MAX_TEMPLATES} 条）")
        resources.update(overrides)

    meta_out: Dict[str, Any] = dict(meta)
    if meta_patch:
        meta_out.update({k: v for k, v in meta_patch.items()})

    meta_pkg = meta_out.get("package") or {}
    manifest = {
        "format": "ec",
        "formatVersion": 1,
        "kind": "industry-simulation",
        "id": scene_id,
        "label": meta_out.get("label", scene_id),
        "package": {
            "vendor": vendor or meta_pkg.get("vendor") or "能碳生态",
            "product": product or meta_pkg.get("product")
            or f"{meta_out.get('label', scene_id)}行业能碳仿真资源包",
            "version": version or meta_pkg.get("version") or "1.0.0",
        },
        "engines": list(meta_out.get("engines") or []),
        "files": ["ec.json", "meta.json"]
        + [fname for k, fname in _PACK_FILES.items() if k in resources],
    }

    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ec.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("meta.json", json.dumps(meta_out, ensure_ascii=False, indent=2))
        for k, fname in _PACK_FILES.items():
            if k in resources:
                zf.writestr(fname, json.dumps(resources[k], ensure_ascii=False, indent=2))
    raw = bio.getvalue()
    if len(raw) > _MAX_PACK_BYTES:
        raise ValueError(f"资源包超过体积上限（{_MAX_PACK_BYTES // (1024 * 1024)}MB）")
    return raw
