"""碳市场领域：行情数据源与价格预测策略。

对外导出：
- create_quote_source(mode)：行情数据源工厂（remote / simulated / auto 降级组合）；
- create_forecast_method(name)：预测算法工厂（linear / moving_average / exponential）。
"""
from .forecast import (
    ExponentialForecast,
    ForecastMethod,
    LinearForecast,
    MovingAverageForecast,
    create_forecast_method,
)
from .sources import (
    FallbackQuoteSource,
    QuoteSource,
    RemoteQuoteSource,
    SimulatedQuoteSource,
    create_quote_source,
)

__all__ = [
    "QuoteSource",
    "RemoteQuoteSource",
    "SimulatedQuoteSource",
    "FallbackQuoteSource",
    "create_quote_source",
    "ForecastMethod",
    "LinearForecast",
    "MovingAverageForecast",
    "ExponentialForecast",
    "create_forecast_method",
]
