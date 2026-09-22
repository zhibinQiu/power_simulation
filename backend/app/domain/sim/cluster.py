"""多设备时间序列聚类分析（纯 Python 实现，无 sklearn 依赖）。

流程：
  1. 特征提取：对每台设备的时间序列计算 6 个形态特征（均值 / 变异系数 / 线性趋势 /
     波动剧烈度 / 相对极差 / 当前偏移），全部为相对量纲，天然可比；
  2. z-score 归一化（跨设备）后执行 KMeans（k-means++ 初始化 + Lloyd 迭代）；
  3. 轮廓系数（基于质心距离的近似）评估分群质量；
  4. 输出每簇设备清单、质心与中文摘要，供「工况数据分析 → 聚类分析」前端展示。

被 simulation_router 的 POST /api/cluster 调用；算法本身无框架依赖，可独立单测。
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Tuple

FEATURE_NAMES = ["mean", "std", "trend", "volatility", "range_ratio", "final_offset"]
FEATURE_LABELS = {
    "mean": "平均水平",
    "std": "波动幅度(变异系数)",
    "trend": "变化趋势(斜率)",
    "volatility": "波动剧烈度",
    "range_ratio": "相对极差",
    "final_offset": "当前偏移",
}

_EPS = 1e-9


# ------------------------- 特征提取 -------------------------

def extract_features(series: List[Dict[str, Any]]) -> Dict[str, float]:
    """从 [{t, v}, ...] 序列提取统计特征。

    所有特征均除以均值做无量纲化，使不同量纲设备（m³/h / kW / ℃）可以直接比较形态。
    """
    vals = [float(p["v"]) for p in (series or []) if p.get("v") is not None]
    if not vals:
        return {n: 0.0 for n in FEATURE_NAMES}

    n = len(vals)
    mean = sum(vals) / n
    denom = mean if abs(mean) > _EPS else _EPS

    # 标准差（变异系数）
    var = sum((v - mean) ** 2 for v in vals) / n
    std = math.sqrt(var) / denom

    # 线性趋势斜率（对均匀采样序列用索引回归），归一化为“每点相对变化率”
    trend = 0.0
    if n >= 2:
        mean_i = (n - 1) / 2.0
        cov = sum((i - mean_i) * (v - mean) for i, v in enumerate(vals))
        var_i = sum((i - mean_i) ** 2 for i in range(n)) / n
        slope = cov / var_i if var_i > 0 else 0.0
        trend = slope / denom

    # 波动剧烈度：一阶差分绝对均值（相对）
    volatility = 0.0
    if n >= 2:
        diffs = [abs(vals[i] - vals[i - 1]) for i in range(1, n)]
        volatility = (sum(diffs) / len(diffs)) / denom

    # 相对极差
    range_ratio = (max(vals) - min(vals)) / denom

    # 当前偏移：末值相对均值的偏差
    final_offset = (vals[-1] - mean) / denom

    return {
        "mean": mean,
        "std": std,
        "trend": trend,
        "volatility": volatility,
        "range_ratio": range_ratio,
        "final_offset": final_offset,
    }


# ------------------------- KMeans（纯 Python） -------------------------

def _dist(a: List[float], b: List[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def kmeans(X: List[List[float]], k: int, max_iter: int = 200,
           seed: int = 42) -> Tuple[List[int], List[List[float]], float]:
    """k-means++ 初始化 + Lloyd 迭代。返回 (labels, centroids, inertia)。"""
    n = len(X)
    if n == 0:
        return [], [], 0.0
    k = max(1, min(k, n))
    dim = len(X[0])
    rnd = random.Random(seed)

    # ---- k-means++ 初始化 ----
    centroids = [list(X[rnd.randrange(n)])]
    while len(centroids) < k:
        dists = [min(_dist(x, c) for c in centroids) ** 2 for x in X]
        total = sum(dists)
        if total <= _EPS:
            centroids.append(list(X[rnd.randrange(n)]))
        else:
            r = rnd.random() * total
            acc = 0.0
            chosen = n - 1
            for i, d in enumerate(dists):
                acc += d
                if acc >= r:
                    chosen = i
                    break
            centroids.append(list(X[chosen]))

    labels = [0] * n
    for _ in range(max_iter):
        # 指派
        changed = False
        for i, x in enumerate(X):
            best, best_d = 0, _dist(x, centroids[0]) ** 2
            for ci in range(1, k):
                d = sum((x[j] - centroids[ci][j]) ** 2 for j in range(dim))
                if d < best_d:
                    best_d, best = d, ci
            if labels[i] != best:
                labels[i], changed = best, True

        # 更新质心，处理空簇
        counts = [0] * k
        sums = [[0.0] * dim for _ in range(k)]
        for i, x in enumerate(X):
            c = labels[i]
            counts[c] += 1
            for j in range(dim):
                sums[c][j] += x[j]
        empty = False
        for ci in range(k):
            if counts[ci] == 0:
                # 空簇：质心放到“离现有质心最远”的点
                empty = True
                far, far_d = 0, -1.0
                for i, x in enumerate(X):
                    d = min(_dist(x, c) for c in centroids)
                    if d > far_d:
                        far_d, far = d, i
                centroids[ci] = list(X[far])
            else:
                for j in range(dim):
                    centroids[ci][j] = sums[ci][j] / counts[ci]
        if not changed and not empty:
            break

    inertia = sum(
        min(sum((x[j] - c[j]) ** 2 for j in range(dim)) for c in centroids) for x in X)
    return labels, centroids, inertia


def silhouette(X: List[List[float]], labels: List[int],
               centroids: List[List[float]]) -> float:
    """基于质心距离的轮廓系数近似（越大分群越清晰，-1~1）。"""
    n = len(X)
    if n < 2 or len(centroids) < 2:
        return 0.0
    total = 0.0
    for i, x in enumerate(X):
        c = labels[i]
        a = _dist(x, centroids[c])
        b = min(_dist(x, centroids[j]) for j in range(len(centroids)) if j != c)
        total += (b - a) / max(a, b, _EPS)
    return total / n


def _zscore(X: List[List[float]]) -> List[List[float]]:
    """逐特征 z-score 归一化（就地返回新矩阵）。"""
    if not X:
        return X
    dim = len(X[0])
    out = [list(r) for r in X]
    for j in range(dim):
        col = [r[j] for r in out]
        m = sum(col) / len(col)
        s = math.sqrt(sum((v - m) ** 2 for v in col) / len(col)) or 1.0
        for r in out:
            r[j] = (r[j] - m) / s
    return out


# ------------------------- 聚类入口 -------------------------

def _level(v: float, ref: float) -> str:
    if v > ref * 1.2:
        return "高"
    if v < ref * 0.8:
        return "低"
    return "中"


def _summarize(cluster_mean: Dict[str, float], ref_mean: Dict[str, float],
               labels: List[str]) -> str:
    """根据簇内特征均值生成一句话中文摘要（相对全体设备的参考水平）。"""
    desc: List[str] = []
    desc.append(f"平均负荷{_level(cluster_mean['mean'], ref_mean['mean'])}")
    desc.append(f"波动{_level(cluster_mean['volatility'], ref_mean['volatility'])}".replace("高中", "较大").replace("中", ""))
    trend = cluster_mean["trend"]
    if trend > 0.02:
        desc.append("整体呈上升趋势")
    elif trend < -0.02:
        desc.append("整体呈下降趋势")
    else:
        desc.append("整体平稳")
    dev = cluster_mean["final_offset"]
    if dev > 0.1:
        desc.append("当前偏高于均值")
    elif dev < -0.1:
        desc.append("当前偏低低于均值")
    return f"簇内 {len(labels)} 台设备：{'、'.join(labels[:4])}" + (" 等" if len(labels) > 4 else "") + f"（{('，'.join(desc))}）"


def cluster_devices(
    devices: List[Dict[str, Any]],
    k: Optional[int] = None,
) -> Dict[str, Any]:
    """对多台设备的时间序列做聚类分析。

    devices: [{id, label?, unit?, series: [{t, v}]}]
    返回：{n, k, method, silhouette, features, clusters, notes}
    """
    if not devices:
        raise ValueError("至少需要 1 台设备")
    n = len(devices)
    if n < 2:
        raise ValueError("聚类分析至少需要 2 台设备")

    feats_raw = [extract_features(d.get("series", [])) for d in devices]
    X = [[feats_raw[i][f] for f in FEATURE_NAMES] for i in range(n)]

    Z = _zscore(X)  # 归一化后统一在 z-score 空间聚类与评估

    if k is None or k < 1:
        # 自动选 k：2..min(5, n) 中轮廓系数最高者
        best_k, best_score, best = 2, -2.0, None
        for cand in range(2, min(5, n) + 1):
            labels, cents, _ = kmeans(Z, cand)
            score = silhouette(Z, labels, cents)
            if score > best_score:
                best_k, best_score, best = cand, score, (labels, cents)
        k = best_k
        labels, centroids = best
    else:
        k = max(1, min(k, n))
        labels, centroids, _ = kmeans(Z, k)

    sil = silhouette(Z, labels, centroids)

    features_out: Dict[str, Dict[str, float]] = {}
    for i, d in enumerate(devices):
        features_out[d["id"]] = {f: round(feats_raw[i][f], 4) for f in FEATURE_NAMES}

    ref_mean = {
        f: sum(feats_raw[i][f] for i in range(n)) / n for f in FEATURE_NAMES}

    clusters: List[Dict[str, Any]] = []
    for ci in range(k):
        members = [i for i in range(n) if labels[i] == ci]
        if not members:
            continue
        cm: Dict[str, float] = {}
        for f in FEATURE_NAMES:
            cm[f] = sum(feats_raw[i][f] for i in members) / len(members)
        devices_in = [{
            "id": devices[i]["id"],
            "label": devices[i].get("label") or devices[i]["id"],
            "unit": devices[i].get("unit", ""),
        } for i in members]
        clusters.append({
            "cluster": ci,
            "size": len(members),
            "devices": devices_in,
            "centroid": {f: round(cm[f], 4) for f in FEATURE_NAMES},
            "summary": _summarize(cm, ref_mean, [d["label"] for d in devices_in]),
        })
    clusters.sort(key=lambda c: -c["size"])

    return {
        "ok": True,
        "n": n,
        "k": len(clusters),
        "method": "kmeans (k-means++ + Lloyd)",
        "silhouette": round(sil, 4),
        "feature_names": FEATURE_NAMES,
        "feature_labels": FEATURE_LABELS,
        "features": features_out,
        "clusters": clusters,
        "notes": (
            "特征均为无量纲相对量（除以均值），跨设备可直接比较；"
            "silhouette 越大表示分群越清晰（>0.5 良好，0.25~0.5 一般，<0.25 不明显）。"
        ),
    }
