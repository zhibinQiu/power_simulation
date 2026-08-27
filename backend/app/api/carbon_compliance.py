# -*- coding: utf-8 -*-
"""控排企业履约策略 REST（挂载于 carbon-assistant 前缀下）。

照搬自 pdf_trans 参考项目 backend/app/api/carbon_compliance.py，
适配本平台：无用户系统（DEFAULT_USER_ID）、无 SQLAlchemy（db 传 None）、
无 ApiResponse 包装（直接返回数据）。
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.services import carbon_compliance_service as ccs
from app.services.carbon_compliance.defaults import INDUSTRIES, INDUSTRY_LABELS, RISK_PROFILE_LABELS
from app.services.carbon_assistant_service import DEFAULT_USER_ID

router = APIRouter(tags=["carbon-compliance"])


# ---------------------------------------------------------------- schemas
class EnterpriseCreate(BaseModel):
    name: str = ""
    uscc: str = ""
    industry: str
    market_start_year: int
    compliance_cycle: str = "annual"
    risk_profile: str = "balanced"
    annual_budget_cap: float = 0
    single_trade_limit: float = 0
    enterprise_attrs: dict[str, Any] = Field(default_factory=dict)


class EnterpriseUpdate(BaseModel):
    name: str | None = None
    uscc: str | None = None
    industry: str | None = None
    market_start_year: int | None = None
    compliance_cycle: str | None = None
    risk_profile: str | None = None
    annual_budget_cap: float | None = None
    single_trade_limit: float | None = None
    enterprise_attrs: dict[str, Any] | None = None


class EmissionYearIn(BaseModel):
    year: int
    verified_total: float | None = None
    scope1_combustion: float = 0
    scope1_process: float = 0
    scope2_power: float = 0
    purchased_mwh: float = 0
    monthly_detail: dict[str, Any] = Field(default_factory=dict)
    historical_gap: float | None = None
    ccer_used: float = 0


class ForecastIn(BaseModel):
    year: int
    forecast_total: float = 0
    capacity_plan: str = ""
    abatement_projects: list[Any] = Field(default_factory=list)
    production_plan: str = ""


class CeaHoldingIn(BaseModel):
    vintage_year: int
    free_quota: float = 0
    carry_forward_qty: float = 0
    net_sell_qty: float = 0
    avg_cost: float = 0
    estimated_free_quota: float = 0
    sellable_cap: float | None = None


class TradeIn(BaseModel):
    side: str
    qty: float
    price: float = 0
    note: str = ""


class CcerHoldingIn(BaseModel):
    id: str | None = None
    project_type: str = ""
    issue_year: int
    expire_at: str | None = None
    qty: float = 0
    cost: float = 0
    eligible_qty: float | None = None
    linked_green_cert: bool = False


class GreenPowerIn(BaseModel):
    year: int
    market_green_mwh: float = 0
    self_gen_mwh: float = 0
    premium_per_mwh: float = 0
    contract_ref: str = ""


class GreenCertIn(BaseModel):
    id: str | None = None
    year: int
    qty: float = 0
    unit_price: float = 0
    retired: bool = False
    ren_weight_target: float | None = None


class MarketCeaIn(BaseModel):
    year_month: str
    avg_price: float
    high: float | None = None
    low: float | None = None
    period_tag: str = ""


class MarketCcerIn(BaseModel):
    year_month: str
    project_type: str = "general"
    avg_price: float


class MarketEnergyIn(BaseModel):
    year_month: str
    region: str = "national"
    green_premium: float | None = None
    grec_price: float | None = None
    coal_price: float | None = None


class StrategyRunIn(BaseModel):
    compliance_year: int


class SettingsUpdate(BaseModel):
    payload: dict[str, Any]


# ---------------------------------------------------------------- helpers
def _err(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------- meta & settings
@router.get("/meta")
def compliance_meta() -> dict:
    return {
        "industries": [{"value": k, "label": INDUSTRY_LABELS[k]} for k in INDUSTRIES],
        "risk_profiles": [{"value": k, "label": RISK_PROFILE_LABELS[k]} for k in RISK_PROFILE_LABELS],
    }


@router.get("/settings")
def get_settings() -> dict:
    return ccs.get_settings(None)


@router.put("/settings")
def put_settings(body: SettingsUpdate) -> dict:
    return ccs.update_settings(None, body.payload)


# ---------------------------------------------------------------- enterprises
@router.get("/enterprises")
def list_enterprises() -> list:
    rows = ccs.list_enterprises(None, DEFAULT_USER_ID)
    return [ccs.enterprise_to_dict(e) for e in rows]


@router.post("/enterprises")
def create_enterprise(body: EnterpriseCreate) -> dict:
    try:
        ent = ccs.create_enterprise(None, DEFAULT_USER_ID, body.model_dump())
    except ValueError as exc:
        raise _err(exc) from exc
    return ccs.enterprise_to_dict(ent)


@router.get("/enterprises/{enterprise_id}")
def get_enterprise(enterprise_id: str) -> dict:
    ent = ccs.get_enterprise(None, DEFAULT_USER_ID, enterprise_id)
    if not ent:
        raise HTTPException(status_code=404, detail="enterprise not found")
    return ccs.enterprise_to_dict(ent)


@router.put("/enterprises/{enterprise_id}")
def update_enterprise(enterprise_id: str, body: EnterpriseUpdate) -> dict:
    try:
        ent = ccs.update_enterprise(
            None, DEFAULT_USER_ID, enterprise_id, body.model_dump(exclude_unset=True)
        )
    except (LookupError, ValueError) as exc:
        raise _err(exc) from exc
    return ccs.enterprise_to_dict(ent)


@router.delete("/enterprises/{enterprise_id}")
def delete_enterprise(enterprise_id: str) -> dict:
    try:
        ccs.delete_enterprise(None, DEFAULT_USER_ID, enterprise_id)
    except LookupError as exc:
        raise _err(exc) from exc
    return {"ok": True}


# ---------------------------------------------------------------- emissions
@router.get("/enterprises/{enterprise_id}/emissions")
def list_emissions(enterprise_id: str) -> list:
    if not ccs.get_enterprise(None, DEFAULT_USER_ID, enterprise_id):
        raise HTTPException(status_code=404, detail="enterprise not found")
    rows = ccs.list_emission_years(None, enterprise_id)
    return [
        {
            "id": str(r.id),
            "year": r.year,
            "verified_total": r.verified_total,
            "scope1_combustion": r.scope1_combustion,
            "scope1_process": r.scope1_process,
            "scope2_power": r.scope2_power,
            "purchased_mwh": r.purchased_mwh,
            "monthly_detail": r.monthly_detail,
            "historical_gap": r.historical_gap,
            "ccer_used": r.ccer_used,
        }
        for r in rows
    ]


@router.post("/enterprises/{enterprise_id}/emissions")
def upsert_emission(enterprise_id: str, body: EmissionYearIn) -> dict:
    try:
        row = ccs.upsert_emission_year(None, DEFAULT_USER_ID, enterprise_id, body.model_dump())
    except LookupError as exc:
        raise _err(exc) from exc
    return {"id": str(row.id), "year": row.year}


@router.delete("/enterprises/{enterprise_id}/emissions/{year}")
def delete_emission(enterprise_id: str, year: int) -> dict:
    try:
        ccs.delete_emission_year(None, DEFAULT_USER_ID, enterprise_id, year)
    except LookupError as exc:
        raise _err(exc) from exc
    return {"ok": True, "year": year}


# ---------------------------------------------------------------- forecasts
@router.get("/enterprises/{enterprise_id}/forecasts")
def list_forecasts(enterprise_id: str) -> list:
    if not ccs.get_enterprise(None, DEFAULT_USER_ID, enterprise_id):
        raise HTTPException(status_code=404, detail="enterprise not found")
    rows = ccs.list_forecasts(None, enterprise_id)
    return [
        {
            "id": str(r.id),
            "year": r.year,
            "forecast_total": r.forecast_total,
            "capacity_plan": r.capacity_plan,
            "abatement_projects": r.abatement_projects,
            "production_plan": r.production_plan,
        }
        for r in rows
    ]


@router.post("/enterprises/{enterprise_id}/forecasts")
def upsert_forecast(enterprise_id: str, body: ForecastIn) -> dict:
    try:
        row = ccs.upsert_forecast(None, DEFAULT_USER_ID, enterprise_id, body.model_dump())
    except LookupError as exc:
        raise _err(exc) from exc
    return {"id": str(row.id), "year": row.year}


# ---------------------------------------------------------------- CEA
@router.get("/enterprises/{enterprise_id}/cea")
def list_cea(enterprise_id: str) -> list:
    if not ccs.get_enterprise(None, DEFAULT_USER_ID, enterprise_id):
        raise HTTPException(status_code=404, detail="enterprise not found")
    rows = ccs.list_cea_holdings(None, enterprise_id)
    return [
        {
            "id": str(r.id),
            "vintage_year": r.vintage_year,
            "free_quota": r.free_quota,
            "carry_forward_qty": r.carry_forward_qty,
            "net_sell_qty": r.net_sell_qty,
            "avg_cost": r.avg_cost,
            "estimated_free_quota": r.estimated_free_quota,
            "sellable_cap": r.sellable_cap,
        }
        for r in rows
    ]


@router.post("/enterprises/{enterprise_id}/cea")
def upsert_cea(enterprise_id: str, body: CeaHoldingIn) -> dict:
    try:
        row = ccs.upsert_cea_holding(None, DEFAULT_USER_ID, enterprise_id, body.model_dump())
    except LookupError as exc:
        raise _err(exc) from exc
    return {"id": str(row.id), "vintage_year": row.vintage_year}


@router.delete("/enterprises/{enterprise_id}/cea/{vintage_year}")
def delete_cea(enterprise_id: str, vintage_year: int) -> dict:
    try:
        ccs.delete_cea_holding(None, DEFAULT_USER_ID, enterprise_id, vintage_year)
    except LookupError as exc:
        raise _err(exc) from exc
    return {"ok": True, "vintage_year": vintage_year}


@router.post("/enterprises/{enterprise_id}/cea/trades")
def add_cea_trade(enterprise_id: str, body: TradeIn) -> dict:
    try:
        row = ccs.add_cea_trade(None, DEFAULT_USER_ID, enterprise_id, body.model_dump())
    except (LookupError, ValueError) as exc:
        raise _err(exc) from exc
    return {"id": str(row.id)}


# ---------------------------------------------------------------- CCER
@router.get("/enterprises/{enterprise_id}/ccer")
def list_ccer(enterprise_id: str) -> list:
    if not ccs.get_enterprise(None, DEFAULT_USER_ID, enterprise_id):
        raise HTTPException(status_code=404, detail="enterprise not found")
    rows = ccs.list_ccer_holdings(None, enterprise_id)
    return [
        {
            "id": str(r.id),
            "project_type": r.project_type,
            "issue_year": r.issue_year,
            "expire_at": (
                r.expire_at.isoformat()
                if hasattr(r.expire_at, "isoformat")
                else r.expire_at
            ),
            "qty": r.qty,
            "cost": r.cost,
            "eligible_qty": r.eligible_qty,
            "linked_green_cert": r.linked_green_cert,
        }
        for r in rows
    ]


@router.post("/enterprises/{enterprise_id}/ccer")
def upsert_ccer(enterprise_id: str, body: CcerHoldingIn) -> dict:
    try:
        row = ccs.upsert_ccer_holding(None, DEFAULT_USER_ID, enterprise_id, body.model_dump())
    except LookupError as exc:
        raise _err(exc) from exc
    return {"id": str(row.id)}


@router.delete("/enterprises/{enterprise_id}/ccer/{holding_id}")
def delete_ccer(enterprise_id: str, holding_id: str) -> dict:
    try:
        ccs.delete_ccer_holding(None, DEFAULT_USER_ID, enterprise_id, holding_id)
    except LookupError as exc:
        raise _err(exc) from exc
    return {"ok": True, "id": holding_id}


@router.post("/enterprises/{enterprise_id}/ccer/trades")
def add_ccer_trade(enterprise_id: str, body: TradeIn) -> dict:
    try:
        row = ccs.add_ccer_trade(None, DEFAULT_USER_ID, enterprise_id, body.model_dump())
    except (LookupError, ValueError) as exc:
        raise _err(exc) from exc
    return {"id": str(row.id)}


# ---------------------------------------------------------------- green power / certs
@router.get("/enterprises/{enterprise_id}/green-power")
def list_green_power(enterprise_id: str) -> list:
    if not ccs.get_enterprise(None, DEFAULT_USER_ID, enterprise_id):
        raise HTTPException(status_code=404, detail="enterprise not found")
    rows = ccs.list_green_power(None, enterprise_id)
    return [
        {
            "id": str(r.id),
            "year": r.year,
            "market_green_mwh": r.market_green_mwh,
            "self_gen_mwh": r.self_gen_mwh,
            "premium_per_mwh": r.premium_per_mwh,
            "contract_ref": r.contract_ref,
        }
        for r in rows
    ]


@router.post("/enterprises/{enterprise_id}/green-power")
def upsert_green_power(enterprise_id: str, body: GreenPowerIn) -> dict:
    try:
        row = ccs.upsert_green_power(None, DEFAULT_USER_ID, enterprise_id, body.model_dump())
    except LookupError as exc:
        raise _err(exc) from exc
    return {"id": str(row.id), "year": row.year}


@router.get("/enterprises/{enterprise_id}/green-certs")
def list_green_certs(enterprise_id: str) -> list:
    if not ccs.get_enterprise(None, DEFAULT_USER_ID, enterprise_id):
        raise HTTPException(status_code=404, detail="enterprise not found")
    rows = ccs.list_green_certs(None, enterprise_id)
    return [
        {
            "id": str(r.id),
            "year": r.year,
            "qty": r.qty,
            "unit_price": r.unit_price,
            "retired": r.retired,
            "ren_weight_target": r.ren_weight_target,
        }
        for r in rows
    ]


@router.post("/enterprises/{enterprise_id}/green-certs")
def upsert_green_cert(enterprise_id: str, body: GreenCertIn) -> dict:
    try:
        row = ccs.upsert_green_cert(None, DEFAULT_USER_ID, enterprise_id, body.model_dump())
    except LookupError as exc:
        raise _err(exc) from exc
    return {"id": str(row.id)}


# ---------------------------------------------------------------- market
@router.get("/market/cea")
def market_cea_list() -> list:
    rows = ccs.list_market_cea(None)
    return [
        {
            "id": str(r.id),
            "year_month": r.year_month,
            "avg_price": r.avg_price,
            "high": r.high,
            "low": r.low,
            "period_tag": r.period_tag,
        }
        for r in rows
    ]


@router.post("/market/cea")
def market_cea_upsert(body: MarketCeaIn) -> dict:
    row = ccs.upsert_market_cea(None, body.model_dump())
    return {"id": str(row.id), "year_month": row.year_month}


@router.get("/market/ccer")
def market_ccer_list() -> list:
    rows = ccs.list_market_ccer(None)
    return [
        {
            "id": str(r.id),
            "year_month": r.year_month,
            "project_type": r.project_type,
            "avg_price": r.avg_price,
        }
        for r in rows
    ]


@router.post("/market/ccer")
def market_ccer_upsert(body: MarketCcerIn) -> dict:
    row = ccs.upsert_market_ccer(None, body.model_dump())
    return {"id": str(row.id)}


@router.get("/market/energy")
def market_energy_list() -> list:
    rows = ccs.list_market_energy(None)
    return [
        {
            "id": str(r.id),
            "year_month": r.year_month,
            "region": r.region,
            "green_premium": r.green_premium,
            "grec_price": r.grec_price,
            "coal_price": r.coal_price,
        }
        for r in rows
    ]


@router.post("/market/energy")
def market_energy_upsert(body: MarketEnergyIn) -> dict:
    row = ccs.upsert_market_energy(None, body.model_dump())
    return {"id": str(row.id)}


@router.get("/market/cea/kline")
async def market_cea_kline(
    kind: str = Query("daily", description="daily|forecast"),
    method: str = Query("rule", description="forecast only: rule|ets|sarimax|prophet"),
) -> dict:
    """CEA 图表序列：日线 / 至年底日度预测。"""
    from app.services.carbon_compliance.market_sync import fetch_cea_chart_series

    return await fetch_cea_chart_series(kind, method=method)


@router.get("/market/ccer/kline")
async def market_ccer_kline(
    kind: str = Query("daily", description="daily|forecast"),
    method: str = Query("rule", description="forecast only: rule|ets|sarimax|prophet"),
) -> dict:
    """CCER 折线图：日线 / 至年底日度预测。"""
    from app.services.carbon_compliance.market_sync import fetch_ccer_chart_series

    return await fetch_ccer_chart_series(kind, method=method)


@router.get("/market/cea/forecast")
async def market_cea_forecast() -> dict:
    """CEA 从当前到年底的日度预测（策略用）。"""
    from app.services.carbon_compliance.market_sync import fetch_cea_forecast_to_year_end

    return await fetch_cea_forecast_to_year_end()


@router.post("/market/sync")
async def market_sync() -> dict:
    """从外站拉取 CEA/CCER 行情并写入月度库表。"""
    from app.services.carbon_compliance.market_sync import fetch_structured_quotes

    fetched = await fetch_structured_quotes()
    written: dict[str, Any] = {"cea": None, "ccer": None, "cea_months": 0}
    errors: list[str] = []

    monthly_rows = fetched.get("cea_monthly") or []
    if monthly_rows:
        try:
            latest_ym = monthly_rows[-1]["year_month"]
            for m in monthly_rows:
                is_latest = m["year_month"] == latest_ym
                avg_price = float(m["avg_price"])
                if is_latest:
                    avg_price = float(m.get("last_close") or avg_price)
                row = ccs.upsert_market_cea(
                    None,
                    {
                        "year_month": str(m["year_month"]),
                        "avg_price": avg_price,
                        "high": float(m["high"]),
                        "low": float(m["low"]),
                        "period_tag": str(m.get("period_tag") or ""),
                    },
                )
                written["cea"] = {"year_month": row.year_month, "avg_price": row.avg_price}
            written["cea_months"] = len(monthly_rows)
        except Exception as exc:
            errors.append(f"cea_monthly: {exc}")
    elif fetched.get("cea"):
        try:
            raw = fetched["cea"]
            ym = str(raw.get("year_month") or raw.get("trade_date") or "")[:7]
            if not ym:
                raise ValueError("no year_month")
            avg_price = float(raw.get("avg_price") or raw.get("close") or 0)
            row = ccs.upsert_market_cea(
                None,
                {
                    "year_month": ym,
                    "avg_price": avg_price,
                    "high": raw.get("high"),
                    "low": raw.get("low"),
                    "period_tag": "latest",
                },
            )
            written["cea"] = {
                "year_month": row.year_month,
                "avg_price": row.avg_price,
                "trade_date": raw.get("trade_date"),
                "source": raw.get("source"),
            }
            written["cea_months"] = 1
        except Exception as exc:
            errors.append(f"cea: {exc}")

    if fetched.get("ccer"):
        try:
            raw = fetched["ccer"]
            ym = str(raw.get("year_month") or raw.get("trade_date") or "")[:7]
            if not ym:
                raise ValueError("no year_month")
            row = ccs.upsert_market_ccer(
                None,
                {
                    "year_month": ym,
                    "project_type": "general",
                    "avg_price": float(raw.get("avg_price") or raw.get("close") or 0),
                },
            )
            written["ccer"] = {
                "year_month": row.year_month,
                "avg_price": row.avg_price,
                "trade_date": raw.get("trade_date"),
                "source": raw.get("source"),
            }
        except Exception as exc:
            errors.append(f"ccer: {exc}")

    return {
        "ok": not errors,
        "written": written,
        "errors": errors,
        "synced_at": fetched.get("synced_at"),
        "sources_tried": fetched.get("sources_tried") or [],
    }


# ---------------------------------------------------------------- strategy
@router.post("/enterprises/{enterprise_id}/strategy/run")
def run_strategy(enterprise_id: str, body: StrategyRunIn) -> dict:
    try:
        run = ccs.run_strategy(None, DEFAULT_USER_ID, enterprise_id, body.compliance_year)
    except LookupError as exc:
        raise _err(exc) from exc
    return ccs.run_to_dict(run)


@router.get("/enterprises/{enterprise_id}/strategy/runs")
def list_runs(enterprise_id: str) -> list:
    try:
        rows = ccs.list_strategy_runs(None, DEFAULT_USER_ID, enterprise_id)
    except LookupError as exc:
        raise _err(exc) from exc
    return [ccs.run_to_dict(r) for r in rows]


@router.get("/enterprises/{enterprise_id}/strategy/runs/{run_id}/download")
def download_run(enterprise_id: str, run_id: str):
    if not ccs.get_enterprise(None, DEFAULT_USER_ID, enterprise_id):
        raise HTTPException(status_code=404, detail="enterprise not found")
    run = None
    for r in ccs.list_strategy_runs(None, DEFAULT_USER_ID, enterprise_id):
        if str(r.id) == run_id:
            run = r
            break
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    md = getattr(run, "report_md", None)
    if not md:
        raise HTTPException(status_code=400, detail="report empty")
    return Response(
        content=md.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="strategy_{run.compliance_year}.md"'
        },
    )


# ---------------------------------------------------------------- alerts
@router.get("/alerts")
def list_alerts(
    enterprise_id: Optional[str] = Query(None),
    unacked_only: bool = Query(False),
) -> list:
    rows = ccs.list_alerts(
        None, DEFAULT_USER_ID, enterprise_id=enterprise_id, unacked_only=unacked_only
    )
    return [ccs.alert_to_dict(a) for a in rows]


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: str) -> dict:
    try:
        row = ccs.ack_alert(None, DEFAULT_USER_ID, alert_id)
    except LookupError as exc:
        raise _err(exc) from exc
    return ccs.alert_to_dict(row)


# ---------------------------------------------------------------- import
@router.get("/enterprises/{enterprise_id}/import/template")
def import_template(enterprise_id: str):
    if not ccs.get_enterprise(None, DEFAULT_USER_ID, enterprise_id):
        raise HTTPException(status_code=404, detail="enterprise not found")
    try:
        content = ccs.build_import_template_bytes()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="carbon_import_template.xlsx"'},
    )


@router.post("/enterprises/{enterprise_id}/import")
async def import_excel(enterprise_id: str, file: UploadFile = File(...)) -> dict:
    raw = await file.read()
    try:
        counts = ccs.import_enterprise_excel(None, DEFAULT_USER_ID, enterprise_id, raw)
    except (LookupError, RuntimeError, ValueError) as exc:
        raise _err(exc) from exc
    return counts
