# -*- coding: utf-8 -*-
"""碳资产报告数据模型。

当前项目使用内存/磁盘混合存储（见 report_store），本模块仅定义 Pydantic 校验模型，
与 pdf_trans 项目的 carbon_report 模型保持接口对齐，便于后续迁移到数据库。
"""
from typing import List, Optional
from pydantic import BaseModel, Field

# 支持的报告类型：碳交易简报 / 政策摘要 / 履约综合分析
REPORT_TYPES = ("market_brief", "policy_digest", "compliance_analysis")

# 支持的价格预测方法（与 carbon_market.forecast_series 对齐）
FORECAST_METHODS = ("linear", "moving_average", "exponential")


class CarbonReportCreate(BaseModel):
    """提交碳资产报告生成任务的请求体。"""
    title: str = Field(default="碳资产管理综合分析报告", min_length=1, max_length=200)
    period: str = Field(default="2026年度", min_length=1, max_length=100)
    report_type: str = Field(default="compliance_analysis", max_length=50)
    forecast_method: str = Field(default="linear", max_length=30)
    focus: List[str] = Field(default_factory=lambda: ["compliance", "trading"])
    extra: str = Field(default="", max_length=2000)
    # 履约综合分析专属：目标企业 + 履约年份（缺省时取 period 内年份）
    enterprise_id: str = Field(default="", max_length=64)
    compliance_year: Optional[int] = Field(default=None, ge=2021, le=2100)


class CarbonReportTask(BaseModel):
    """已提交的报告生成任务。"""
    task_id: str
    report_id: Optional[str] = None
    status: str = "pending"  # pending / running / completed / failed / cancelled
    title: str
    report_type: str = "compliance_analysis"
    progress: int = 0  # 0-100
    created_at: str
    message: str = ""


class CarbonReportOut(BaseModel):
    """返回给前端的报告元信息。"""
    id: str
    title: str
    created_at: str
    length: int
    url: str
    engine: str = ""
    strategy_name: str = ""
    scenario: str = ""
    report_type: str = "compliance_analysis"


class CarbonReportDetail(BaseModel):
    """单份报告的完整内容。"""
    id: str
    title: str
    created_at: str
    markdown: str
    length: int
    report_type: str = "compliance_analysis"
