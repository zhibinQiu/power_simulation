"""资源包安装/覆盖/卸载规则测试（backend）。

覆盖链路（scene_registry.install_resource_package —— 「文件 → 打开资源包…」后端承载）：
  全新安装（企业包独立 id 并存）
  内置就绪包：低/同版本拒绝、高版本覆盖升级且保留内置属性（不可卸载）
  占位（ready=false）内置包可直接覆盖
  第三方就绪包：版本门禁 + 可卸载
  仅 .ec：无 ec.json 清单 / 清单 format 非 ec 一律拒绝（无兼容、无宽松形态）

运行：
  cd backend && python -m pytest tests/test_scene_packages.py -v
"""
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.scene import scene_registry  # noqa: E402


def _make_ec_bytes(scene_id, version, ready=True, extra_files=None):
    """构造一个最小可用 .ec（zip）字节串（标准形态：ec.json format=ec）。"""
    meta = {
        "id": scene_id,
        "label": scene_id.replace("-", " ").title(),
        "ready": ready,
        "enterprise": f"企业-{scene_id}",
        "package": {"vendor": "测试厂商", "product": f"{scene_id} 企业资源包", "version": version},
    }
    manifest = {
        "format": "ec",
        "formatVersion": 1,
        "id": scene_id,
        "label": meta["label"],
        "package": {"vendor": "测试厂商", "product": f"{scene_id} 企业资源包", "version": version},
        "files": ["ec.json", "meta.json"],
    }
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ec.json", json.dumps(manifest, ensure_ascii=False))
        zf.writestr("meta.json", json.dumps(meta, ensure_ascii=False))
        zf.writestr("model.json", json.dumps({"units": [], "connections": []}))
        zf.writestr("factors.json", json.dumps({"grid": 0.581}))
        for name, content in (extra_files or {}).items():
            zf.writestr(name, json.dumps(content, ensure_ascii=False))
    return bio.getvalue()


@pytest.fixture()
def scenes_tmp(tmp_path, monkeypatch):
    """把场景注册表指向临时目录，避免污染真实 backend/data/scenes。"""
    monkeypatch.setattr(scene_registry, "_SCENES_DIR", str(tmp_path))
    return str(tmp_path)


