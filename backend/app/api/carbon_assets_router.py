# -*- coding: utf-8 -*-
"""碳资产管理 API：碳市场行情、市场快讯、报告生成任务、碳资产助手（报告 + 碳合规）。

业务域归属：碳资产（碳市场行情 / 排放配额 / CCER / 绿电绿证 / 合规报告）。
- /api/carbon-market/*、/api/market-news：碳市场实时行情与市场快讯（carbon_market / market_news）
- /api/report、/api/report/task、/api/reports、/api/report/{rid}：碳减排报告生成任务（后台线程 + 轮询）
- /api/carbon-assistant/*：碳资产助手（碳资产综合分析报告 + 控排履约策略，见 carbon_assistant.py）
- /report/{rid}：报告 HTML 分享页（share_router，无 /api 前缀，新标签页查看/打印）
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ..carbon_market import fetch_chart, fetch_quotes, forecast_series
from ..market_news import fetch_news
from ..models import ParsedOp, SimResult
from ..report import generate_report
from .. import report_store
from ..md_render import render_report_page
from .carbon_assistant import router as carbon_assistant_router

router = APIRouter(prefix="/api", tags=["carbon-assets"])
router.include_router(carbon_assistant_router)

# 报告分享页：无 /api 前缀（/report/{rid}），由 main.py 单独挂载
share_router = APIRouter(tags=["report-share"])


# ------------------------- 碳市场实时行情（CEA / CCER） -------------------------

@router.get("/carbon-market/quotes")
def carbon_market_quotes():
    """实时碳市场报价：CEA（上海环交所）+ CCER 最新成交、涨跌幅、月均价聚合。
    数据由 carbon_market 模块拉取并做 60s TTL 缓存；外网不可用时降级为模拟行情。"""
    return fetch_quotes()


@router.get("/carbon-market/chart")
def carbon_market_chart(instrument: str = "cea", kind: str = "daily"):
    """碳市场图表序列：cea → 日K线蜡烛数据，ccer → 成交均价折线数据。"""
    return fetch_chart(instrument, kind)


@router.get("/carbon-market/forecast")
def carbon_market_forecast(instrument: str = "cea", days: int = 10,
                           method: str = "linear"):
    """碳市场走势预测：外推未来 N 个交易日价格与置信区间。

    method: linear（线性回归）/ moving_average（移动平均）/ exponential（指数平滑）。"""
    return forecast_series(instrument, days, method=method)


@router.get("/market-news")
def market_news(page: int = 1):
    """市场快讯：爬取中国煤炭交易网「市场快讯」栏目（60s TTL 缓存）。

    外网不可用时返回 ok=False + 空列表，前端优雅降级隐藏滚动条。"""
    return fetch_news(page)


# ------------------------- 报告生成任务（后台线程 + 轮询进度） -------------------------

class ReportRequest(BaseModel):
    """导出报告请求：基线仿真结果 + 可选策略仿真结果与策略描述 + 生成参数配置。"""
    baseline: SimResult
    strategy: Optional[SimResult] = None
    strategy_name: str = ""
    strategy_text: str = ""
    ops: List[ParsedOp] = Field(default_factory=list)
    understood: List[str] = Field(default_factory=list)
    scenario: str = ""
    title: str = ""              # 自定义报告标题（空则自动拼接）
    engine: str = "auto"         # auto | llm | template
    depth: str = "standard"      # brief | standard | deep
    with_appendix: bool = True   # 是否包含「附录：全流程明细」


_REPORT_TASKS: Dict[str, Dict[str, Any]] = {}
_REPORT_TASKS_LOCK = threading.Lock()


def _task_update(tid: str, **kw: Any) -> None:
    with _REPORT_TASKS_LOCK:
        t = _REPORT_TASKS.get(tid)
        if t is not None:
            t.update(kw)


def _run_report_task(tid: str, req: "ReportRequest") -> None:
    """后台线程执行报告生成：按段回调进度，完成/失败后写入任务结果供前端轮询。"""
    try:
        def _p(pct: int, stage: str) -> None:
            _task_update(tid, progress=pct, stage=stage)

        out = generate_report(
            baseline=req.baseline,
            strategy=req.strategy,
            strategy_name=req.strategy_name,
            strategy_text=req.strategy_text,
            ops=req.ops,
            understood=req.understood,
            scenario=req.scenario,
            title=req.title,
            engine=req.engine,
            depth=req.depth,
            with_appendix=req.with_appendix,
            progress_cb=_p,
        )
        if not out.get("ok"):
            _task_update(tid, done=True, ok=False, progress=100, stage="done",
                         error=out.get("error") or "报告生成失败")
            return
        title_parts = [p for p in [req.strategy_name.strip(), req.scenario.strip()] if p]
        title = req.title.strip() or (" · ".join(title_parts) if title_parts else "碳减排分析报告")
        meta = report_store.save_report(
            markdown=out.get("markdown", ""),
            title=title,
            engine=out.get("engine", ""),
            strategy_name=req.strategy_name,
            scenario=req.scenario,
        )
        out["id"] = meta["id"]
        out["url"] = meta["url"]
        out["title"] = meta["title"]
        out["created_at"] = meta["created_at"]
        _task_update(tid, done=True, ok=True, progress=100, stage="done", result=out)
    except Exception as e:  # noqa: BLE001
        _task_update(tid, done=True, ok=False, progress=100, stage="done", error=str(e))


@router.post("/report")
def make_report(req: ReportRequest):
    """创建报告生成任务并立即返回 task_id；生成在后台线程执行，进度经 GET /api/report/task/{id} 轮询。"""
    tid = uuid.uuid4().hex[:12]
    with _REPORT_TASKS_LOCK:
        _REPORT_TASKS[tid] = {
            "id": tid, "done": False, "ok": None, "progress": 0,
            "stage": "queued", "error": None, "result": None,
            "created_at": time.time(),
        }
        # 简单清理：任务过多时移除已完成的最老任务
        if len(_REPORT_TASKS) > 200:
            for k in [k for k, t in list(_REPORT_TASKS.items()) if t.get("done")][:50]:
                _REPORT_TASKS.pop(k, None)
    threading.Thread(target=_run_report_task, args=(tid, req), daemon=True).start()
    return {"ok": True, "task_id": tid}


@router.get("/report/task/{tid}")
def report_task(tid: str):
    """轮询报告生成任务：{ok, done, progress, stage, error?, result?}。"""
    with _REPORT_TASKS_LOCK:
        t = _REPORT_TASKS.get(tid)
    if t is None:
        return {"ok": False, "done": True, "error": "任务不存在或已过期"}
    return {k: t.get(k) for k in ("id", "done", "ok", "progress", "stage", "error", "result")}


@router.get("/reports")
def list_reports(limit: int = 100, keyword: str = "", report_type: str = ""):
    """历史报告列表（按生成时间倒序）：id / title / created_at / engine / 策略名 / 场景。"""
    data = report_store.list_reports(
        limit=limit, keyword=keyword or None, report_type=report_type or None
    )
    return {"ok": True, **data}


@router.get("/report/{rid}")
def get_report(rid: str):
    """单个历史报告详情：元信息 + Markdown 原文。"""
    found = report_store.get_report(rid)
    if not found:
        return {"ok": False, "error": "报告不存在或已删除"}
    meta, markdown = found
    meta["ok"] = True
    meta["markdown"] = markdown
    return meta


@router.delete("/reports/{rid}")
def delete_report(rid: str):
    """删除一条历史报告。"""
    return {"ok": True, "deleted": report_store.delete_report(rid)}


# ------------------------- 报告分享页 -------------------------

@share_router.get("/report/{rid}", response_class=HTMLResponse)
def report_page(rid: str):
    """报告分享页：把历史报告的 Markdown 渲染为独立 HTML 页面（新标签页查看/打印）。"""
    found = report_store.get_report(rid)
    if not found:
        return HTMLResponse(
            "<!DOCTYPE html><html><head><meta charset='utf-8'/><title>报告不存在</title></head>"
            "<body style='font-family:sans-serif;text-align:center;padding:80px;color:#666'>"
            "<h2>报告不存在或已删除</h2><p><a href='/'>返回平台</a></p></body></html>",
            status_code=404,
        )
    meta, markdown = found
    return HTMLResponse(render_report_page(markdown, meta))
