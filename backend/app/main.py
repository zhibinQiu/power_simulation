"""FastAPI 主程序：REST 接口 + 静态托管前端。

实时遥测（WebSocket 推送 + 监测设备历史时序）已拆分到 realtime.py，由 register_realtime(app) 挂载，
本模块只负责 HTTP 路由与前端静态托管，保持精简、低耦合。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import presets
from .carbon_engine import cached_simulate, sim_cache_stats, default_factors
from .models import (ParseResult, ParseRequest, ParsedOp, ProcessModel, SimulateRequest,
                     SimulateResponse, SimResult, Strategy)
from .nl_parser import apply_ops, parse_strategy
from .llm_strategy import llm_parse, chat_completion
from .report import generate_report
from . import report_store
from .md_render import render_report_page
from .param_schema import TECHS_INFO, UNIT_TYPES_INFO
from .store import store
from . import platform_config
from . import realtime
from . import optimizers
from .carbon_engine import parameter_scan, conservation_audit

app = FastAPI(title="行业能碳仿真平台", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")


# ----------------------------- REST -----------------------------

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "steel-carbon-twin"}


@app.get("/api/cache/stats")
def cache_stats():
    """仿真缓存命中率（诊断用）：连续重复仿真（前端轮询/防抖后请求）应命中缓存。"""
    return sim_cache_stats()


@app.get("/api/model/preset", response_model=ProcessModel)
def get_preset():
    return presets.default_model()


@app.get("/api/presets/strategies")
def get_preset_strategies():
    return presets.preset_strategies()


@app.get("/api/factors")
def get_factors():
    """返回默认排放因子表（燃料 NCV/CC、电网因子、碳酸盐/电极因子），供前端配置面板初始化。"""
    return default_factors()


@app.post("/api/parse", response_model=ParseResult)
def parse(req: ParseRequest):
    units = [u.model_dump() for u in req.model.units] if req.model else None
    # 优先用大模型拆解；无 key / 超时 / 解析失败则回退确定性启发式
    res = llm_parse(req.text, units)
    if res is None:
        res = parse_strategy(req.text, units)
    return res


@app.get("/api/param-schema")
def get_param_schema():
    """返回工序参数分级元数据（config/optim、label、单位、参考范围），供前端编辑器渲染。
    返回前叠加「平台配置」中的参数运行空间覆盖。"""
    return {
        "schema": platform_config.apply_to_schema(),
        "unit_types": UNIT_TYPES_INFO,
        "techs": TECHS_INFO,
        "kinds": {
            "config": "给定约束/因变量：由工厂既定条件决定，提供参考范围，不在策略自动优化范围",
            "optim": "节能减排决策变量/自变量：会直接影响能耗与碳排的操作与配比杠杆",
        },
    }


@app.get("/api/devices")
def get_devices():
    """内置监测设备库：设备类型元数据 + 各工序设备规格（挂载方位/实测量/喂给引擎的输入）。
    返回前叠加「平台配置」中的设备量程覆盖。"""
    return platform_config.apply_to_devices()


# ------------------------- 平台可配置项 -------------------------

@app.get("/api/platform-config")
def get_platform_config():
    """返回平台可配置项：工艺规模档位、设备量程、参数运行空间（含默认值与档位预设）。"""
    return platform_config.config_payload()


@app.put("/api/platform-config")
def put_platform_config(cfg: dict = Body(...)):
    """保存平台可配置项覆盖（全量提交，未提供的字段回落默认）。"""
    platform_config.save_config(cfg)
    return {"ok": True}


@app.post("/api/platform-config/reset")
def reset_platform_config():
    """恢复平台可配置项出厂默认。"""
    platform_config.reset_config()
    return {"ok": True}


@app.post("/api/simulate", response_model=SimulateResponse)
def do_simulate(req: SimulateRequest):
    baseline = cached_simulate(req.model, req.factors)
    resp = SimulateResponse(baseline=baseline)
    if req.ops:
        applied = apply_ops(req.model, req.ops)
        strategy = cached_simulate(applied)
        resp.strategy = strategy
        b, s = baseline.totals, strategy.totals
        resp.delta = {
            "co2_total": round(s.co2_total - b.co2_total, 2),
            "co2_direct": round(s.co2_direct - b.co2_direct, 2),
            "co2_indirect": round(s.co2_indirect - b.co2_indirect, 2),
            "intensity": round(s.intensity - b.intensity, 1),
            "carbon_utilization": round(s.carbon_utilization - b.carbon_utilization, 4),
            "steel_output": round(s.steel_output - b.steel_output, 1),
            "co2_reduction_pct": round((1 - s.co2_total / b.co2_total) * 100, 1) if b.co2_total else 0.0,
        }
    return resp


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


# ------------------------- 报告生成任务（后台线程 + 轮询进度） -------------------------
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


@app.post("/api/report")
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


@app.get("/api/report/task/{tid}")
def report_task(tid: str):
    """轮询报告生成任务：{ok, done, progress, stage, error?, result?}。"""
    with _REPORT_TASKS_LOCK:
        t = _REPORT_TASKS.get(tid)
    if t is None:
        return {"ok": False, "done": True, "error": "任务不存在或已过期"}
    return {k: t.get(k) for k in ("id", "done", "ok", "progress", "stage", "error", "result")}


@app.get("/api/reports")
def list_reports(limit: int = 100):
    """历史报告列表（按生成时间倒序）：id / title / created_at / engine / 策略名 / 场景。"""
    return {"ok": True, "reports": report_store.list_reports(limit=limit)}


@app.get("/api/report/{rid}")
def get_report(rid: str):
    """单个历史报告详情：元信息 + Markdown 原文。"""
    found = report_store.get_report(rid)
    if not found:
        return {"ok": False, "error": "报告不存在或已删除"}
    meta, markdown = found
    meta["ok"] = True
    meta["markdown"] = markdown
    return meta


@app.delete("/api/reports/{rid}")
def delete_report(rid: str):
    """删除一条历史报告。"""
    return {"ok": True, "deleted": report_store.delete_report(rid)}


@app.get("/api/strategies", response_model=List[Strategy])
def list_strategies():
    return store.list()


@app.post("/api/strategies", response_model=Strategy)
def create_strategy(
    name: str = Body(..., description="策略名称"),
    description: str = Body("", description="策略描述"),
    raw_text: str = Body("", description="策略原文"),
    ops: List[ParsedOp] = Body(default_factory=list, description="策略操作列表"),
):
    """创建策略。前端以 JSON body 提交 {name, description, raw_text, ops}，故参数需显式声明为 Body。"""
    return store.create(name=name, description=description, raw_text=raw_text, ops=ops)


@app.get("/api/strategies/{sid}", response_model=Strategy)
def get_strategy(sid: str):
    return store.get(sid)


@app.put("/api/strategies/{sid}", response_model=Strategy)
def update_strategy(sid: str, name: Optional[str] = None, description: Optional[str] = None,
                    raw_text: Optional[str] = None, ops: Optional[str] = None):
    """更新策略的名称/描述/原文/操作（None 字段保持原值）。ops 为 JSON 数组字符串（如 ops=[{...}]），可为空。"""
    parsed_ops = None
    if ops is not None and ops.strip():
        try:
            parsed_ops = [ParsedOp.model_validate(o) for o in json.loads(ops)]
        except Exception:
            parsed_ops = None
    s = store.update(sid, name=name, description=description, raw_text=raw_text, ops=parsed_ops)
    if not s:
        raise HTTPException(status_code=404, detail="strategy not found")
    return s


@app.delete("/api/strategies/{sid}")
def delete_strategy(sid: str):
    return {"deleted": store.delete(sid)}


@app.post("/api/strategies/{sid}/apply")
def apply_strategy(sid: str, model: ProcessModel = Body(...),
                   factors: Optional[Dict[str, Any]] = Body(None)):
    """将已保存策略应用到当前流程。前端以 JSON body 提交 {model, factors}。"""
    s = store.get(sid)
    if not s:
        return {"error": "not found"}
    applied = apply_ops(model, s.ops)
    store.set_applied(sid, True)
    return {"model": applied, "sim": cached_simulate(applied, factors)}


@app.post("/api/apply")
def apply_parsed(model: ProcessModel = Body(...),
                 ops: List[ParsedOp] = Body(default_factory=list),
                 factors: Optional[Dict[str, Any]] = Body(None)):
    """直接对当前流程应用一组操作（无需先保存）。前端以 JSON body 提交 {model, ops, factors}。"""
    applied = apply_ops(model, ops)
    return {"model": applied, "sim": cached_simulate(applied, factors)}


# ------------------------- 求解 / 分析能力（参数扫描 + 守恒审计） -------------------------

class ScanRequest(BaseModel):
    """参数扫描（一维敏感性分析）：固定其余参数，扫描单工序某一参数，返回全厂指标随参数变化的曲线。"""
    model: ProcessModel
    unit_id: str
    param: str
    low: float
    high: float
    steps: int = 11
    factors: Optional[Dict[str, Any]] = None


@app.post("/api/scan")
def do_scan(req: ScanRequest):
    """单工序参数扫描：返回 { unit_name, param, points:[{value, co2_total, intensity, ...}] }。"""
    try:
        return parameter_scan(req.model, req.factors, req.unit_id, req.param, req.low, req.high, req.steps)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/audit")
def do_audit(model: ProcessModel = Body(...)):
    """碳元素守恒审计：逐工序核对碳输入与各去向（排CO₂/固钢/入渣/捕集/产品携出），返回闭合余量。"""
    return conservation_audit(model, None)


# ------------------------- 命令行窗口：自然语言聊天（复用已配置的 LLM） -------------------------
class ChatRequest(BaseModel):
    text: str
    history: List = []          # [[role, content], ...]
    mode: str = "chat"          # chat | code | plan


# 各模式系统提示词（与前端 CMD_MODES 保持一致）
CHAT_MODE_PROMPTS = {
    "chat": "你是一个友好的中文聊天助手，轻松自然地陪用户闲聊，口语化、简洁。",
    "code": "你是一个资深程序员助手。优先给出可运行、带注释的代码，并解释关键思路；遇到报错帮助定位问题。",
    "plan": "你是一个项目规划助手。把用户诉求拆成有序、可执行的步骤，标注依赖与优先级，输出清单式计划。",
}


@app.post("/api/chat")
def chat(req: ChatRequest):
    """命令行窗口的自然语言对话端点。无 LLM key / 网络异常时返回 ok=False 与兜底提示。"""
    sys_prompt = CHAT_MODE_PROMPTS.get(req.mode, CHAT_MODE_PROMPTS["chat"])
    messages = [{"role": "system", "content": sys_prompt}]
    for pair in (req.history or [])[-12:]:
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            messages.append({"role": pair[0], "content": str(pair[1])})
    messages.append({"role": "user", "content": req.text})
    reply = chat_completion(messages)
    if reply is None:
        return {"ok": False, "mode": req.mode,
                "reply": "（模型未配置或未连通：请在后端设置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 后重启）"}
    return {"ok": True, "mode": req.mode, "reply": reply}


# ------------------------- AI 优化模型（GA / PSO / RL 在线训练） -------------------------
# 训练上下文同步：前端在流程模型变化/进入策略面板时调用；模型变更自动重建各优化器。
# 后台定时训练由 optimizers.TrainingScheduler 常驻线程驱动（无需前端轮询触发训练）。

@app.post("/api/optimizers/context")
def set_optimizer_context(model: ProcessModel = Body(...),
                          factors: Optional[Dict[str, Any]] = Body(None)):
    """同步 AI 优化训练上下文（当前流程模型 + 排放因子）。"""
    return optimizers.set_context(model, factors)


@app.get("/api/optimizers")
def list_optimizers():
    """AI 优化模型列表与训练状态（前端每数秒轮询，展示随实时数据逐渐变优）。"""
    return {"models": [o.state() for o in optimizers.all_optimizers()]}


@app.get("/api/optimizers/{oid}")
def get_optimizer(oid: str):
    o = optimizers.get_optimizer(oid)
    if o is None:
        raise HTTPException(404, "未知的优化模型")
    return o.state(full=True)


@app.post("/api/optimizers/{oid}/start")
def start_optimizer(oid: str):
    """开启自动训练：后台调度线程将随实时传感器数据定时迭代。"""
    o = optimizers.get_optimizer(oid)
    if o is None:
        raise HTTPException(404, "未知的优化模型")
    if not o.ready:
        raise HTTPException(400, "训练上下文未就绪：请先同步流程模型（/api/optimizers/context）")
    o.running = True
    o.next_train_at = time.time() + 1.0   # 开启后立即安排首次迭代
    o._log("自动训练已开启：后台定时训练，随实时传感器数据持续优化")
    return {"ok": True, **o.state()}


@app.post("/api/optimizers/{oid}/stop")
def stop_optimizer(oid: str):
    o = optimizers.get_optimizer(oid)
    if o is None:
        raise HTTPException(404, "未知的优化模型")
    o.running = False
    o._log("自动训练已暂停")
    return {"ok": True, **o.state()}


@app.post("/api/optimizers/{oid}/train")
def train_optimizer(oid: str, steps: int = Body(1, ge=1, le=50, embed=True)):
    """手动触发训练（steps 步），用于无自动调度时的即时迭代。"""
    o = optimizers.get_optimizer(oid)
    if o is None:
        raise HTTPException(404, "未知的优化模型")
    if not o.ready:
        raise HTTPException(400, "训练上下文未就绪")
    for _ in range(int(steps)):
        o.step()
    return {"ok": True, **o.state()}


@app.post("/api/optimizers/{oid}/reset")
def reset_optimizer(oid: str):
    o = optimizers.get_optimizer(oid)
    if o is None:
        raise HTTPException(404, "未知的优化模型")
    o.reset()
    return {"ok": True, **o.state()}


@app.put("/api/optimizers/{oid}/hyper")
def set_optimizer_hyper(oid: str, patch: Dict[str, float] = Body(...)):
    o = optimizers.get_optimizer(oid)
    if o is None:
        raise HTTPException(404, "未知的优化模型")
    o.set_hyper(patch)
    return {"ok": True, **o.state()}


@app.post("/api/optimizers/{oid}/apply")
def apply_optimizer(oid: str):
    """把「当前生效版本」的最优参数应用到流程（返回新模型 + 仿真结果）。"""
    o = optimizers.get_optimizer(oid)
    if o is None:
        raise HTTPException(404, "未知的优化模型")
    try:
        m2, sim = o.apply()
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return {"model": m2, "sim": sim, **o.state()}


@app.put("/api/optimizers/{oid}/settings")
def set_optimizer_settings(oid: str, patch: Dict[str, Any] = Body(...)):
    """更新控制与自训练设置：{auto_control?: bool, schedule?: {interval?, window?}}。"""
    o = optimizers.get_optimizer(oid)
    if o is None:
        raise HTTPException(404, "未知的优化模型")
    o.set_settings(patch)
    return {"ok": True, **o.state()}


@app.post("/api/optimizers/{oid}/archive")
def archive_optimizer(oid: str):
    """把当前最优参数保存为模型版本（仅优于当前版本才替换生效）。"""
    o = optimizers.get_optimizer(oid)
    if o is None:
        raise HTTPException(404, "未知的优化模型")
    try:
        r = o.archive(force=True)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "promoted": r["promoted"], "version": r["version"], **o.state()}


@app.post("/api/optimizers/{oid}/switch")
def switch_optimizer_version(oid: str, version_id: str = Body(..., embed=True)):
    """在历史模型版本间切换（旧版本保留，可随时切回）。"""
    o = optimizers.get_optimizer(oid)
    if o is None:
        raise HTTPException(404, "未知的优化模型")
    try:
        o.switch_version(version_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, **o.state()}


@app.post("/api/optimizers/{oid}/ack")
def ack_optimizer(oid: str):
    """确认提醒：清除手动调优提醒 / 自动控制待下发标记。"""
    o = optimizers.get_optimizer(oid)
    if o is None:
        raise HTTPException(404, "未知的优化模型")
    o.ack()
    return {"ok": True, **o.state()}


# ------------------------- 实时遥测（WebSocket + 设备历史） -------------------------
realtime.register_realtime(app)


# ------------------------- 报告分享页 -------------------------


@app.get("/report/{rid}", response_class=HTMLResponse)
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


# ------------------------- 静态托管前端 -------------------------
if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        # 若存在真实静态文件（模型/解码器等），直接返回，避免全部回退 index.html
        candidate = os.path.join(FRONTEND_DIST, full_path)
        if os.path.isfile(candidate):
            return FileResponse(candidate)
        index = os.path.join(FRONTEND_DIST, "index.html")
        if os.path.exists(index):
            return FileResponse(index)
        return {"detail": "frontend not built"}


# 启动时为默认流程预填设备历史，保证前端首屏即有趋势数据
try:
    realtime.seed_history(presets.default_model())
except Exception as _e:  # pragma: no cover
    print("seed history warn:", _e)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8010)