def _seed_builtin(tmp, scene_id, version="1.0.0", ready=True):
    """预置一个平台内置场景目录（占位或就绪）。"""
    d = Path(tmp) / scene_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(
        json.dumps(
            {
                "id": scene_id,
                "label": "内置-" + scene_id,
                "ready": ready,
                "package": {"vendor": "能碳生态", "product": "官方包", "version": version, "builtin": True},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_fresh_install_builtin_false_then_uninstall(scenes_tmp):
    """全新安装（企业包独立 id）：builtin=False、可卸载、可重装。"""
    raw = _make_ec_bytes("acme-steel", "1.0.0")
    r = scene_registry.install_resource_package(raw)
    assert r["ok"] and r["replaced"] is False
    assert r["scene"]["package"]["builtin"] is False
    assert r["scene"]["ready"] is True
    assert (Path(scenes_tmp) / "acme-steel" / "model.json").exists()

    # 同版本再次安装：已就绪包拒绝（版本未提高）
    r2 = scene_registry.install_resource_package(raw)
    assert r2["ok"] is False and "未高于现有版本" in r2["error"]

    # 升级后再卸载
    assert scene_registry.uninstall_resource_package("acme-steel")["ok"] is True
    # 目录已删除，可重新安装
    assert scene_registry.install_resource_package(raw)["ok"] is True


def test_only_ec_manifest_enforced(scenes_tmp):
    """仅接受 .ec 完整清单形态：缺 ec.json 或 format 非 ec 一律拒绝（无宽松/兼容）。"""
    # 缺 ec.json（只有 meta.json，模拟旧宽松形态）→ 拒绝
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "meta.json",
            json.dumps(
                {
                    "id": "acme-loose",
                    "label": "Acme Loose",
                    "ready": True,
                    "package": {"vendor": "测试厂商", "product": "宽松包", "version": "1.0.0"},
                },
                ensure_ascii=False,
            ),
        )
        zf.writestr("model.json", json.dumps({"units": []}))
    r = scene_registry.install_resource_package(bio.getvalue())
    assert r["ok"] is False and "ec.json" in r["error"]

    # 清单 format 非 ec（如旧 format=qzb）→ 拒绝
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "ec.json",
            json.dumps({"format": "qzb", "formatVersion": 1, "id": "acme-qzb"}),
        )
        zf.writestr(
            "meta.json",
            json.dumps({"id": "acme-qzb", "label": "Acme Qzb", "ready": True}),
        )
    r = scene_registry.install_resource_package(bio.getvalue())
    assert r["ok"] is False and "非 ec 格式" in r["error"]

    # 注册表未被污染
    assert scene_registry.get_scene("acme-loose") is None
    assert scene_registry.get_scene("acme-qzb") is None


def test_builtin_low_or_equal_version_rejected(scenes_tmp):
    """内置就绪包：低/同版本覆盖被拒（修复前：一律被拒 → 现在版本门禁）。"""
    _seed_builtin(scenes_tmp, "steel", version="2.0.0", ready=True)
    for v in ("1.0.0", "2.0.0", "v1.9.9"):
        r = scene_registry.install_resource_package(_make_ec_bytes("steel", v))
        assert r["ok"] is False and "未高于现有版本" in r["error"], v


def test_builtin_higher_version_upgrade_keeps_builtin(scenes_tmp):
    """内置就绪包：更高版本 .ec 可覆盖升级（此前“无法打开”根因），内置属性保留、不可卸载。"""
    _seed_builtin(scenes_tmp, "steel", version="1.0.0", ready=True)
    r = scene_registry.install_resource_package(_make_ec_bytes("steel", "2.0.0"))
    assert r["ok"] and r["replaced"] is True
    scene = scene_registry.get_scene("steel")
    assert scene["package"]["builtin"] is True, "覆盖内置后应保留内置属性"
    assert scene["package"]["version"] == "2.0.0"
    assert scene["package"].get("updatedAt")
    assert scene["enterprise"] == "企业-steel"

    # 内置升级后依然禁止卸载
    u = scene_registry.uninstall_resource_package("steel")
    assert u["ok"] is False and "不可卸载" in u["error"]


def test_placeholder_builtin_can_be_overwritten(scenes_tmp):
    """占位/未就绪内置包（如水泥/化工/有色）无需版本门禁，直接覆盖。"""
    _seed_builtin(scenes_tmp, "cement", version="0.0.0", ready=False)
    r = scene_registry.install_resource_package(_make_ec_bytes("cement", "0.9.0"))
    assert r["ok"] and r["replaced"] is True
    assert scene_registry.get_scene("cement")["package"]["builtin"] is True


def test_third_party_package_version_gate_and_uninstall(scenes_tmp):
    """第三方已装包同样受版本门禁；升级后为非内置可卸载。"""
    raw = _make_ec_bytes("acme-dc", "1.0.0")
    assert scene_registry.install_resource_package(raw)["ok"] is True
    assert scene_registry.install_resource_package(_make_ec_bytes("acme-dc", "1.0.0"))["ok"] is False
    assert scene_registry.install_resource_package(_make_ec_bytes("acme-dc", "1.0.1"))["ok"] is True
    assert scene_registry.get_scene("acme-dc")["package"]["builtin"] is False
    assert scene_registry.uninstall_resource_package("acme-dc")["ok"] is True


def test_parse_version():
    """版本解析：v 前缀/多段号均可比较。"""
    assert scene_registry._parse_version("v2.0.0") == (2, 0, 0)
    assert scene_registry._parse_version("2") == (2,)
    assert scene_registry._parse_version("1.10") > scene_registry._parse_version("1.9")
    assert scene_registry._parse_version("1.0.0") < scene_registry._parse_version("2.0.0")
    assert scene_registry._parse_version(None) == (0,)
