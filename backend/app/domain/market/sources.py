"""碳市场行情数据源（适配器 + 降级组合策略）。

业务可替换点：CEA / CCER 行情数据从哪里获取。
- RemoteQuoteSource：    远程官方源（CNEEX / CCER），网络不可达或解析失败返回 None；
- SimulatedQuoteSource： 本地确定性模拟源（按分钟随机游走），保证离线演示数值持续变化；
- FallbackQuoteSource：  组合策略（远程优先，任一品种失败自动降级为模拟），默认 auto 模式。

新增数据源：实现 QuoteSource 接口（fetch_cea / fetch_ccer），
再在 create_quote_source() 中注册即可，业务组装逻辑无需改动。
"""
from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Dict, Optional


class QuoteSource(ABC):
    """行情源策略接口：分别提供 CEA / CCER 的行情包（失败返回 None）。"""

    name: str = ""

    @abstractmethod
    def fetch_cea(self) -> Optional[Dict[str, Any]]:
        """CEA 行情包（含 points/monthly/latest/intraday），失败返回 None。"""
        raise NotImplementedError

    @abstractmethod
    def fetch_ccer(self) -> Optional[Dict[str, Any]]:
        """CCER 最新报价包（含 latest），失败返回 None。"""
        raise NotImplementedError


class RemoteQuoteSource(QuoteSource):
    """远程官方行情源：通过注入的拉取回调访问外部站点（延迟导入避免循环依赖）。"""

    name = "remote"

    def __init__(self, fetchers: Optional[Dict[str, Any]] = None) -> None:
        self._fetchers = fetchers or {"cea": self._default_fetch_cea, "ccer": self._default_fetch_ccer}

    @staticmethod
    def _default_fetch_cea() -> Optional[Dict[str, Any]]:
        from ...carbon_market import fetch_cea_series  # 延迟导入，避免与碳市场服务循环依赖

        return fetch_cea_series()

    @staticmethod
    def _default_fetch_ccer() -> Optional[Dict[str, Any]]:
        from ...carbon_market import fetch_ccer_quote  # 延迟导入，避免与碳市场服务循环依赖

        return fetch_ccer_quote()

    def fetch_cea(self) -> Optional[Dict[str, Any]]:
        try:
            return self._fetchers["cea"]()
        except Exception:  # noqa: BLE001
            return None

    def fetch_ccer(self) -> Optional[Dict[str, Any]]:
        try:
            return self._fetchers["ccer"]()
        except Exception:  # noqa: BLE001
            return None


class SimulatedQuoteSource(QuoteSource):
    """本地确定性模拟源：基于时间种子随机游走，保证轮询时数值持续变化。"""

    name = "simulated"

    CEA_BASE = 93.5    # 模拟 CEA 基准价（元/吨），与历史降级行为保持一致
    CCER_BASE = 61.2   # 模拟 CCER 基准价（元/吨）

    def fetch_cea(self) -> Dict[str, Any]:
        points = self._sim_points(base=self.CEA_BASE, instrument="cea")
        return {
            "points": points,
            "latest": self._sim_quote(points),
            "intraday": self._intraday(points),
            "sources_tried": ["simulated"],
        }

    def fetch_ccer(self) -> Dict[str, Any]:
        points = self._sim_points(base=self.CCER_BASE, instrument="ccer", n=60)
        return {"points": points, "latest": self._sim_quote(points), "sources_tried": ["simulated"]}

    # ------------------------------------------------------------------ 内部

    @staticmethod
    def _sim_points(*, base: float, instrument: str, n: int = 120, start: date | None = None) -> list[dict[str, Any]]:
        """基于时间的确定性模拟序列：每分钟随机游走。"""
        seed = int(time.time() // 60)
        rng = random.Random(f"{instrument}-{seed}")
        start = start or date.today()
        drift = rng.uniform(-0.015, 0.015)
        out: list[dict[str, Any]] = []
        price = base
        for i in range(n):
            d = date.fromordinal(start.toordinal() - (n - 1 - i))
            o = price
            c = price * (1 + rng.gauss(0, 0.006))
            high = max(o, c) * (1 + abs(rng.gauss(0, 0.003)))
            low = min(o, c) * (1 - abs(rng.gauss(0, 0.003)))
            vol = int(rng.uniform(8000, 42000))
            out.append({
                "t": d.isoformat(),
                "open": round(o, 2), "close": round(c, 2),
                "high": round(high, 2), "low": round(low, 2),
                "price": round(c, 2), "volume": vol, "source": "simulated",
            })
            price = c * (1 + drift * rng.random())
        return out

    @staticmethod
    def _sim_quote(points: list[dict[str, Any]]) -> dict[str, Any]:
        latest = points[-1]
        prev = points[-2] if len(points) > 1 else latest
        pct = (latest["close"] - prev["close"]) / prev["close"] * 100 if prev["close"] else 0
        return {
            **latest,
            "t": date.today().isoformat(),
            "source": "simulated",
            "change_pct": round(pct, 2),
        }

    @staticmethod
    def _intraday(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """取最近 60 个点作为分时序列（与真实分时响应结构保持一致）。"""
        return points[-60:]


class FallbackQuoteSource(QuoteSource):
    """组合降级策略：远程优先，任一品种失败自动回退模拟源。"""

    name = "auto"

    def __init__(self, remote: Optional[QuoteSource] = None,
                 simulated: Optional[QuoteSource] = None) -> None:
        self._remote = remote or RemoteQuoteSource()
        self._simulated = simulated or SimulatedQuoteSource()
        self.cea_source = "remote"
        self.ccer_source = "remote"

    def fetch_cea(self) -> Dict[str, Any]:
        result = self._remote.fetch_cea()
        # 远程拉取失败时返回空结构（latest=None / points=[]），需按"无有效行情"降级
        if result and result.get("latest") and result.get("points"):
            self.cea_source = "remote"
            return result
        self.cea_source = "simulated"
        sim = self._simulated.fetch_cea()
        if isinstance(result, dict):
            tried = result.get("sources_tried") or []
            if tried:
                sim["sources_tried"] = list(tried) + list(sim.get("sources_tried") or [])
        return sim

    def fetch_ccer(self) -> Dict[str, Any]:
        result = self._remote.fetch_ccer()
        if result and result.get("latest"):
            self.ccer_source = "remote"
            return result
        self.ccer_source = "simulated"
        sim = self._simulated.fetch_ccer()
        if isinstance(result, dict):
            tried = result.get("sources_tried") or []
            if tried:
                sim["sources_tried"] = list(tried) + list(sim.get("sources_tried") or [])
        return sim


# ---------------------------------------------------------------------------
# 工厂：按模式创建行情源（新增数据源在此注册）
# ---------------------------------------------------------------------------


def create_quote_source(mode: str = "auto") -> QuoteSource:
    """创建行情数据源：'remote' 强制远程（无降级），'simulated' 强制模拟，其他为自动降级。"""
    mode = (mode or "auto").lower()
    if mode == "remote":
        return RemoteQuoteSource()
    if mode == "simulated":
        return SimulatedQuoteSource()
    return FallbackQuoteSource()
