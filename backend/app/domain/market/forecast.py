"""碳价走势预测算法（策略模式 + 注册表）。

业务可替换点：未来交易日价格如何外推。
- LinearForecast：       一元线性回归（最小二乘） + 残差置信带；
- MovingAverageForecast：最近 N 日移动平均水平外推；
- ExponentialForecast：  指数平滑 SES 水平外推（α=0.3）。

新增预测算法：继承 ForecastMethod 并实现 fit / predict / sigma，
再注册到 _REGISTRY 即可，调用方（forecast_series / API 层）无需改动。
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class ForecastMethod(ABC):
    """碳价外推策略的抽象基类。"""

    name: str = ""
    label: str = ""
    slope: float = 0.0

    @abstractmethod
    def fit(self, xs: List[float], ys: List[float]) -> None:
        """基于历史样本（x: 序号, y: 收盘价）拟合模型参数。"""
        raise NotImplementedError

    @abstractmethod
    def predict(self, step: int) -> float:
        """外推第 step 个未来交易日的中心价。"""
        raise NotImplementedError

    @abstractmethod
    def sigma(self, xs: List[float], ys: List[float]) -> float:
        """拟合残差/离散程度（用于置信带宽度）。"""
        raise NotImplementedError


class LinearForecast(ForecastMethod):
    """一元线性回归 y = a + b*x，置信带取残差标准差。

    predict(step) 以「最后样本的回归拟合值」为锚点外推，
    保证与其余水平外推策略的接口语义一致（都从历史尾部出发）。
    """

    name = "linear"
    label = "线性回归（最小二乘） + 残差置信带"

    def __init__(self) -> None:
        self._a = 0.0
        self._b = 0.0
        self._anchor = 0.0

    def fit(self, xs, ys) -> None:
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        sxx = sum((x - mx) ** 2 for x in xs)
        self._b = sxy / sxx if sxx else 0.0
        self._a = my - self._b * mx
        self.slope = self._b
        # 锚点：最后样本（xs=n-1）处的拟合值，外推以此为基准
        self._anchor = self._a + self._b * (n - 1)

    def predict(self, step: int) -> float:
        return self._anchor + self._b * step

    def sigma(self, xs, ys) -> float:
        resid = [y - (self._a + self._b * x) for x, y in zip(xs, ys)]
        return math.sqrt(sum(r * r for r in resid) / max(1, len(resid) - 2))


class _LevelForecast(ForecastMethod):
    """水平外推基类：移动平均 / 指数平滑共用离散度（整体标准差）。"""

    def __init__(self) -> None:
        self._level = 0.0

    def fit(self, xs, ys) -> None:
        self._level = self._compute_level(ys)

    @abstractmethod
    def _compute_level(self, ys: List[float]) -> float:
        raise NotImplementedError

    def predict(self, step: int) -> float:
        return self._level

    def sigma(self, xs, ys) -> float:
        mean = sum(ys) / len(ys)
        return math.sqrt(sum((y - mean) ** 2 for y in ys) / len(ys))


class MovingAverageForecast(_LevelForecast):
    """最近 N 日移动平均（窗口 ≤ 20）水平外推。"""

    name = "moving_average"

    def __init__(self, window: int = 20) -> None:
        super().__init__()
        self._window = window
        self.label = f"最近 {window} 个交易日移动平均（水平外推）"

    def _compute_level(self, ys) -> float:
        window = max(3, min(self._window, len(ys)))
        self.label = f"最近 {window} 个交易日移动平均（水平外推）"
        return sum(ys[-window:]) / window


class ExponentialForecast(_LevelForecast):
    """指数平滑 SES（α=0.3）水平外推。"""

    name = "exponential"
    label = "指数平滑 SES（水平外推，α=0.3）"

    def __init__(self, alpha: float = 0.3) -> None:
        super().__init__()
        self._alpha = alpha

    def _compute_level(self, ys) -> float:
        level = ys[0]
        for y in ys[1:]:
            level = self._alpha * y + (1 - self._alpha) * level
        return level


# ---------------------------------------------------------------------------
# 注册表 + 工厂（新增算法在此注册）
# ---------------------------------------------------------------------------

_REGISTRY: Dict[str, type] = {
    LinearForecast.name: LinearForecast,
    MovingAverageForecast.name: MovingAverageForecast,
    ExponentialForecast.name: ExponentialForecast,
}


def create_forecast_method(name: str = "linear", **kwargs: Any) -> ForecastMethod:
    """按名称创建预测算法；未知名称回退为线性回归。"""
    key = (name or "linear").strip().lower()
    cls = _REGISTRY.get(key, LinearForecast)
    return cls(**kwargs)
