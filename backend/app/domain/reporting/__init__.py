"""报告领域：分析段落生成策略。

对外导出：
- create_report_engine(mode)：按模式创建报告分析引擎（简单工厂）；
- ReportEngine 及三种实现：Template / Llm / Auto（LLM 优先、模板兜底）；
- _fmt(v, digits) / _pct(part, whole)：数值格式化工具（报告渲染与模板共用，
  由报告应用层（report.py）作为公共 API 使用）。
"""
from .engines import (
    AutoReportEngine,
    LlmReportEngine,
    ReportEngine,
    TemplateReportEngine,
    create_report_engine,
    _fmt,
    _pct,
)

__all__ = [
    "ReportEngine",
    "TemplateReportEngine",
    "LlmReportEngine",
    "AutoReportEngine",
    "create_report_engine",
    "_fmt",
    "_pct",
]
