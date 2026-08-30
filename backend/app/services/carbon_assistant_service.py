# -*- coding: utf-8 -*-
"""碳资产助手服务：报告任务编排。

提供 submit_report_task / get_task / cancel_report_task，
与 pdf_trans 项目同名模块保持接口对齐。

当前项目使用内存任务表 + 后台线程执行报告生成，结果持久化到 report_store。
报告生成调用碳合规完整流水线（参考版照搬）：台账核算 → 策略引擎 → 政策检索 → AI 撰写。

任务状态机：pending -> running -> completed | failed | cancelled
任务字段：task_id / report_id / status / title / report_type / progress / created_at / message
"""
import asyncio
import json
import threading
import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Dict, List, Optional

from .. import report_store
from .carbon_compliance.compliance_analysis_report import run_compliance_analysis_report

DEFAULT_USER_ID = "default"


_tasks: Dict[str, Dict] = {}
_cancel_events: Dict[str, threading.Event] = {}
_lock = threading.Lock()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def submit_report_task(title: str = "碳资产管理综合分析报告",
                       period: str = "2026年度",
                       focus: Optional[List[str]] = None,
                       extra: str = "",
                       report_type: str = "compliance_analysis",
                       forecast_method: str = "linear",
                       enterprise_id: str = "",
                       compliance_year: Optional[int] = None) -> Dict:
    """提交一份报告生成任务，立即返回任务对象并在后台线程运行。"""
    task_id = uuid.uuid4().hex[:12]
    task = {
        "task_id": task_id,
        "report_id": None,
        "status": "pending",
        "title": title,
        "report_type": report_type,
        "progress": 0,
        "created_at": _now(),
        "message": "任务已提交，等待执行",
    }
    with _lock:
        _tasks[task_id] = task
        _cancel_events[task_id] = threading.Event()

    thread = threading.Thread(
        target=_run_report_task,
        args=(task_id, title, period, focus or ["compliance", "trading"],
              extra, report_type, forecast_method, enterprise_id, compliance_year),
        daemon=True,
    )
    thread.start()
    return dict(task)


def cancel_report_task(task_id: str) -> bool:
    """取消一个尚未完成的报告任务；返回是否成功设置取消标记。"""
    with _lock:
        task = _tasks.get(task_id)
        if task is None:
            return False
        if task["status"] in ("completed", "failed", "cancelled"):
            return False
        event = _cancel_events.get(task_id)
    if event is not None:
        event.set()
    with _lock:
        task["status"] = "cancelled"
        task["progress"] = 100
        task["message"] = "任务已被用户取消"
    return True


def _run_report_task(task_id: str, title: str, period: str,
                     focus: List[str], extra: str,
                     report_type: str, forecast_method: str,
                     enterprise_id: str = "",
                     compliance_year: Optional[int] = None) -> None:
    """后台执行报告生成（参考版异步流水线）。"""
    with _lock:
        _tasks[task_id]["status"] = "running"
        _tasks[task_id]["progress"] = 5
        _tasks[task_id]["message"] = "正在启动报告生成…"

    def _on_progress(pct: int, msg: str) -> None:
        with _lock:
            task = _tasks.get(task_id)
            if task is not None and task["status"] == "running":
                task["progress"] = pct
                task["message"] = msg

    def _on_content(text: str) -> None:
        # 流式内容仅用于进度展示/预热，不在此落库
        pass

    def _check_cancelled() -> bool:
        event = _cancel_events.get(task_id)
        return bool(event and event.is_set())

    try:
        if _check_cancelled():
            return  # cancel_report_task 已将状态置为 cancelled

        # 解析履约年份：优先显式参数，其次从 period 中提取 4 位年份
        year = compliance_year
        if not year:
            import re
            m = re.search(r"(20\d{2})", period or "")
            year = int(m.group(1)) if m else datetime.now().year
        year = int(year or datetime.now().year)

        report_like = SimpleNamespace(
            user_id=DEFAULT_USER_ID,
            subject=title,
            target_year=year,
            ai_context=json.dumps({
                "enterprise_id": enterprise_id,
                "compliance_year": year,
                "forecast_method": forecast_method,
            }, ensure_ascii=False),
        )

        loop = asyncio.new_event_loop()
        try:
            md = loop.run_until_complete(
                run_compliance_analysis_report(
                    None,
                    report_like,
                    on_progress=_on_progress,
                    on_content=_on_content,
                )
            )
        finally:
            loop.close()

        if _check_cancelled():
            # 生成过程中被取消：清理可能已落库的报告，保持 cancelled 状态
            return
        meta = report_store.save_report(
            markdown=md,
            title=title,
            engine="carbon-assistant",
            report_type=report_type,
        )
        with _lock:
            task = _tasks.get(task_id)
            if task is not None:
                task.update({
                    "status": "completed",
                    "report_id": meta.get("id"),
                    "progress": 100,
                    "message": "报告生成完成",
                })
    except Exception as exc:
        event = _cancel_events.get(task_id)
        if event and event.is_set():
            return
        with _lock:
            task = _tasks.get(task_id)
            if task is not None:
                task.update({
                    "status": "failed",
                    "progress": 100,
                    "message": f"生成失败：{exc}",
                })


def get_task(task_id: str) -> Optional[Dict]:
    """获取任务状态。"""
    with _lock:
        return dict(_tasks.get(task_id, {})) if task_id in _tasks else None
