"""AI 优化模型「数据拟合分析」（optimizers.DataFitOptimizer，ai::fit）测试用例（backend）。

运行：
  cd backend && python -m pytest tests/test_fit_optimizer.py -v
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


def _seed_history():
    """注入 60 个点的抛物线读数（y = 0.01·(i-30)² + 50），时间戳落在最近 10 分钟窗口内。"""
    t = time.time()
    pts = []
    for i in range(60):
        v = 0.01 * (i - 30) ** 2 + 50
        pts.append({"t": t - 590 + i * 10, "v": round(v, 3)})
    DEVICE_HISTORY["dev_fit"] = pts
    DEVICE_META["dev_fit"] = {"label": "风机功耗", "unit": "kW", "unit_name": "电耗", "unit_type": "power"}


def _ready_fit():
    o = get_optimizer("ai::fit")
    o.setup(_MODEL, {})
    o.running = True
    return o


# ------------------------- 注册与基础状态 -------------------------

def test_fit_registered():
    o = OPTIMIZERS.get("ai::fit")
    assert o is not None
    assert o.kind == "fit"
    assert o.name == "数据拟合分析"
    assert sorted(o.hyperparams.keys()) == ["future", "order", "window"]
    assert [m["id"] for m in o.state()["methods"]] == ["poly", "exp", "log", "power"]


def test_fit_state_unready():
    """未 setup 时 state() 不抛错：method 默认 poly、fit 为空。"""
    o = get_optimizer("ai::fit")
    st = o.state()
    assert st["ready"] is False
    assert st["method"] == "poly"
    assert st["target"] == "load"
    assert st["fit"] is None
    assert st["curve"] == []
    assert st["best_r2"] == 0.0


def test_fit_setup_ready():
    _seed_history()
    o = _ready_fit()
    assert o.ready
    assert o.space, "流程模型应包含可优化参数"
    assert o.iteration == 0


# ------------------------- 多项式拟合（抛物线，R² 应接近 1） -------------------------

def test_fit_poly_parabola_r2():
    _seed_history()
    o = _ready_fit()
    o.set_hyper({"order": 2, "window": 60})
    o.set_settings({"target": "dev_fit"})
    assert o.target == "dev_fit"
    for _ in range(2):
        o.step()
    st = o.state()
    assert st["fit"], "应有拟合结果"
    assert st["fit"]["equation"], "应有拟合方程"
    assert st["fit"]["r2"] > 0.95, f"抛物线二次拟合 R² 应接近 1，实际 {st['fit']['r2']}"
    assert st["best_r2"] > 0.95
    assert len(st["curve"]) > 1
    # 曲线点包含实际值与拟合值
    assert all("y" in c and "yfit" in c for c in st["curve"])


def test_fit_set_settings_method_switch():
    _seed_history()
    o = _ready_fit()
    o.set_settings({"method": "exp"})
    assert o.method == "exp"
    o.set_settings({"method": "power"})
    assert o.method == "power"
    # 未知方法被忽略
    o.set_settings({"method": "no_such"})
    assert o.method == "power"
    # 未知目标被忽略
    o.set_settings({"target": "no_such_dev"})
    assert o.target == "load"


def test_fit_no_data_keeps_running():
    """无传感器数据时 step 不抛错、iteration 正常递增、无拟合结果。"""
    o = _ready_fit()
    for _ in range(2):
        o.step()
    assert o.iteration == 2
    assert o.state()["fit"] is None


def test_fit_state_contains_meta():
    _seed_history()
    o = _ready_fit()
    for _ in range(2):
        o.step()
    st = o.state()
    assert "methods" in st and "targets" in st and "fit" in st and "curve" in st
    assert st["targets"][0]["id"] == "load"
    assert any(t["id"] == "dev_fit" for t in st["targets"])
    assert st["method"] in ("poly", "exp", "log", "power")
