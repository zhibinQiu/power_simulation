"""「云端/边缘重启」功能回归测试（backend）。

覆盖根因：BoxCloudRestartRequest 曾为空壳模型（无字段定义），
req.kind / req.name 访问抛 AttributeError → 端点 500。
本测试锁定：模型字段存在、解析正确、端点参数正确传递、缺 name 返回友好错误而非 500。

运行：
  cd backend && python -m pytest tests/test_box_cloud_restart.py -v
（不依赖真实云端：restart_cloud_workload 用 mock）
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.box_router import BoxCloudRestartRequest, box_cloud_restart  # noqa: E402
from app import box_console  # noqa: E402


# ---------------------------------------------------------------------------
# 模型：防止再变成「只有 docstring、没有字段」的空壳
# ---------------------------------------------------------------------------
def test_model_has_required_fields():
    fields = set(BoxCloudRestartRequest.model_fields.keys())
    assert {"kind", "name", "namespace"} <= fields, f"缺少字段，当前字段: {fields}"


def test_model_parse_edge():
    req = BoxCloudRestartRequest(kind="edge", name="box-mapper")
    assert req.kind == "edge"
    assert req.name == "box-mapper"
    assert req.namespace == "default"  # 默认命名空间


def test_model_parse_defaults():
    req = BoxCloudRestartRequest.model_validate({"kind": "deployment"})
    assert req.kind == "deployment"
    assert req.name == ""
    assert req.namespace == "default"


# ---------------------------------------------------------------------------
# 端点：参数传递正确；缺 name 返回友好错误而非 500
# ---------------------------------------------------------------------------
def test_endpoint_passes_args(monkeypatch):
    captured = {}

    def fake_restart(kind, name, namespace):
        captured.update(kind=kind, name=name, namespace=namespace)
        return {"ok": True, "kind": kind, "name": name}

    monkeypatch.setattr(box_console, "restart_cloud_workload", fake_restart)
    res = box_cloud_restart(BoxCloudRestartRequest(kind="edge", name="box-mapper"))
    assert res["ok"] is True
    assert captured == {"kind": "edge", "name": "box-mapper", "namespace": "default"}


def test_endpoint_missing_name_returns_friendly_error(monkeypatch):
    """缺 name 不应 500：_K8S_NAME_RE 校验返回 ok:false 友好错误。"""
    calls = []

    def fake_restart(kind, name, namespace):
        calls.append((kind, name, namespace))
        return {"ok": False, "error": "云端对象名不合法"}

    monkeypatch.setattr(box_console, "restart_cloud_workload", fake_restart)
    res = box_cloud_restart(BoxCloudRestartRequest(kind="edge"))
    assert res["ok"] is False
    assert calls == [("edge", "", "default")]
