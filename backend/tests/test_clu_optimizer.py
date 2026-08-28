"""AI 优化模型「聚类工况识别」（optimizers.ClusteringOptimizer，ai::clu）测试用例（backend）。

运行：
  cd backend && python -m pytest tests/test_clu_optimizer.py -v
（纯算法单测：不依赖真实网络 / Broker）
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import ProcessModel, Unit  # noqa: E402
from app.optimizers import OPTIMIZERS, get_optimizer  # noqa: E402
from app.realtime import DEVICE_HISTORY, DEVICE_META  # noqa: E402

# 含 kind='optim' 参数的最小流程模型（风量 / 热风温度 / 富氧率）
_MODEL = ProcessModel(
    units=[
        Unit(id="bf1", type="blast_furnace", name="高炉",
             params={"wind_rate": 500.0, "hot_blast_temp": 1100.0, "oxygen_enrich": 3.0}),
    ],
    flows=[],
)


@pytest.fixture(autouse=True)
def _clean_realtime():
    orig_h = dict(DEVICE_HISTORY)
    orig_m = dict(DEVICE_META)
    DEVICE_HISTORY.clear()
    DEVICE_META.clear()
    yield
    DEVICE_HISTORY.clear()
    DEVICE_HISTORY.update(orig_h)
    DEVICE_META.clear()
    DEVICE_META.update(orig_m)


def _seed_history(high=90.0, low=20.0):
    """注入两组分离的工况读数（高负荷 / 低负荷），时间戳落在最近 10 分钟窗口内。"""
    t = time.time()
    DEVICE_HISTORY["dev_high"] = [{"t": t - 300 + i * 10, "v": high + (i % 3)} for i in range(40)]
    DEVICE_HISTORY["dev_low"] = [{"t": t - 300 + i * 10, "v": low + (i % 2)} for i in range(40)]
    DEVICE_META["dev_high"] = {"label": "高负荷风机", "unit": "kW", "unit_name": "电耗", "unit_type": "power"}
    DEVICE_META["dev_low"] = {"label": "低负荷风机", "unit": "kW", "unit_name": "电耗", "unit_type": "power"}


def _ready_clu():
    o = get_optimizer("ai::clu")
    o.setup(_MODEL, {})
    o.running = True
    return o


# ------------------------- 注册与基础状态 -------------------------

def test_clu_registered():
    o = OPTIMIZERS.get("ai::clu")
    assert o is not None
    assert o.kind == "clu"
    assert o.name == "聚类工况识别"
    assert sorted(o.hyperparams.keys()) == ["eps", "k", "min_pts", "samples"]
    assert [m["id"] for m in o.state()["methods"]] == ["kmeans", "dbscan", "hierarchical"]


def test_clu_state_unready():
    """未 setup 时 state() 不抛错：method 默认 kmeans、clusters 为空。"""
    o = get_optimizer("ai::clu")
    st = o.state()
    assert st["ready"] is False
    assert st["method"] == "kmeans"
    assert st["clusters"] == []
    assert st["compactness"] == 0.0


def test_clu_setup_ready():
    _seed_history()
    o = _ready_clu()
    assert o.ready
    assert o.space, "流程模型应包含可优化参数"
    assert o.iteration == 0


# ------------------------- 前向填充取值 -------------------------

def test_val_at_forward_fill():
    pts = [{"t": 10.0, "v": 1.0}, {"t": 20.0, "v": 2.0}, {"t": 30.0, "v": 3.0}]
    assert CluUtil().val_at(pts, 5.0) == 1.0   # 早于首点 → 首点
    assert CluUtil().val_at(pts, 15.0) == 1.0  # 前向填充
    assert CluUtil().val_at(pts, 25.0) == 2.0
    assert CluUtil().val_at(pts, 35.0) == 3.0  # 晚于末点 → 末点


class CluUtil:
    @staticmethod
    def val_at(pts, t):
        return get_optimizer("ai::clu")._val_at(pts, t)


# ------------------------- 三种聚类算法训练 -------------------------

@pytest.mark.parametrize("method", ["kmeans", "dbscan", "hierarchical"])
def test_clu_train_three_methods(method):
    _seed_history()
    o = _ready_clu()
    if method == "dbscan":
        o.set_hyper({"min_pts": 2, "eps": 0.35})
    o.set_settings({"method": method})
    assert o.method == method
    for _ in range(4):
        o.step()
    assert o.iteration == 4
    st = o.state()
    assert st["clusters"], f"{method} 应识别出工况簇"
    assert st["compactness"] >= 0
    assert sum(c["pct"] for c in st["clusters"]) == pytest.approx(100.0, abs=0.2)
    assert all(c["size"] > 0 and c["name"] for c in st["clusters"])


def test_clu_train_two_load_levels_separated():
    """高/低负荷两组读数应被聚成两簇，且高负荷簇代表负荷更高。"""
    _seed_history(high=95.0, low=15.0)
    o = _ready_clu()
    o.set_hyper({"k": 2})
    o.set_settings({"method": "kmeans"})
    for _ in range(4):
        o.step()
    clusters = o.state()["clusters"]
    assert len(clusters) == 2
    assert clusters[0]["load"] > clusters[1]["load"]  # 按代表负荷降序
    assert clusters[0]["name"] == "高负荷工况"
    assert clusters[1]["name"] == "低负荷工况"


def test_clu_feature_vars_filter():
    _seed_history()
    o = _ready_clu()
    o.set_settings({"feature_vars": ["dev_high"]})
    assert o.feature_vars == ["dev_high"]
    # 空列表 = 全部设备参与聚类
    o.set_settings({"feature_vars": []})
    assert o.feature_vars == []
    # 未知设备被过滤
    o.set_settings({"feature_vars": ["dev_high", "no_such_dev"]})
    assert o.feature_vars == ["dev_high"]
    st = o.state()
    assert {c["id"] for c in st["feature_candidates"]} == {"dev_high", "dev_low"}


def test_clu_no_data_keeps_running():
    """无传感器数据时 step 不抛错、iteration 正常递增、无簇结果。"""
    o = _ready_clu()
    for _ in range(2):
        o.step()
    assert o.iteration == 2
    assert o.state()["clusters"] == []


def test_clu_state_contains_meta():
    _seed_history()
    o = _ready_clu()
    o.set_settings({"feature_vars": ["dev_low"]})
    for _ in range(2):
        o.step()
    st = o.state()
    assert st["feature_vars"] == ["dev_low"]
    assert st["method"] in ("kmeans", "dbscan", "hierarchical")
    assert "methods" in st and "feature_candidates" in st and "compactness" in st
