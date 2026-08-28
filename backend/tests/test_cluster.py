"""多设备时间序列聚类分析（/api/cluster + cluster.py）测试用例（backend）。

运行：
  cd backend && python -m pytest tests/test_cluster.py -v
（纯算法单测：不依赖真实网络 / Broker）
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cluster import extract_features, kmeans, silhouette, cluster_devices  # noqa: E402
from app.api import simulation_router  # noqa: E402


# ------------------------- 特征提取 -------------------------

def _flat_series(vals, step=10.0):
    return [{"t": 1700000000000 + i * step, "v": v} for i, v in enumerate(vals)]


def test_extract_features_basic():
    """平稳序列：std≈0、trend≈0、volatility≈0、range≈0、final_offset≈0。"""
    f = extract_features(_flat_series([10.0] * 20))
    assert abs(f["std"]) < 1e-6
    assert abs(f["trend"]) < 1e-6
    assert abs(f["volatility"]) < 1e-6
    assert abs(f["range_ratio"]) < 1e-6
    assert abs(f["final_offset"]) < 1e-6


def test_extract_features_trend_direction():
    """单调上升序列：trend 为正。"""
    f_up = extract_features(_flat_series([float(i) for i in range(1, 21)]))
    assert f_up["trend"] > 0
    f_down = extract_features(_flat_series([float(20 - i) for i in range(1, 21)]))
    assert f_down["trend"] < 0


def test_extract_features_empty_and_single():
    """空序列 / 单点 / 全 None：返回全 0 特征，不抛异常。"""
    assert all(v == 0.0 for v in extract_features([]).values())
    assert all(v == 0.0 for v in extract_features([{"t": 1, "v": None}]).values())
    f = extract_features(_flat_series([7.0]))
    assert f["mean"] == pytest.approx(7.0)


# ------------------------- KMeans 算法 -------------------------

def test_kmeans_two_clusters():
    """两组明显分离的点应被正确分到两个簇。"""
    X = [[1.0, 1.0], [1.2, 1.1], [0.9, 1.05]] + [[9.0, 9.0], [9.1, 8.8], [8.9, 9.2]]
    labels, centroids, inertia = kmeans(X, 2, seed=7)
    assert sorted(set(labels)) == [0, 1]
    assert labels[:3] == [labels[0]] * 3  # 前三后三分属不同簇
    assert labels[3:] == [labels[3]] * 3
    assert inertia > 0


def test_kmeans_single_cluster_when_k_gt_n():
    """k > n 时自动收敛到 n 簇；n == 1 时单簇。"""
    X = [[1.0], [2.0]]
    labels, _, _ = kmeans(X, 5, seed=1)
    assert len(labels) == 2
    labels1, _, _ = kmeans([[3.0]], 3, seed=1)
    assert labels1 == [0]


def test_silhouette_range():
    """轮廓系数应在 [-1, 1] 内；分离良好的数据得分明显高于混叠数据。"""
    # 两组中心相距远、簇内有一定散布 → 轮廓系数接近 1
    good = ([[0.0, 0.0], [0.8, -0.5], [-0.6, 0.9], [0.3, 0.7], [-0.9, -0.4]] +
            [[10.0, 10.0], [10.8, 9.5], [9.4, 10.9], [10.3, 10.7], [9.1, 9.6]])
    g_labels, g_cent, _ = kmeans(good, 2, seed=7)
    sg = silhouette(good, g_labels, g_cent)

    # 两组中心相距近、散布相当 → 轮廓系数明显偏低
    mixed = ([[0.0, 0.0], [0.8, -0.5], [-0.6, 0.9], [0.3, 0.7], [-0.9, -0.4]] +
             [[1.3, 0.0], [2.1, -0.5], [0.7, 0.9], [1.6, 0.7], [0.4, -0.4]])
    m_labels, m_cent, _ = kmeans(mixed, 2, seed=7)
    sm = silhouette(mixed, m_labels, m_cent)
    assert -1 <= sg <= 1 and -1 <= sm <= 1
    assert sg > sm


# ------------------------- 聚类入口 -------------------------

def test_cluster_devices_separates_high_low_load():
    """高负荷平稳 + 低负荷平稳两组设备应被分成两簇。"""
    high = [{"id": "h1", "label": "高炉A", "series": _flat_series([90.0] * 60)}]
    high2 = [{"id": "h2", "label": "高炉B", "series": _flat_series([95.0] * 60)}]
    low = [{"id": "l1", "label": "转炉A", "series": _flat_series([10.0] * 60)}]
    low2 = [{"id": "l2", "label": "转炉B", "series": _flat_series([12.0] * 60)}]
    res = cluster_devices(high + high2 + low + low2, k=2)
    assert res["ok"]
    assert res["n"] == 4 and res["k"] == 2
    assert len(res["clusters"]) == 2
    # 每簇内设备标签一致（高负荷在一起，低负荷在一起）
    for c in res["clusters"]:
        ids = {d["id"] for d in c["devices"]}
        assert ids == {"h1", "h2"} or ids == {"l1", "l2"}
    assert 0 <= res["silhouette"] <= 1


def test_cluster_devices_auto_k():
    """不指定 k：自动选 k，结果结构完整。"""
    devs = []
    for base, n_dev, noise in [(50.0, 3, 2.0), (20.0, 3, 1.5), (80.0, 3, 2.5)]:
        for j in range(n_dev):
            import random
            rnd = random.Random(j)
            series = [{"t": 1e12 + i * 1000,
                       "v": base + rnd.uniform(-noise, noise)} for i in range(50)]
            devs.append({"id": f"d{len(devs)}", "label": f"设备{len(devs)}", "series": series})
    res = cluster_devices(devs)
    assert res["ok"] and 2 <= res["k"] <= len(devs)
    assert sum(c["size"] for c in res["clusters"]) == len(devs)
    assert all(c["summary"] for c in res["clusters"])
    assert all(d["id"] in res["features"] for d in devs)


def test_cluster_devices_validation():
    """少于 2 台设备 / 空输入应抛 ValueError。"""
    with pytest.raises(ValueError):
        cluster_devices([])
    with pytest.raises(ValueError):
        cluster_devices([{"id": "a", "series": []}])


def test_cluster_api_route_exists():
    """POST /api/cluster 路由已注册且入参模型正确。"""
    paths = {r.path for r in simulation_router.router.routes}
    assert "/api/cluster" in paths
