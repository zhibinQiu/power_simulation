"""路径真相源守卫：backend 下所有目录必须由 core.config 派生。

历史上发生过两次「模块下沉导致相对路径层级变化、目录静默漂移」的事故：
  1. domain/scene/scene_registry.py 的 _SCENES_DIR 漂到 app/domain/data/scenes
     → list_scenes() 恒返回 [] → 平台上所有场景包「消失」；
  2. domain/reporting/report_store.py 的 _DIR 漂到 app/domain/data/reports
     → 报告落盘到错位目录，而 JsonRepository 写失败是静默的。

本测试锁死两件事：
  - core.config 的三个目录常量指向正确；
  - app 下任何模块都不得再用 __file__ 自行拼接 config/data 目录。
"""
from __future__ import annotations

import ast
import os
import pathlib

import pytest

from app.core.config import APP_DIR, CONFIG_DIR, DATA_DIR, PROJECT_DIR, config_path, data_path, project_path

BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent          # backend/


def test_dir_constants_point_at_backend():
    assert os.path.realpath(APP_DIR) == str(BACKEND_DIR)
    assert os.path.realpath(CONFIG_DIR) == str(BACKEND_DIR / "config")
    assert os.path.realpath(DATA_DIR) == str(BACKEND_DIR / "data")
    assert os.path.realpath(PROJECT_DIR) == str(BACKEND_DIR.parent)


def test_helpers_join_under_right_root():
    assert config_path("box_config.json").endswith(os.path.join("config", "box_config.json"))
    assert data_path("reports", "index.json").endswith(os.path.join("data", "reports", "index.json"))
    assert project_path("platform", "box-deploy").endswith(os.path.join("platform", "box-deploy"))


def test_no_module_derives_dirs_from_dunder_file():
    """扫描 app/ 下全部 .py：不得出现用 __file__ 拼 config/data 目录的写法。

    允许 main.py 的 PyInstaller 打包路径（sys._MEIPASS 分支，语义不同）。
    """
    offenders = []
    for py in (BACKEND_DIR / "app").rglob("*.py"):
        if py.name == "config.py" and py.parent.name == "core":
            continue                                   # 真相源本身
        if py.name == "main.py":
            continue                                   # 打包路径，非业务目录
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        for node in ast.walk(tree):
            src = ast.unparse(node) if hasattr(ast, "unparse") else ""
            if "__file__" not in src:
                continue
            low = src.lower()
            if "config" in low or "data" in low or "parents[" in src or '".."' in src:
                offenders.append(f"{py.relative_to(BACKEND_DIR)}:{getattr(node, 'lineno', '?')} {src[:90]}")

    assert not offenders, "以下位置仍在用 __file__ 拼接目录，请改用 app.core.config：\n" + "\n".join(offenders)


@pytest.mark.parametrize(
    "module_path,attr",
    [
        ("app.domain.reporting.report_store", "_DIR"),
        ("app.agents.store", "DATA_DIR"),
        ("app.ontology.store", "DATA_DIR"),
        ("app.skills.registry", "DATA_DIR"),
        ("app.services.chat_store", "_DATA_DIR"),
        ("app.services.carbon_compliance_service", "_DATA_DIR"),
        ("app.mqtt_source._shared", "CONFIG_DIR"),
        ("app.mqtt_source.camera_assembler", "DATA_ROOT"),
        ("app.api.help_router", "_CONFIG_DIR"),
        ("app.data_sources.config", "CONFIG_DIR"),
        ("app.box_console._shared", "CONFIG_DIR"),
    ],
)
def test_module_dirs_resolve_under_backend(module_path, attr):
    import importlib

    mod = importlib.import_module(module_path)
    value = str(getattr(mod, attr))
    assert os.path.realpath(value).startswith(str(BACKEND_DIR) + os.sep), f"{module_path}.{attr} = {value}"
