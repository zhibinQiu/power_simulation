"""报告领域：分析段落生成策略。

对外导出：
- create_report_engine(mode)：按模式创建报告分析引擎（简单工厂）；
- ReportEngine 及三种实现：Template / Llm / Auto（LLM 优先、模板兜底）。
"""
from .engines import (
    AutoReportEngine,
    LlmReportEngine,
    ReportEngine,
    TemplateReportEngine,
    create_report_engine,
)

__all__ = [
    "ReportEngine",
    "TemplateReportEngine",
    "LlmReportEngine",
    "AutoReportEngine",
    "create_report_engine",
]
