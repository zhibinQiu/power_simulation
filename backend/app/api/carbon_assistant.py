# -*- coding: utf-8 -*-
"""碳资产助手 API：报告生成、任务管理、列表、详情、下载与 HTML 阅读页。

对应 pdf_trans 项目的 backend/app/api/carbon_assistant.py，路由挂载在
/api/carbon-assistant 前缀下。
"""
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse

from ..models.carbon_report import (
    FORECAST_METHODS,
    REPORT_TYPES,
    CarbonReportCreate,
    CarbonReportTask,
)
from ..services import carbon_assistant_service
from .. import report_store
from ..md_render import render_report_page
from .carbon_compliance import router as compliance_router

router = APIRouter(prefix="/carbon-assistant", tags=["carbon-assistant"])
router.include_router(compliance_router)


@router.post("/report", response_model=CarbonReportTask)
def create_report(payload: CarbonReportCreate):
    """提交碳资产报告生成任务。"""
    if payload.report_type not in REPORT_TYPES:
        raise HTTPException(status_code=422, detail=f"不支持的报告类型：{payload.report_type}")
    if payload.forecast_method not in FORECAST_METHODS:
        raise HTTPException(status_code=422, detail=f"不支持的预测方法：{payload.forecast_method}")
    task = carbon_assistant_service.submit_report_task(
        title=payload.title,
        period=payload.period,
        focus=payload.focus,
        extra=payload.extra,
        report_type=payload.report_type,
        forecast_method=payload.forecast_method,
        enterprise_id=payload.enterprise_id,
        compliance_year=payload.compliance_year,
    )
    return task


@router.get("/reports")
def list_reports(limit: int = Query(20, ge=1, le=100),
                 offset: int = Query(0, ge=0),
                 keyword: str = Query("", max_length=200),
                 report_type: str = Query("")):
    """获取已生成的碳资产报告列表，支持关键字/类型筛选与分页。"""
    data = report_store.list_reports(
        limit=limit,
        engine="carbon-assistant",
        keyword=keyword or None,
        report_type=report_type or None,
        offset=offset,
    )
    return {"total": data["total"], "reports": data["reports"]}


@router.get("/reports/{report_id}")
def get_report(report_id: str):
    """获取单份报告的 Markdown 正文。"""
    result = report_store.get_report(report_id)
    if not result:
        raise HTTPException(status_code=404, detail="报告不存在")
    meta, markdown = result
    return {
        "id": meta["id"],
        "title": meta["title"],
        "created_at": meta["created_at"],
        "markdown": markdown,
        "length": meta.get("length", 0),
        "report_type": meta.get("report_type", "compliance_analysis"),
    }


@router.get("/reports/{report_id}/view", response_class=HTMLResponse)
def view_report(report_id: str):
    """以 HTML 阅读页渲染报告正文（新窗口查看）。"""
    result = report_store.get_report(report_id)
    if not result:
        raise HTTPException(status_code=404, detail="报告不存在")
    meta, markdown = result
    page = render_report_page(markdown, meta)
    return HTMLResponse(content=page)


@router.get("/reports/{report_id}/download")
def download_report(report_id: str):
    """下载报告 Markdown 文件。"""
    result = report_store.get_report(report_id)
    if not result:
        raise HTTPException(status_code=404, detail="报告不存在")
    meta, markdown = result
    filename = f"{meta['title'] or '碳资产报告'}.md"
    encoded = quote(filename, safe='')
    return PlainTextResponse(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


@router.delete("/reports/{report_id}")
def delete_report(report_id: str):
    """删除指定报告。"""
    if not report_store.delete_report(report_id):
        raise HTTPException(status_code=404, detail="报告不存在或已删除")
    return {"ok": True, "id": report_id}


@router.get("/tasks/{task_id}")
def get_task(task_id: str):
    """查询报告生成任务状态（含进度）。"""
    task = carbon_assistant_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str):
    """取消一个尚未完成的报告生成任务。"""
    if not carbon_assistant_service.cancel_report_task(task_id):
        raise HTTPException(status_code=404, detail="任务不存在或已完成")
    return {"ok": True, "task_id": task_id}
