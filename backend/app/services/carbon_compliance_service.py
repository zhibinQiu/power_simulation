"""控排企业履约策略：CRUD、配置、策略运行门面（JSON 文件存储版）。

函数签名与参考项目 pdf_trans 的 carbon_compliance_service.py 保持一致，
`db` 参数保留但接受 None（无 SQLAlchemy 会话），数据存储于
backend/data/carbon_compliance.json。
"""

from __future__ import annotations

import io
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from app.services.carbon_compliance.accounting import AccountingInput, compute_accounting
from app.services.carbon_compliance.alerts import build_alerts
from app.services.carbon_compliance.carry_forward import (
    POLICY_DEFAULT_BASE_QTY,
    compute_carry_forward,
    resolve_carry_policy,
)
from app.services.carbon_compliance.cea_rollforward import roll_cea_over_years
from app.services.carbon_compliance.compliance import eligible_ccer_qty
from app.services.carbon_compliance.defaults import (
    INDUSTRIES,
    INDUSTRY_LABELS,
    RISK_PROFILES,
    deep_merge,
    default_settings,
)
from app.services.carbon_compliance.emission_forecast import build_emission_forecast
from app.services.carbon_compliance.market_cycle import judge_market_cycle
from app.services.carbon_compliance.report_export import strategy_run_to_markdown
from app.services.carbon_compliance.strategy_engine import build_strategy_payload
from ..core.config import DATA_DIR
from ..core.storage import read_json_file, write_json_atomic

try:
    from openpyxl import Workbook, load_workbook
except ImportError:  # pragma: no cover
    Workbook = None  # type: ignore
    load_workbook = None  # type: ignore

try:  # 模板表头样式：openpyxl 缺失时整体降级为纯文本表格，不影响导入
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
except ImportError:  # pragma: no cover
    Alignment = Font = PatternFill = None  # type: ignore
    get_column_letter = None  # type: ignore

# 数据目录允许用环境变量覆盖（联调 / 回归时指向临时副本），
# 避免为了验证「保存」这类写操作而碰到真实台账
_DATA_DIR = os.environ.get("CARBON_COMPLIANCE_DATA_DIR") or DATA_DIR
_DATA_PATH = os.path.join(_DATA_DIR, "carbon_compliance.json")

# 平台无用户系统，固定默认用户
DEFAULT_USER_ID = "default"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _norm_trade_at(v: Any) -> str:
    """交易登记时间：允许前端补录历史交易（datetime-local 形如 2026-10-26T14:39），
    缺省取当前时间。补秒是为了让同一字段格式统一 —— 流水列表按字符串倒序排。"""
    s = str(v or "").strip()
    if not s:
        return _now_iso()
    if len(s) == 16 and "T" in s:
        s = s + ":00"
    return s


def _empty_store() -> dict:
    return {
        "settings": {},
        "enterprises": [],
        "market_cea": [],
        "market_ccer": [],
        "market_energy": [],
    }


def _load_store() -> dict:
    if not os.path.exists(_DATA_PATH):
        store = _empty_store()
        _save_store(store)
        return store
    data = read_json_file(_DATA_PATH, None) or _empty_store()
    return {
        "settings": data.get("settings") or {},
        "enterprises": data.get("enterprises") or [],
        "market_cea": data.get("market_cea") or [],
        "market_ccer": data.get("market_ccer") or [],
        "market_energy": data.get("market_energy") or [],
    }


def _save_store(store: dict) -> None:
    write_json_atomic(_DATA_PATH, store)


class _Row(dict):
    """支持属性访问的 dict（兼容流水线 ORM 属性访问方式）。

    缺失键返回 None（对齐参考版 ORM 列默认值语义，避免属性访问抛错）。
    """

    def __getattr__(self, key: str):
        return self.get(key)


def _uuid() -> str:
    return str(uuid.uuid4())


def _find_enterprise(store: dict, enterprise_id: str) -> dict | None:
    for e in store.get("enterprises") or []:
        if str(e.get("id")) == str(enterprise_id):
            return e
    return None


def get_settings(db: Any = None) -> dict:
    store = _load_store()
    return deep_merge(default_settings(), store.get("settings") or {})


def update_settings(db: Any = None, payload: dict | None = None) -> dict:
    store = _load_store()
    merged = deep_merge(default_settings(), deep_merge(store.get("settings") or {}, payload or {}))
    store["settings"] = merged
    _save_store(store)
    return deep_merge(default_settings(), store["settings"])


def list_enterprises(db: Any = None, user_id: str = DEFAULT_USER_ID) -> list:
    store = _load_store()
    rows = [e for e in store.get("enterprises") or [] if str(e.get("user_id")) == str(user_id)]
    rows.sort(key=lambda e: e.get("updated_at") or "", reverse=True)
    return [_Row(e) for e in rows]


def get_enterprise(
    db: Any = None, user_id: str = DEFAULT_USER_ID, enterprise_id: str = ""
) -> _Row | None:
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    if not ent or str(ent.get("user_id")) != str(user_id):
        return None
    return _Row(ent)


def create_enterprise(db: Any = None, user_id: str = DEFAULT_USER_ID, data: dict | None = None) -> _Row:
    data = data or {}
    industry = data.get("industry") or ""
    if industry not in INDUSTRIES:
        raise ValueError(f"industry must be one of {INDUSTRIES}")
    risk = data.get("risk_profile") or "balanced"
    if risk not in RISK_PROFILES:
        raise ValueError(f"risk_profile must be one of {RISK_PROFILES}")
    raw_name = str(data.get("name") or "").strip()
    if not raw_name:
        label = INDUSTRY_LABELS.get(industry, industry)
        uscc = str(data.get("uscc") or "").strip()
        raw_name = f"{label}履约主体" + (f"-{uscc[-6:]}" if uscc else "")
    now = _now_iso()
    ent = {
        "id": _uuid(),
        "user_id": str(user_id),
        "name": raw_name,
        "uscc": str(data.get("uscc") or "").strip(),
        "industry": industry,
        "market_start_year": int(data["market_start_year"]),
        "compliance_cycle": str(data.get("compliance_cycle") or "annual"),
        "risk_profile": risk,
        "annual_budget_cap": float(data.get("annual_budget_cap") or 0),
        "single_trade_limit": float(data.get("single_trade_limit") or 0),
        "enterprise_attrs": dict(data.get("enterprise_attrs") or {}),
        "created_at": now,
        "updated_at": now,
        "emissions": [],
        "forecasts": [],
        "cea_holdings": [],
        "cea_trades": [],
        "ccer_holdings": [],
        "ccer_trades": [],
        "green_power": [],
        "green_certs": [],
        "strategy_runs": [],
        "alerts": [],
    }
    store = _load_store()
    store["enterprises"].append(ent)
    _save_store(store)
    return _Row(ent)


def update_enterprise(
    db: Any = None, user_id: str = DEFAULT_USER_ID, enterprise_id: str = "", data: dict | None = None
) -> _Row:
    data = data or {}
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    if not ent or str(ent.get("user_id")) != str(user_id):
        raise LookupError("enterprise not found")
    if "name" in data and data["name"] is not None:
        ent["name"] = str(data["name"]).strip()
    if "uscc" in data:
        ent["uscc"] = str(data.get("uscc") or "").strip()
    if "industry" in data and data["industry"] is not None:
        if data["industry"] not in INDUSTRIES:
            raise ValueError(f"industry must be one of {INDUSTRIES}")
        ent["industry"] = data["industry"]
    if "market_start_year" in data and data["market_start_year"] is not None:
        ent["market_start_year"] = int(data["market_start_year"])
    if "compliance_cycle" in data and data["compliance_cycle"] is not None:
        ent["compliance_cycle"] = str(data["compliance_cycle"])
    if "risk_profile" in data and data["risk_profile"] is not None:
        if data["risk_profile"] not in RISK_PROFILES:
            raise ValueError(f"risk_profile must be one of {RISK_PROFILES}")
        ent["risk_profile"] = data["risk_profile"]
    if "annual_budget_cap" in data and data["annual_budget_cap"] is not None:
        ent["annual_budget_cap"] = float(data["annual_budget_cap"])
    if "single_trade_limit" in data and data["single_trade_limit"] is not None:
        ent["single_trade_limit"] = float(data["single_trade_limit"])
    if "enterprise_attrs" in data and data["enterprise_attrs"] is not None:
        ent["enterprise_attrs"] = dict(data["enterprise_attrs"])
    ent["updated_at"] = _now_iso()
    _save_store(store)
    return _Row(ent)


def delete_enterprise(db: Any = None, user_id: str = DEFAULT_USER_ID, enterprise_id: str = "") -> None:
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    if not ent or str(ent.get("user_id")) != str(user_id):
        raise LookupError("enterprise not found")
    store["enterprises"] = [e for e in store["enterprises"] if str(e.get("id")) != str(enterprise_id)]
    _save_store(store)


# 排放台账的月度指标：月度上报与年度合计共用同一组字段，
# 保证「12 个月加起来」与「年度值」是同一口径，核算引擎不需要区分来源
EMISSION_METRICS: tuple[str, ...] = (
    "verified_total",
    "scope1_combustion",
    "scope1_process",
    "scope2_power",
    "purchased_mwh",
    "ccer_used",
)


def _normalize_months(raw: Any) -> dict[int, dict[str, float]]:
    """把 monthly_detail 收敛成 {1..12: {指标: 数值}}，脏键、空值、非数字一律丢弃。

    外部传入的月份键可能是 "1"、"01"、1 三种写法，历史脏数据里还可能出现 13 月，
    统一在这里过滤，避免下面每次求和都要重复判空。
    """
    out: dict[int, dict[str, float]] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        try:
            m = int(str(k).strip())
        except (TypeError, ValueError):
            continue
        if m < 1 or m > 12 or not isinstance(v, dict):
            continue
        cell: dict[str, float] = {}
        for f in EMISSION_METRICS:
            val = v.get(f)
            if val is None or val == "":
                continue
            try:
                cell[f] = float(val)
            except (TypeError, ValueError):
                continue
        if cell:
            out[m] = cell
    return out


def _forecast_ledger_drift(forecast_row: dict, emission_row: dict) -> str | None:
    """预测是「某一时点的快照」：里面的台账月与当前台账对不上时，提示重新测算。

    只比较来源标为 ledger 的月份——推算月和人工月本来就不会跟台账一致。
    """
    detail = _normalize_months(forecast_row.get("monthly_detail"))
    source = _normalize_forecast_source(forecast_row.get("monthly_source"))
    if not detail or not source:
        return None
    ledger_now: dict[int, float] = {}
    for m, cell in _normalize_months(emission_row.get("monthly_detail")).items():
        if "verified_total" in cell:
            ledger_now[m] = float(cell["verified_total"])
    drift: list[int] = []
    for m, src in source.items():
        if src != "ledger":
            continue
        now = ledger_now.get(m)
        old = (detail.get(m) or {}).get("verified_total")
        if now is None or old is None:
            continue
        if abs(float(old) - now) > 0.01:
            drift.append(m)
    if not drift:
        return None
    months_txt = "、".join(f"{m}月" for m in sorted(drift))
    return (
        "存档预测与当前台账已不一致（"
        + months_txt
        + "的排放值发生变化），本次仍按预测值核算；建议重新测算预测后再运行策略。"
    )


def _sum_months(months: dict[int, dict[str, float]]) -> dict[str, float]:
    """12 个月合计。某指标只要有任一月份填过就参与合计，全年都没填则不出现。"""
    total: dict[str, float] = {}
    for cell in months.values():
        for f, val in cell.items():
            total[f] = total.get(f, 0.0) + val
    return total


def _recompute_emission_year(row: dict, *, clear_when_empty: bool = False) -> None:
    """按月度合计刷新年度字段，人工核定值优先。

    优先级：annual_override > 12 个月合计 > 原有手填值。
    最后一档是为历史数据准备的——它们没有月度明细，不能被汇总逻辑清零。
    `clear_when_empty` 用于「删掉最后一个月」：此时应回到 0，而不是留着上次的合计。
    """
    months = _normalize_months(row.get("monthly_detail"))
    total = _sum_months(months)
    # 月度填满一整年后，历史冻结自动让位：此时月度数据已足够完整，
    # 再挂在老年度值上反而会让「12 个月填完了年度值却没动」变成困惑
    if row.get("override_legacy") and len(months) >= 12:
        row.pop("annual_override", None)
        row.pop("override_legacy", None)
    override = dict(row.get("annual_override") or {})
    for f in EMISSION_METRICS:
        if f in override:
            row[f] = override[f]
        elif f in total:
            row[f] = round(total[f], 6)
        elif clear_when_empty:
            row[f] = 0.0
    row["monthly_auto"] = {f: round(v, 6) for f, v in total.items()}
    row["monthly_filled"] = len(months)


def _emission_months_payload(months: dict[int, dict[str, float]]) -> dict[str, dict]:
    """落盘格式统一为「字符串月份 → 明细」，按月份升序，方便前端直接渲染。"""
    return {str(m): dict(cell) for m, cell in sorted(months.items())}


def _freeze_legacy_annual(row: dict) -> None:
    """首次录入月度前，把历史手填的年度值冻结成「核定值」。

    老台账只有年度数（如 2026 年 1500 万吨），一旦补录 1 月 100 万吨，
    按纯汇总口径年度值会立刻变成 100，核算缺口、策略、三份报告全部跟着反向。
    冻结之后年度值保持不变，前端显示「核定 1500 / 月度合计 100（1/12）」，
    用户自行决定是否点「改用月度合计」解除冻结。
    """
    if _normalize_months(row.get("monthly_detail")) or row.get("annual_override"):
        return
    frozen: dict[str, float] = {}
    for f in EMISSION_METRICS:
        val = row.get(f)
        if val is None:
            continue
        try:
            num = float(val)
        except (TypeError, ValueError):
            continue
        if abs(num) > 0:
            frozen[f] = num
    if frozen:
        row["annual_override"] = frozen
        # 打标记是为了区分「历史迁移来的冻结」与「用户主动核定」：
        # 前者在 12 个月填满后应自动让位给月度合计，后者不该被系统改掉
        row["override_legacy"] = True


def _find_emission_row(ent: dict, year: int) -> dict | None:
    for r in ent.get("emissions") or []:
        if int(r.get("year") or 0) == int(year):
            return r
    return None


def _upsert_emission_year(store: dict, enterprise_id: str, data: dict) -> _Row:
    ent = _find_enterprise(store, enterprise_id)
    year = int(data["year"])
    row = _find_emission_row(ent, year)
    if not row:
        row = {"id": _uuid(), "year": year}
        ent.setdefault("emissions", []).append(row)

    # 传空字典不清空：前端整年编辑时不一定带月份数据，
    # 无条件覆盖会把已录的月度明细抹掉（删月份请走专用接口）
    if data.get("monthly_detail"):
        row["monthly_detail"] = _emission_months_payload(
            _normalize_months(data["monthly_detail"])
        )

    months = _normalize_months(row.get("monthly_detail"))
    total = _sum_months(months)

    # 整年写入的值视为「核定值」；但与月度合计一致的不算覆盖，
    # 否则用户只是把合计回填一次，之后改月度年度值就再也不跟着变了
    clear = bool(data.get("clear_override"))
    override: dict[str, float] = {} if clear else dict(row.get("annual_override") or {})
    # 明确要求「改用月度合计」时，不能再用入参里的值重建覆盖：
    # EmissionYearIn 的 scope 字段默认 0，会一路把月度合计改回 0
    if not clear:
        for f in EMISSION_METRICS:
            if f not in data or data[f] is None:
                continue
            try:
                num = float(data[f])
            except (TypeError, ValueError):
                continue
            if f in total and abs(num - total[f]) < 1e-6:
                override.pop(f, None)
            else:
                override[f] = num
    if override:
        row["annual_override"] = override
        # 用户主动填了年度值，视为人工核定，不再是「历史迁移冻结」
        row.pop("override_legacy", None)
    else:
        row.pop("annual_override", None)
        row.pop("override_legacy", None)

    # 历史缺口与月度无关，单独处理
    if data.get("historical_gap") is not None:
        row["historical_gap"] = data["historical_gap"]

    _recompute_emission_year(row)
    return _Row(row)


def _apply_emission_month(
    store: dict, enterprise_id: str, year: int, month: int, values: dict
) -> dict:
    """把某月指标并进该年度明细并重算年度值（不落盘）。

    单独拎出来是为了让「界面单月上报」和「台账导入」走同一段逻辑：
    导入 12 个月与逐月手工填报必须得到完全一样的存储结构。
    """
    ent = _find_enterprise(store, enterprise_id)
    if ent is None:
        raise LookupError("enterprise not found")
    row = _find_emission_row(ent, int(year))
    if not row:
        row = {"id": _uuid(), "year": int(year)}
        ent.setdefault("emissions", []).append(row)

    _freeze_legacy_annual(row)
    months = _normalize_months(row.get("monthly_detail"))
    cell = dict(months.get(month) or {})
    for f in EMISSION_METRICS:
        if values.get(f) is None:
            continue
        try:
            cell[f] = float(values[f])
        except (TypeError, ValueError):
            continue
    if not cell:
        raise ValueError("no metric provided")
    months[month] = cell
    row["monthly_detail"] = _emission_months_payload(months)
    _recompute_emission_year(row)
    return row


def upsert_emission_month(
    db: Any = None, user_id: str = DEFAULT_USER_ID, enterprise_id: str = "", data: dict | None = None
) -> _Row:
    """单月上报：写入该月明细后立即重算年度值。

    只覆盖本次传入的指标，未传的保留该月原值——月度填报常常分几次补，
    不能因为这次只填了排放量就把同月的范畴数据清空。
    """
    if not get_enterprise(db, user_id, enterprise_id):
        raise LookupError("enterprise not found")
    payload = data or {}
    year = int(payload.get("year") or 0)
    month = int(payload.get("month") or 0)
    if not year:
        raise ValueError("year is required")
    if month < 1 or month > 12:
        raise ValueError("month must be 1-12")
    store = _load_store()
    row = _apply_emission_month(store, enterprise_id, year, month, payload)
    _save_store(store)
    return _Row(row)


def delete_emission_month(
    db: Any = None, user_id: str = DEFAULT_USER_ID, enterprise_id: str = "", year: int = 0, month: int = 0
) -> None:
    """删除某月明细并重算年度值；删空了就回到 0，不留上次的合计。"""
    if not get_enterprise(db, user_id, enterprise_id):
        raise LookupError("enterprise not found")
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    row = _find_emission_row(ent, int(year))
    if not row:
        raise LookupError("emission year not found")
    months = _normalize_months(row.get("monthly_detail"))
    if int(month) not in months:
        raise LookupError("emission month not found")
    months.pop(int(month))
    row["monthly_detail"] = _emission_months_payload(months)
    _recompute_emission_year(row, clear_when_empty=not months)
    _save_store(store)


def list_emission_years(db: Any = None, enterprise_id: str = "") -> list:
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    if not ent:
        return []
    rows = sorted(ent.get("emissions") or [], key=lambda r: r.get("year"), reverse=True)
    return [_Row(r) for r in rows]


def _normalize_forecast_months(raw: Any) -> dict[int, float]:
    """预测的逐月值收敛成 {1..12: 万吨}。

    同时接受 {"3": 125.5} 与 {"3": {"value": 125.5, "source": "forecast"}}
    两种写法：前者是精简存档，后者是前端把测算结果原样回传，省一层转换。
    """
    out: dict[int, float] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        try:
            m = int(str(k).strip())
        except (TypeError, ValueError):
            continue
        if m < 1 or m > 12:
            continue
        if isinstance(v, dict):
            v = v.get("value")
        if v is None or v == "":
            continue
        try:
            out[m] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def _normalize_forecast_source(raw: Any) -> dict[int, str]:
    """每月的数据来源：ledger（台账实际）/ forecast（推算）/ manual（人工改过）。只保留合法值。"""
    out: dict[int, str] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        try:
            m = int(str(k).strip())
        except (TypeError, ValueError):
            continue
        if m < 1 or m > 12:
            continue
        s = str(v or "").strip().lower()
        if s in ("ledger", "forecast", "manual"):
            out[m] = s
    return out


def preview_emission_forecast(
    db: Any = None,
    user_id: str = DEFAULT_USER_ID,
    enterprise_id: str = "",
    year: int = 0,
    capacity_output: float | None = None,
    plan_months: dict | None = None,
) -> dict:
    """测算某一履约年度的 12 个月排放。

    两种口径，优先用生产计划：
    1. 传了 `capacity_output`（年计划产量）或 `plan_months`（月度排产）→
       按「计划产量 × 排放强度」逐月出数，强度优先取企业属性里的
       intensity_per_t_steel / intensity_per_t_product，缺省时用台账年度值 ÷ 计划产量反推；
    2. 没传计划 → 退回「台账已填月份均值 → 季节/趋势外推」。

    只读，不落盘。真正的存档发生在 upsert_forecast——预测是「某一时点的快照」，
    台账后续补录不会自动改写历史预测，需要重新测算才会更新。
    """
    ent = get_enterprise(db, user_id, enterprise_id)
    if not ent:
        raise LookupError("enterprise not found")
    year = int(year or 0)
    if not year:
        raise ValueError("year is required")

    target_months: dict[int, float] = {}
    target_annual: float | None = None
    history: list[dict] = []
    for r in list_emission_years(db, enterprise_id):
        ry = int(r.get("year") or 0)
        months: dict[int, float] = {}
        for m, cell in _normalize_months(r.get("monthly_detail")).items():
            if "verified_total" in cell:
                months[m] = cell["verified_total"]
        annual = r.get("verified_total")
        if ry == year:
            target_months = months
            target_annual = float(annual) if annual is not None else None
        else:
            history.append({"year": ry, "months": months, "annual": annual})

    attrs = ent.get("enterprise_attrs") or {}

    def _attr_num(*keys: str) -> float:
        for k in keys:
            try:
                v = float(attrs.get(k) or 0)
            except (TypeError, ValueError):
                continue
            if v > 0:
                return v
        return 0.0

    # 企业属性里现成的「设计产量 / 排放强度」，用来给前端预填、也给测算兜底
    attr_capacity = _attr_num("crude_steel_output", "design_capacity", "annual_output", "capacity_output")
    attr_intensity = _attr_num(
        "intensity_per_t_steel", "intensity_per_t_product", "emission_intensity", "intensity"
    )

    out = build_emission_forecast(
        year=year,
        target_months=target_months,
        history=history,
        target_annual=target_annual,
        plan_months=plan_months,
        capacity_output=capacity_output,
        intensity=attr_intensity or None,
    )
    out["enterprise_id"] = enterprise_id
    out["ledger_annual"] = target_annual
    # 前端据此预填「产能计划 / 生产计划」：企业属性没有时给 0，由用户自己填
    out["default_capacity_output"] = attr_capacity
    out["default_intensity"] = attr_intensity

    # 与台账年度值偏差过大时明说：两个数都不是错的，但需要人来决定用哪个
    if out["basis"] == "ledger_monthly" and target_annual:
        dev = (out["total"] - target_annual) / target_annual
        if abs(dev) >= 0.2:
            out["warnings"].append(
                "按已填月份外推得 {:.2f} 万吨，与台账年度值 {:.2f} 万吨相差 {:+.1%}，"
                "请确认年度值是否仍按原口径，或补录季度性波动较大的月份。".format(
                    out["total"], target_annual, dev
                )
            )
    return out



def upsert_emission_year(
    db: Any = None, user_id: str = DEFAULT_USER_ID, enterprise_id: str = "", data: dict | None = None
) -> _Row:
    if not get_enterprise(db, user_id, enterprise_id):
        raise LookupError("enterprise not found")
    store = _load_store()
    row = _upsert_emission_year(store, enterprise_id, data or {})
    _save_store(store)
    return row


def delete_emission_year(
    db: Any = None, user_id: str = DEFAULT_USER_ID, enterprise_id: str = "", year: int = 0
) -> None:
    if not get_enterprise(db, user_id, enterprise_id):
        raise LookupError("enterprise not found")
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    before = len(ent.get("emissions") or [])
    ent["emissions"] = [r for r in ent.get("emissions") or [] if int(r.get("year")) != int(year)]
    if len(ent.get("emissions")) == before:
        raise LookupError("emission year not found")
    _save_store(store)


def upsert_forecast(
    db: Any = None, user_id: str = DEFAULT_USER_ID, enterprise_id: str = "", data: dict | None = None
) -> _Row:
    if not get_enterprise(db, user_id, enterprise_id):
        raise LookupError("enterprise not found")
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    year = int(data["year"])
    row = None
    for r in ent.get("forecasts") or []:
        if int(r.get("year")) == year:
            row = r
            break
    if not row:
        row = {"id": _uuid(), "year": year}
        ent.setdefault("forecasts", []).append(row)
    # 逐月测算结果优先：传了月度明细，全年值就由 12 个月加总得出，
    # 否则「表里的合计」和「逐月明细」会出现两套对不上的口径
    months = _normalize_forecast_months(data.get("monthly_detail"))
    if months:
        row["monthly_detail"] = {str(m): round(v, 2) for m, v in sorted(months.items())}
        # 来源随月度值一起存档：台账后续补录后，历史预测的「哪几个月是实测」不应跟着变，
        # 否则同一份预测在不同时间打开会显示不同的构成
        src = _normalize_forecast_source(data.get("monthly_source"))
        row["monthly_source"] = {str(m): src[m] for m in sorted(months) if m in src}
        row["forecast_total"] = round(sum(months.values()), 2)
    else:
        # 无月度支撑（如未来年度台账为空）时退回手工填的全年值
        row["monthly_detail"] = {}
        row["monthly_source"] = {}
        row["forecast_total"] = float(data.get("forecast_total") or 0)
    row["basis"] = str(data.get("basis") or "")
    row["basis_text"] = str(data.get("basis_text") or "")
    row["capacity_plan"] = str(data.get("capacity_plan") or "")
    row["abatement_projects"] = list(data.get("abatement_projects") or [])
    row["production_plan"] = str(data.get("production_plan") or "")
    # ---- 生产计划口径：年计划产量（万吨）+ 逐月排产（万吨）----
    # 存档一份，编辑时原样回填；不存的话重新打开弹窗会退化成历史外推，
    # 用户改了半天的排产计划就白填了。
    cap = data.get("capacity_output")
    try:
        row["capacity_output"] = round(float(cap), 4) if cap not in (None, "") else 0.0
    except (TypeError, ValueError):
        row["capacity_output"] = 0.0
    plan: dict[str, float] = {}
    raw_plan = data.get("plan_months")
    if isinstance(raw_plan, dict):
        for k, v in raw_plan.items():
            try:
                m = int(str(k).strip())
            except (TypeError, ValueError):
                continue
            if m < 1 or m > 12 or v in (None, ""):
                continue
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if fv > 0:
                plan[str(m)] = round(fv, 2)
    row["plan_months"] = plan
    row["plan_intensity"] = data.get("plan_intensity") or 0
    row["updated_at"] = _now_iso()
    _save_store(store)
    return _Row(row)


def delete_forecast(
    db: Any = None, user_id: str = DEFAULT_USER_ID, enterprise_id: str = "", forecast_id: str = ""
) -> None:
    """按 id 删除排放预测记录。

    用 id 而不是年份：年份虽然在建档时判重，但老数据可能存在年份相同、id 不同的脏记录，
    按年份删会一次抹掉多行。
    """
    if not get_enterprise(db, user_id, enterprise_id):
        raise LookupError("enterprise not found")
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    before = len(ent.get("forecasts") or [])
    ent["forecasts"] = [r for r in ent.get("forecasts") or [] if str(r.get("id")) != str(forecast_id)]
    if len(ent.get("forecasts")) == before:
        raise LookupError("forecast not found")
    _save_store(store)


def list_forecasts(db: Any = None, enterprise_id: str = "") -> list:
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    if not ent:
        return []
    rows = sorted(ent.get("forecasts") or [], key=lambda r: r.get("year"), reverse=True)
    return [_Row(r) for r in rows]


def upsert_cea_holding(
    db: Any = None, user_id: str = DEFAULT_USER_ID, enterprise_id: str = "", data: dict | None = None
) -> _Row:
    if not get_enterprise(db, user_id, enterprise_id):
        raise LookupError("enterprise not found")
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    vy = int(data["vintage_year"])
    row = None
    for r in ent.get("cea_holdings") or []:
        if int(r.get("vintage_year")) == vy:
            row = r
            break
    if not row:
        row = {"id": _uuid(), "vintage_year": vy}
        ent.setdefault("cea_holdings", []).append(row)
    for field in (
        "free_quota",
        "carry_forward_qty",
        "net_sell_qty",
        "buy_qty",
        "avg_cost",
        "estimated_free_quota",
        "sellable_cap",
    ):
        if field in data:
            row[field] = data[field]
    # 兼容旧字段名
    if "carry_forward_qty" not in data and "expired_qty" in data:
        row["carry_forward_qty"] = float(data.get("expired_qty") or 0)
    _save_store(store)
    return _Row(row)


def list_cea_holdings(db: Any = None, enterprise_id: str = "") -> list:
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    if not ent:
        return []
    rows = sorted(ent.get("cea_holdings") or [], key=lambda r: r.get("vintage_year"), reverse=True)
    return [_Row(r) for r in rows]


def delete_cea_holding(
    db: Any = None, user_id: str = DEFAULT_USER_ID, enterprise_id: str = "", vintage_year: int = 0
) -> None:
    if not get_enterprise(db, user_id, enterprise_id):
        raise LookupError("enterprise not found")
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    before = len(ent.get("cea_holdings") or [])
    ent["cea_holdings"] = [
        r for r in ent.get("cea_holdings") or [] if int(r.get("vintage_year")) != int(vintage_year)
    ]
    if len(ent.get("cea_holdings")) == before:
        raise LookupError("cea holding not found")
    _save_store(store)


def get_cea_holding_for_year(
    db: Any = None, enterprise_id: str = "", vintage_year: int = 0
) -> _Row | None:
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    if not ent:
        return None
    for r in ent.get("cea_holdings") or []:
        if int(r.get("vintage_year")) == int(vintage_year):
            return _Row(r)
    return None


def add_cea_trade(
    db: Any = None, user_id: str = DEFAULT_USER_ID, enterprise_id: str = "", data: dict | None = None
) -> _Row:
    if not get_enterprise(db, user_id, enterprise_id):
        raise LookupError("enterprise not found")
    side = data.get("side")
    if side not in ("buy", "sell"):
        raise ValueError("side must be buy or sell")
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    vy = data.get("vintage_year")
    row = {
        "id": _uuid(),
        "enterprise_id": enterprise_id,
        "side": side,
        "qty": float(data["qty"]),
        "price": float(data.get("price") or 0),
        "note": str(data.get("note") or ""),
        "traded_at": _norm_trade_at(data.get("traded_at")),
        # 归属配额年度：与交易发生年解耦，用于把买卖量算进对应年度的「净卖出」
        "vintage_year": int(vy) if vy not in (None, "") else None,
    }
    ent.setdefault("cea_trades", []).append(row)
    _save_store(store)
    return _Row(row)


def list_cea_trades(db: Any = None, enterprise_id: str = "") -> list:
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    if not ent:
        return []
    rows = sorted(ent.get("cea_trades") or [], key=lambda r: r.get("traded_at"), reverse=True)
    return [_Row(r) for r in rows]


def delete_cea_trade(
    db: Any = None, user_id: str = DEFAULT_USER_ID, enterprise_id: str = "", trade_id: str = ""
) -> None:
    """删除一条 CEA 交易流水。净卖出是从流水派生的，删掉后持仓「净卖出」会自动跟着回退。"""
    if not get_enterprise(db, user_id, enterprise_id):
        raise LookupError("enterprise not found")
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    rows = ent.get("cea_trades") or []
    kept = [r for r in rows if str(r.get("id")) != str(trade_id)]
    if len(kept) == len(rows):
        raise LookupError("cea trade not found")
    ent["cea_trades"] = kept
    _save_store(store)


def cea_net_sell_qty(db: Any = None, enterprise_id: str = "") -> float:
    """从交易流水汇总净卖出 = 卖出量 − 买入量（万吨）。"""
    sold = 0.0
    bought = 0.0
    for t in list_cea_trades(db, enterprise_id):
        q = float(t.get("qty") or 0)
        if t.get("side") == "sell":
            sold += q
        elif t.get("side") == "buy":
            bought += q
    return sold - bought


def cea_trade_net_by_year(db: Any = None, enterprise_id: str = "") -> dict:
    """按「归属年度」汇总 CEA 流水的卖出/买入量（万吨）：{年: {"sell": x, "buy": y}}。

    归属年度优先取流水自带的 vintage_year（登记时选定），老数据没有这个字段时退回
    traded_at 的年份 —— 与前端台账面板「可用配额」的归集口径保持一致，
    否则面板显示可用 27 万吨、策略却按免费配额 10 万吨算缺口。
    """
    out: dict = {}
    for t in list_cea_trades(db, enterprise_id):
        vy = t.get("vintage_year")
        if vy in (None, ""):
            m = re.search(r"(\d{4})", str(t.get("traded_at") or ""))
            vy = int(m.group(1)) if m else None
        else:
            try:
                vy = int(vy)
            except (TypeError, ValueError):
                vy = None
        if not vy:
            continue
        cur = out.setdefault(int(vy), {"sell": 0.0, "buy": 0.0})
        q = float(t.get("qty") or 0)
        if t.get("side") == "sell":
            cur["sell"] += q
        else:
            cur["buy"] += q
    return out


def resolve_cea_net_sell(
    db: Any = None, enterprise_id: str = "", compliance_year: int = 0
) -> float:
    """净卖出（万吨）= 卖出 − 买入。

    口径与台账面板「可用 = 配额基准 − 卖出 + 买入」一致：某年度有交易流水时以流水为准，
    没有流水才回退到台账手填的「卖出 − 买入」；compliance_year == 0（全年度）逐年按同一优先级累加。
    """
    by_year = cea_trade_net_by_year(db, enterprise_id)
    if int(compliance_year) == 0:
        holdings = list_cea_holdings(db, enterprise_id)
        if holdings:
            total = 0.0
            for r in holdings:
                y = int(r.get("vintage_year") or 0)
                agg = by_year.get(y)
                if agg:
                    total += agg["sell"] - agg["buy"]
                else:
                    total += float(r.get("net_sell_qty") or 0) - float(r.get("buy_qty") or 0)
            return total
        return cea_net_sell_qty(db, enterprise_id)
    agg = by_year.get(int(compliance_year))
    if agg:
        return agg["sell"] - agg["buy"]
    row = get_cea_holding_for_year(db, enterprise_id, compliance_year)
    if row is not None:
        # net_sell_qty 是「卖出量」（沿用历史字段名），买入量在 buy_qty
        return float(row.get("net_sell_qty") or 0) - float(row.get("buy_qty") or 0)
    return cea_net_sell_qty(db, enterprise_id)


def upsert_ccer_holding(
    db: Any = None, user_id: str = DEFAULT_USER_ID, enterprise_id: str = "", data: dict | None = None
) -> _Row:
    if not get_enterprise(db, user_id, enterprise_id):
        raise LookupError("enterprise not found")
    data = data or {}
    expire_at = data.get("expire_at")
    if isinstance(expire_at, str) and expire_at:
        expire_at = expire_at[:10]
    qty = max(0.0, float(data.get("qty") or 0))
    if data.get("eligible_qty") is not None:
        eligible = max(0.0, float(data["eligible_qty"]))
        if eligible <= 0 and qty > 0:
            eligible = qty
        elif qty > 0:
            eligible = min(eligible, qty)
    else:
        eligible = qty
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    holding_id = str(data.get("id") or _uuid())
    row = None
    for r in ent.get("ccer_holdings") or []:
        if str(r.get("id")) == holding_id:
            row = r
            break
    if not row:
        row = {"id": holding_id}
        ent.setdefault("ccer_holdings", []).append(row)
    row["enterprise_id"] = enterprise_id
    row["project_type"] = str(data.get("project_type") or "")
    row["issue_year"] = int(data["issue_year"])
    row["expire_at"] = expire_at
    row["qty"] = qty
    row["cost"] = float(data.get("cost") or 0)
    row["eligible_qty"] = eligible
    row["linked_green_cert"] = bool(data.get("linked_green_cert") or False)
    _save_store(store)
    return _Row(row)


def list_ccer_holdings(db: Any = None, enterprise_id: str = "") -> list:
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    if not ent:
        return []
    rows = sorted(ent.get("ccer_holdings") or [], key=lambda r: r.get("issue_year"), reverse=True)
    return [_Row(r) for r in rows]


def delete_ccer_holding(
    db: Any = None, user_id: str = DEFAULT_USER_ID, enterprise_id: str = "", holding_id: str = ""
) -> None:
    if not get_enterprise(db, user_id, enterprise_id):
        raise LookupError("enterprise not found")
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    before = len(ent.get("ccer_holdings") or [])
    ent["ccer_holdings"] = [
        r for r in ent.get("ccer_holdings") or [] if str(r.get("id")) != str(holding_id)
    ]
    if len(ent.get("ccer_holdings")) == before:
        raise LookupError("ccer holding not found")
    _save_store(store)


def add_ccer_trade(
    db: Any = None, user_id: str = DEFAULT_USER_ID, enterprise_id: str = "", data: dict | None = None
) -> _Row:
    if not get_enterprise(db, user_id, enterprise_id):
        raise LookupError("enterprise not found")
    side = data.get("side")
    if side not in ("buy", "sell"):
        raise ValueError("side must be buy or sell")
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    traded_at = _norm_trade_at(data.get("traded_at"))
    project_type = str(data.get("project_type") or "general")
    row = {
        "id": _uuid(),
        "enterprise_id": enterprise_id,
        "side": side,
        "qty": float(data["qty"]),
        "price": float(data.get("price") or 0),
        "note": str(data.get("note") or ""),
        "traded_at": traded_at,
        "project_type": project_type,
    }
    ent.setdefault("ccer_trades", []).append(row)
    # 买入时若该「项目类型」尚无持仓记录，自动补一条空持仓（基准量 0、到期日空），
    # 让买入量能落到持仓表上可见，而不是变成「悬空流水」。
    if side == "buy":
        holdings = ent.setdefault("ccer_holdings", [])
        exists = any(
            str(h.get("project_type") or "") == project_type for h in holdings
        )
        if not exists:
            m = re.match(r"(\d{4})", traded_at)
            issue_year = int(m.group(1)) if m else int(_now_iso()[:4])
            holdings.append({
                "id": _uuid(),
                "enterprise_id": enterprise_id,
                "project_type": project_type,
                "issue_year": issue_year,
                "expire_at": "",
                "qty": 0.0,
                "cost": 0.0,
                "eligible_qty": 0.0,
                "linked_green_cert": False,
            })
    _save_store(store)
    return _Row(row)


def list_ccer_trades(db: Any = None, enterprise_id: str = "") -> list:
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    if not ent:
        return []
    rows = sorted(ent.get("ccer_trades") or [], key=lambda r: r.get("traded_at"), reverse=True)
    return [_Row(r) for r in rows]


def upsert_green_power(
    db: Any = None, user_id: str = DEFAULT_USER_ID, enterprise_id: str = "", data: dict | None = None
) -> _Row:
    if not get_enterprise(db, user_id, enterprise_id):
        raise LookupError("enterprise not found")
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    year = int(data["year"])
    row = None
    for r in ent.get("green_power") or []:
        if int(r.get("year")) == year:
            row = r
            break
    if not row:
        row = {"id": _uuid(), "year": year}
        ent.setdefault("green_power", []).append(row)
    row["market_green_mwh"] = float(data.get("market_green_mwh") or 0)
    row["self_gen_mwh"] = float(data.get("self_gen_mwh") or 0)
    row["premium_per_mwh"] = float(data.get("premium_per_mwh") or 0)
    row["contract_ref"] = str(data.get("contract_ref") or "")
    _save_store(store)
    return _Row(row)


def list_green_power(db: Any = None, enterprise_id: str = "") -> list:
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    if not ent:
        return []
    rows = sorted(ent.get("green_power") or [], key=lambda r: r.get("year"), reverse=True)
    return [_Row(r) for r in rows]


def delete_green_power(
    db: Any = None, user_id: str = DEFAULT_USER_ID, enterprise_id: str = "", year: int = 0
) -> None:
    """按年份删除绿电记录（绿电建档主键是 year）。"""
    if not get_enterprise(db, user_id, enterprise_id):
        raise LookupError("enterprise not found")
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    before = len(ent.get("green_power") or [])
    ent["green_power"] = [r for r in ent.get("green_power") or [] if int(r.get("year")) != int(year)]
    if len(ent.get("green_power")) == before:
        raise LookupError("green power year not found")
    _save_store(store)


def upsert_green_cert(
    db: Any = None, user_id: str = DEFAULT_USER_ID, enterprise_id: str = "", data: dict | None = None
) -> _Row:
    if not get_enterprise(db, user_id, enterprise_id):
        raise LookupError("enterprise not found")
    data = data or {}
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    cert_id = str(data.get("id") or _uuid())
    row = None
    for r in ent.get("green_certs") or []:
        if str(r.get("id")) == cert_id:
            row = r
            break
    if not row:
        row = {"id": cert_id}
        ent.setdefault("green_certs", []).append(row)
    row["enterprise_id"] = enterprise_id
    row["year"] = int(data["year"])
    row["qty"] = float(data.get("qty") or 0)
    row["unit_price"] = float(data.get("unit_price") or 0)
    row["retired"] = bool(data.get("retired") or False)
    row["ren_weight_target"] = data.get("ren_weight_target")
    _save_store(store)
    return _Row(row)


def list_green_certs(db: Any = None, enterprise_id: str = "") -> list:
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    if not ent:
        return []
    rows = sorted(ent.get("green_certs") or [], key=lambda r: r.get("year"), reverse=True)
    return [_Row(r) for r in rows]


def delete_green_cert(
    db: Any = None, user_id: str = DEFAULT_USER_ID, enterprise_id: str = "", cert_id: str = ""
) -> None:
    """按 id 删除绿证记录（绿证建档主键是 id，同年份可有多个批次）。"""
    if not get_enterprise(db, user_id, enterprise_id):
        raise LookupError("enterprise not found")
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    before = len(ent.get("green_certs") or [])
    ent["green_certs"] = [r for r in ent.get("green_certs") or [] if str(r.get("id")) != str(cert_id)]
    if len(ent.get("green_certs")) == before:
        raise LookupError("green cert not found")
    _save_store(store)


def upsert_market_cea(db: Any = None, data: dict | None = None) -> _Row:
    data = data or {}
    ym = str(data["year_month"])
    store = _load_store()
    row = None
    for r in store.get("market_cea") or []:
        if str(r.get("year_month")) == ym:
            row = r
            break
    if not row:
        row = {"id": _uuid(), "year_month": ym}
        store.setdefault("market_cea", []).append(row)
    row["avg_price"] = float(data["avg_price"])
    row["high"] = data.get("high")
    row["low"] = data.get("low")
    row["period_tag"] = str(data.get("period_tag") or "")
    _save_store(store)
    return _Row(row)


def list_market_cea(db: Any = None, limit: int = 60) -> list:
    store = _load_store()
    rows = sorted(store.get("market_cea") or [], key=lambda r: r.get("year_month"), reverse=True)
    return [_Row(r) for r in rows[:limit]]


def upsert_market_ccer(db: Any = None, data: dict | None = None) -> _Row:
    data = data or {}
    ym = str(data["year_month"])
    ptype = str(data.get("project_type") or "general")
    store = _load_store()
    row = None
    for r in store.get("market_ccer") or []:
        if str(r.get("year_month")) == ym and str(r.get("project_type") or "general") == ptype:
            row = r
            break
    if not row:
        row = {"id": _uuid(), "year_month": ym, "project_type": ptype}
        store.setdefault("market_ccer", []).append(row)
    row["avg_price"] = float(data["avg_price"])
    _save_store(store)
    return _Row(row)


def list_market_ccer(db: Any = None, limit: int = 60) -> list:
    store = _load_store()
    rows = sorted(store.get("market_ccer") or [], key=lambda r: r.get("year_month"), reverse=True)
    return [_Row(r) for r in rows[:limit]]


def upsert_market_energy(db: Any = None, data: dict | None = None) -> _Row:
    data = data or {}
    ym = str(data["year_month"])
    region = str(data.get("region") or "national")
    store = _load_store()
    row = None
    for r in store.get("market_energy") or []:
        if str(r.get("year_month")) == ym and str(r.get("region") or "national") == region:
            row = r
            break
    if not row:
        row = {"id": _uuid(), "year_month": ym, "region": region}
        store.setdefault("market_energy", []).append(row)
    row["green_premium"] = data.get("green_premium")
    row["grec_price"] = data.get("grec_price")
    row["coal_price"] = data.get("coal_price")
    _save_store(store)
    return _Row(row)


def list_market_energy(db: Any = None, limit: int = 60) -> list:
    store = _load_store()
    rows = sorted(store.get("market_energy") or [], key=lambda r: r.get("year_month"), reverse=True)
    return [_Row(r) for r in rows[:limit]]


async def sync_market_quotes(db: Any = None) -> dict[str, Any]:
    """拉取外部 CEA/CCER 行情并写入月度表（复用目标项目同步行情函数）。"""
    from app.services.carbon_compliance.market_sync import (
        fetch_cneeex_daily_quotes_sync,
    )

    errors: list[str] = []
    written: dict[str, Any] = {"cea": None, "ccer": None, "cea_months": 0}
    try:
        hist = fetch_cneeex_daily_quotes_sync() or []
        by_month: dict[str, list[float]] = {}
        for q in hist:
            t = str(q.get("t") or "")
            ym = t[:7]
            by_month.setdefault(ym, []).append(float(q.get("close") or q.get("price") or 0))
        months = sorted(by_month.keys())
        for ym in months:
            prices = by_month[ym]
            upsert_market_cea(
                None,
                {
                    "year_month": ym,
                    "avg_price": sum(prices) / len(prices),
                    "high": max(prices),
                    "low": min(prices),
                    "period_tag": _period_tag(int(ym.split("-")[1])),
                },
            )
        written["cea_months"] = len(months)
        if months:
            last_ym = months[-1]
            row = None
            for r in list_market_cea(None, limit=1):
                row = r
            written["cea"] = {
                "year_month": last_ym,
                "avg_price": row.get("avg_price") if row else None,
                "high": row.get("high") if row else None,
                "low": row.get("low") if row else None,
            }
    except Exception as exc:  # noqa: BLE001
        errors.append(f"cea: {exc}")

    settings = get_settings(db)
    integrations = dict(settings.get("integrations") or {})
    integrations["last_sync_at"] = _now_iso()
    integrations["last_sync_ok"] = bool(written["cea"] or written["ccer"])
    integrations["last_sync_detail"] = {"written": written, "errors": errors}
    update_settings(db, {"integrations": integrations})

    return {
        "ok": bool(written["cea"] or written["ccer"]),
        "written": written,
        "errors": errors,
    }


def _period_tag(month: int) -> str:
    if month <= 2:
        return "Q1"
    if month <= 5:
        return "Q2"
    if month <= 8:
        return "Q3"
    return "Q4"


def should_auto_sync_market(settings: dict | None = None) -> bool:
    """根据 market_sync_period 与 last_sync_at 判断是否应自动同步。"""
    cfg = (settings or {}).get("integrations") or {}
    if cfg.get("market_sync_enabled") is False:
        return False
    period = str(cfg.get("market_sync_period") or "day").lower()
    last = cfg.get("last_sync_at")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
    except Exception:
        return True
    now = datetime.now(timezone.utc)
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    age_h = (now - last_dt.astimezone(timezone.utc)).total_seconds() / 3600.0
    if period in ("hour", "hourly"):
        return age_h >= 1.0
    if period in ("day", "daily"):
        return age_h >= 12.0
    return age_h >= 24.0


def _holding_to_dict(h: _Row) -> dict:
    return {
        "eligible_qty": h.get("eligible_qty"),
        "qty": h.get("qty"),
        "expire_at": h.get("expire_at"),
        "linked_green_cert": h.get("linked_green_cert"),
    }


def run_strategy(
    db: Any = None,
    user_id: str = DEFAULT_USER_ID,
    enterprise_id: str = "",
    compliance_year: int = 0,
    *,
    notify: bool = True,
) -> _Row:
    ent = get_enterprise(db, user_id, enterprise_id)
    if not ent:
        raise LookupError("enterprise not found")
    settings = get_settings(db)
    industry_params = (settings.get("industry_params") or {}).get(ent.get("industry")) or {}
    cost = settings.get("cost") or {}
    compliance_cfg = settings.get("compliance") or {}

    # compliance_year == 0 表示「全年度」：聚合所有年度的排放 / 预测 / CEA 配额。
    is_all_years = int(compliance_year) == 0
    emission = None
    forecasts = list_forecasts(db, enterprise_id)
    emissions = list_emission_years(db, enterprise_id)
    if is_all_years:
        # 全年度：把各年 scope1/scope2/外购电累加；verified_override 用各年 verified_total 累加
        scopes = {"scope1_combustion": 0.0, "scope1_process": 0.0, "scope2_power": 0.0, "purchased_mwh": 0.0}
        verified_sum = None
        for r in emissions:
            for k in scopes:
                scopes[k] += float(r.get(k) or 0.0)
            if r.get("verified_total") is not None:
                verified_sum = (verified_sum or 0.0) + float(r.get("verified_total"))
        forecast_total = None
        for f in forecasts:
            if f.get("forecast_total") is not None:
                forecast_total = (forecast_total or 0.0) + float(f.get("forecast_total"))
        # 构造一个聚合后的 emission 字典，供后续 scope 取值
        emission = {**scopes}
        if verified_sum is not None:
            emission["verified_total"] = verified_sum
        # 无排放台账但有预测时，用预测合计兜底
        if not emissions and forecast_total is not None:
            emission["verified_total"] = forecast_total
        forecast = {"forecast_total": forecast_total} if forecast_total is not None else None
    else:
        for r in emissions:
            if int(r.get("year")) == int(compliance_year):
                emission = r
                break
        forecast = None
        for r in forecasts:
            if int(r.get("year")) == int(compliance_year):
                forecast = r
                break

    # ---------------- 排放口径：有预测用预测，没预测才纯按台账 ----------------
    # 台账改成逐月上报后，年度值可能只是「已上报月份的合计」。直接拿它核算会把缺口
    # 算反：冀东 2027 只上报 1—6 月（台账 728 万吨 → 盈余 1,272），而按存档预测
    # 2,305.6 万吨实际是缺口 269.6。所以目标年度一旦做了排放预测，就以预测为准；
    # 用户没做预测时保持原行为，只按台账核定值核算。
    ledger_by_year: dict[int, float] = {}
    for _r in emissions:
        _y = int(_r.get("year") or 0)
        if _y > 0 and _r.get("verified_total") is not None:
            ledger_by_year[_y] = float(_r.get("verified_total") or 0.0)
    forecast_by_year: dict[int, float] = {}
    for _f in forecasts:
        _y = int(_f.get("year") or 0)
        _v = _f.get("forecast_total")
        if _y > 0 and _v is not None and float(_v) > 0:
            forecast_by_year[_y] = float(_v)
    # 人工核定值（annual_override）代表已确认的核查结果，比预测更权威；
    # override_legacy 是历史冻结值，不算「人工核定」，不能拿它压预测
    override_years: set[int] = {
        int(r.get("year") or 0)
        for r in emissions
        if (r.get("annual_override") or {}) and not r.get("override_legacy")
    }

    emission_basis = "none"
    emission_basis_text = ""
    emission_basis_warnings: list[str] = []
    chosen_total: float | None = None
    ledger_scope_total: float | None = None
    forecast_scope_total: float | None = None

    if is_all_years:
        all_years = sorted(set(ledger_by_year) | set(forecast_by_year))
        picked = 0.0
        fc_years: list[int] = []
        lg_years: list[int] = []
        for _y in all_years:
            if _y in override_years and _y in ledger_by_year:
                # 核定值优先，即便该年度也做了预测
                picked += ledger_by_year[_y]
                lg_years.append(_y)
            elif _y in forecast_by_year:
                picked += forecast_by_year[_y]
                fc_years.append(_y)
            elif _y in ledger_by_year:
                picked += ledger_by_year[_y]
                lg_years.append(_y)
        ledger_scope_total = sum(ledger_by_year.values()) if ledger_by_year else None
        forecast_scope_total = sum(forecast_by_year.values()) if forecast_by_year else None
        if fc_years and lg_years:
            emission_basis = "mixed"
            emission_basis_text = (
                "全年度口径："
                + "、".join(str(y) for y in fc_years)
                + " 年度按排放预测，"
                + "、".join(str(y) for y in lg_years)
                + " 年度按台账核定值"
            )
        elif fc_years:
            emission_basis = "forecast"
            emission_basis_text = (
                "全年度口径：各年度均按排放预测合计（" + str(len(fc_years)) + " 个年度）"
            )
        elif lg_years:
            emission_basis = "ledger"
            emission_basis_text = (
                "全年度口径：按台账核定值合计（" + str(len(lg_years)) + " 个年度，无排放预测）"
            )
        if emission_basis != "none":
            chosen_total = round(picked, 6)
    else:
        _ty = int(compliance_year)
        ledger_scope_total = ledger_by_year.get(_ty)
        forecast_scope_total = forecast_by_year.get(_ty)
        if _ty in override_years and _ty in ledger_by_year:
            emission_basis = "ledger_override"
            chosen_total = ledger_by_year[_ty]
            emission_basis_text = (
                str(_ty)
                + " 年度台账为人工核定值 "
                + f"{chosen_total:.2f}"
                + " 万吨，优先于排放预测"
                + (
                    " " + f"{forecast_by_year[_ty]:.2f}" + " 万吨"
                    if _ty in forecast_by_year
                    else ""
                )
                + "（核定值代表已确认的核查结果）"
            )
        elif _ty in forecast_by_year:
            emission_basis = "forecast"
            chosen_total = forecast_by_year[_ty]
            if _ty in ledger_by_year:
                emission_basis_text = (
                    str(_ty)
                    + " 年度按排放预测 "
                    + f"{chosen_total:.2f}"
                    + " 万吨核算（台账年度值 "
                    + f"{ledger_by_year[_ty]:.2f}"
                    + " 万吨仅作参考）"
                )
            else:
                emission_basis_text = (
                    str(_ty)
                    + " 年度台账无记录，直接采用排放预测 "
                    + f"{chosen_total:.2f}"
                    + " 万吨核算"
                )
        elif _ty in ledger_by_year:
            emission_basis = "ledger"
            chosen_total = ledger_by_year[_ty]
            emission_basis_text = (
                str(_ty)
                + " 年度未做排放预测，按台账核定值 "
                + f"{chosen_total:.2f}"
                + " 万吨核算"
            )
        else:
            emission_basis_text = str(_ty) + " 年度既无排放预测也无台账核定值，按分项排放核算"

        # 预测是快照：台账之后补录/改数，预测里的「台账月」就可能与现状不一致
        if _ty in forecast_by_year and emission_basis == "forecast":
            _frow = next((f for f in forecasts if int(f.get("year") or 0) == _ty), None)
            _erow = emission if (emission and int(emission.get("year") or 0) == _ty) else None
            if _frow is not None and _erow is not None:
                _stale = _forecast_ledger_drift(_frow, _erow)
                if _stale:
                    emission_basis_warnings.append(_stale)

    # CEA 逐年滚动核销也用同一口径，否则「清缴用预测、结存用台账」会自相矛盾
    emission_rows_for_roll: list[dict] = [dict(_r) for _r in emissions]
    _roll_ledger_years = {int(r.get("year") or 0) for r in emission_rows_for_roll}
    for _row in emission_rows_for_roll:
        _y = int(_row.get("year") or 0)
        if _y in forecast_by_year and _y not in override_years:
            _row["verified_total"] = forecast_by_year[_y]
    for _y, _v in forecast_by_year.items():
        if _y not in _roll_ledger_years:
            emission_rows_for_roll.append({"year": _y, "verified_total": _v})

    cea_rows = list_cea_holdings(db, enterprise_id)
    free_cea = 0.0
    sellable = 0.0
    allocated_free = 0.0  # 当年新分配（不含结转）
    carry_in = 0.0
    market_start_year = int(ent.get("market_start_year") or 0)
    # 配额逐年滚动核算。
    # 台账 cea_holdings 存的是「年度发放量」而非「当前结存」，旧逻辑把所有
    # 「市场纳入年及以后」的发放量整包累加进目标年度，且从不扣减各年清缴消耗，
    # 等于同一批配额被永久重复计入（跑 2027 年度会把 2025/2026 的发放量全算进来）。
    # 单年度一律走滚动：清缴逐年核销、结存向下传递；全年度保留面板聚合口径。
    cea_roll = None
    if is_all_years:
        for c in cea_rows:
            allocated = max(0.0, float(c.get("free_quota") or 0))
            carried = max(0.0, float(c.get("carry_forward_qty") or 0))
            usable = allocated + carried
            free_cea += usable
            allocated_free += allocated
            carry_in += carried
            if c.get("estimated_free_quota"):
                free_cea = max(free_cea, float(c.get("estimated_free_quota")) + carried)
            if c.get("sellable_cap") is not None:
                sellable += float(c.get("sellable_cap"))
            else:
                sellable += usable
    else:
        cea_roll = roll_cea_over_years(
            holdings=[
                {
                    "vintage_year": c.get("vintage_year"),
                    "free_quota": c.get("free_quota"),
                    "carry_forward_qty": c.get("carry_forward_qty"),
                    "net_sell_qty": c.get("net_sell_qty"),
                    "buy_qty": c.get("buy_qty"),
                    "estimated_free_quota": c.get("estimated_free_quota"),
                    "sellable_cap": c.get("sellable_cap"),
                }
                for c in cea_rows
            ],
            emissions=emission_rows_for_roll,
            trades_by_year=cea_trade_net_by_year(db, enterprise_id),
            target_year=int(compliance_year),
            market_start_year=market_start_year,
        )
        free_cea = cea_roll.usable
        allocated_free = cea_roll.allocated_free
        carry_in = cea_roll.carry_in
        sellable = cea_roll.sellable

    ccer_rows = list_ccer_holdings(db, enterprise_id)
    own_ccer = eligible_ccer_qty([_holding_to_dict(h) for h in ccer_rows])

    # ---------------- 交易流水并入可用量 ----------------
    # 「可用」= 免费配额 + 结转 + 买入 − 卖出，与台账面板同一口径。
    # 旧版只认持仓台账的免费配额，登记了买入流水后跑策略仍按免费配额算缺口，
    # 于是面板上可用配额已是 27 万吨、策略却报「排放 20 − 配额 10 = 缺口 10 万吨」。
    trade_by_year = cea_trade_net_by_year(db, enterprise_id)
    traded_buy = 0.0
    traded_sell = 0.0
    for _y, _agg in trade_by_year.items():
        if int(compliance_year) == 0 or int(_y) == int(compliance_year):
            traded_buy += _agg["buy"]
            traded_sell += _agg["sell"]
    if cea_roll is not None:
        # 滚动核算已在目标年度并入买入/卖出，这里只取净额供结转测算，不再二次扣减
        traded_buy = cea_roll.bought
        traded_sell = cea_roll.sold
        net_sell = traded_sell - traded_buy  # 卖出 − 买入
    else:
        net_sell = resolve_cea_net_sell(db, enterprise_id, compliance_year)  # 卖出 − 买入
        if net_sell:
            free_cea = max(0.0, free_cea - net_sell)
            sellable = max(0.0, sellable - net_sell)
    # CCER 流水同样增减可抵扣量（买入加、卖出减），否则登记了买入也抵扣不了
    ccer_traded_net = 0.0
    for t in list_ccer_trades(db, enterprise_id):
        q = float(t.get("qty") or 0)
        ccer_traded_net += q if t.get("side") == "buy" else -q
    if ccer_traded_net:
        own_ccer = max(0.0, own_ccer + ccer_traded_net)

    grid_factor = float(
        industry_params.get("grid_emission_factor")
        or cost.get("grid_emission_factor")
        or 0.5703
    )
    ccer_ratio = float(compliance_cfg.get("ccer_max_ratio") or 0.05)

    scope1_c = float(emission.get("scope1_combustion") or 0.0) if emission else 0.0
    scope1_p = float(emission.get("scope1_process") or 0.0) if emission else 0.0
    scope2 = float(emission.get("scope2_power") or 0.0) if emission else 0.0
    purchased = float(emission.get("purchased_mwh") or 0.0) if emission else 0.0

    # 核查排放：chosen_total 已在上面的口径选择里定了（预测优先 / 无预测按台账）。
    # 只有在「既无预测、台账又没有核定总量」时才回退到分项 Scope1 计算。
    verified_override = float(chosen_total) if chosen_total is not None else None

    acc = compute_accounting(
        AccountingInput(
            scope1_combustion=scope1_c,
            scope1_process=scope1_p,
            scope2_power=scope2,
            purchased_mwh=purchased,
            market_green_mwh=0.0,
            self_gen_mwh=0.0,
            free_cea_quota=free_cea,
            own_ccer_eligible=own_ccer,
            grid_emission_factor=grid_factor,
            ccer_max_ratio=ccer_ratio,
            verified_override=verified_override,
        )
    )

    cea_market = list_market_cea(db, limit=60)
    prices = [float(r.get("avg_price")) for r in reversed(cea_market)]
    current_cea = prices[-1] if prices else 80.0
    ccer_market = list_market_ccer(db, limit=24)
    current_ccer = float(ccer_market[0].get("avg_price")) if ccer_market else 60.0

    market = judge_market_cycle(
        prices,
        current_cea,
        current_ccer,
        # 本方仓位方向：缺口方不能出现「建议出售」
        side=(
            "gap"
            if float(acc.compliance_gap or 0) > 0
            else ("surplus" if float(acc.compliance_gap or 0) < 0 else None)
        ),
        low_percentile=float(compliance_cfg.get("price_low_percentile") or 0.30),
        mid_percentile=float(compliance_cfg.get("price_mid_percentile") or 0.70),
    )

    # 日度碳价预测：用「下一交易日/近期」预测价作为当日无挂单时的锚定
    price_forecast_summary = None
    cea_predicted = None
    ccer_predicted = None
    try:
        from app.services.carbon_compliance.market_sync import fetch_cneeex_daily_quotes_sync
        from app.services.carbon_compliance.price_forecast import forecast_cea_to_year_end

        hist = fetch_cneeex_daily_quotes_sync()
        if not hist:
            hist = [
                {"t": f"{r.get('year_month')}-15", "close": float(r.get("avg_price"))}
                for r in reversed(cea_market)
            ]
        fc = forecast_cea_to_year_end(hist)
        if fc.get("ok"):
            price_forecast_summary = fc.get("summary")
            pts = fc.get("points") or []
            if pts:
                cea_predicted = float(pts[0].get("price") or pts[0].get("close") or current_cea)
            ye = float((price_forecast_summary or {}).get("year_end_price") or current_cea)
            if acc.compliance_gap > 0 and ye > current_cea * 1.03:
                market.rationale = (
                    (market.rationale or "")
                    + f"；日度预测年底约 {ye:.1f} 元/吨（高于现价），宜评估提前分批采购"
                )
            elif acc.compliance_gap < 0 and ye > current_cea * 1.03:
                market.rationale = (
                    (market.rationale or "")
                    + f"；日度预测年底约 {ye:.1f} 元/吨，盈余配额可择高位窗口出售"
                )
    except Exception:  # noqa: BLE001
        price_forecast_summary = None

    # CCER 无公开分时：用最新日均作当日预测锚（可后续接独立预测）
    ccer_predicted = current_ccer

    # 结转测算：年末持仓≈清缴后盈余；净卖出沿用上面已算好的值（流水优先、台账手填兜底）。
    # 口径按履约年度自动切换：《2025、2026 年度配额总量和分配方案》起取消结转数量限制，
    # 盈余配额可全额结转，2025 年度及以后不再有「超额失效」。
    carry_policy = resolve_carry_policy(
        compliance_year, str(compliance_cfg.get("carry_policy") or "auto")
    )
    year_end_holding = max(0.0, -min(0.0, float(acc.compliance_gap)))
    carry_base = float(compliance_cfg.get("carry_base_qty") or 0)
    if carry_base <= 0:
        # 基础结转量按政策取 1 万吨；不再用当年分配量兜底（会放大上限数百倍）
        carry_base = POLICY_DEFAULT_BASE_QTY
    carry = compute_carry_forward(
        base_qty=carry_base,
        net_sell=net_sell,
        year_end_holding=year_end_holding,
        net_sell_multiplier=float(compliance_cfg.get("carry_net_sell_multiplier") or 1.5),
        deadline_md=str(compliance_cfg.get("carry_forward_deadline_md") or "06-10"),
        deadline_year=compliance_year + 1 if not is_all_years else None,  # 履约年后的结转日；全年度无单一年度，回退当年
        policy=carry_policy,
    )

    payload = build_strategy_payload(
        risk_profile=ent.get("risk_profile"),
        annual_budget_cap=ent.get("annual_budget_cap"),
        single_trade_limit=ent.get("single_trade_limit"),
        settings=settings,
        accounting=acc,
        market=market,
        cea_price=current_cea,
        ccer_price=current_ccer,
        sellable_cea=sellable,
        cea_price_predicted=cea_predicted,
        ccer_price_predicted=ccer_predicted,
        carry_forward=carry,
    )
    if price_forecast_summary:
        payload["price_forecast"] = price_forecast_summary
        tags = dict(payload.get("market_tags") or {})
        tags["price_forecast"] = price_forecast_summary
        payload["market_tags"] = tags
    payload["carry_forward"] = carry.to_dict()
    payload["accounting"] = {
        **payload["accounting"],
        "allocated_free_cea": allocated_free,
        "carry_forward_qty": carry_in,
        "usable_cea_total": float(acc.free_cea_quota),
        # 流水拆分：让「可用 CEA = 免费 + 买入 − 卖出」在报告里可追溯
        "traded_buy_qty": traded_buy,
        "traded_sell_qty": traded_sell,
        # CCER 抵销比例上限（默认 5%），报告里把「上限 = 排放 × 比例」写清楚
        "ccer_max_ratio": ccer_ratio,
        # 排放口径留痕：报告与界面据此说明「核查排放这个数是预测还是台账」
        "emission_basis": emission_basis,
        "emission_basis_text": emission_basis_text,
        "ledger_verified_total": ledger_scope_total,
        "forecast_verified_total": forecast_scope_total,
    }
    if emission_basis_warnings:
        payload["accounting"]["emission_basis_warnings"] = list(emission_basis_warnings)
    if cea_roll is not None:
        # 逐年清缴过程留痕：报告可据此说明「可用配额为何是这个数」
        payload["accounting"]["cea_rollforward"] = cea_roll.to_dict()
        if cea_roll.warnings:
            payload["accounting"]["cea_rollforward_warnings"] = list(cea_roll.warnings)
    tags = dict(payload.get("market_tags") or {})
    tags["carry_forward"] = carry.to_dict()
    payload["market_tags"] = tags
    report_md = strategy_run_to_markdown(
        enterprise_name=ent.get("name"),
        compliance_year="全年度" if is_all_years else compliance_year,
        accounting=payload["accounting"],
        market_tags=payload["market_tags"],
        plans=payload["plans"],
    )

    store = _load_store()
    ent_row = _find_enterprise(store, enterprise_id)
    run = {
        "id": _uuid(),
        "enterprise_id": enterprise_id,
        "user_id": str(user_id),
        "compliance_year": int(compliance_year),
        "accounting_snapshot": payload["accounting"],
        "market_tags": payload["market_tags"],
        "plans": payload["plans"],
        "status": "completed",
        "report_md": report_md,
        "created_at": _now_iso(),
    }
    ent_row.setdefault("strategy_runs", []).append(run)

    # 分批后同一方案里会出现多条 use_ccer/buy_ccer，取「单条最大」会低估用量：
    # 方案内求和、再跨方案取最大（三档是互斥备选，不能相加）
    ccer_planned = 0.0
    for p in payload["plans"]:
        _ccer_used_in_plan = sum(
            float(a.get("qty") or 0)
            for a in (p.get("actions") or [])
            if a.get("action") in ("use_ccer", "buy_ccer")
        )
        ccer_planned = max(ccer_planned, _ccer_used_in_plan)

    alert_dicts = build_alerts(
        compliance_year=compliance_year if not is_all_years else date.today().year,
        clearance_deadline_md=str(industry_params.get("clearance_deadline_md") or "12-31"),
        warn_days=list(compliance_cfg.get("clearance_warn_days") or [90, 30, 15]),
        compliance_gap=acc.compliance_gap,
        ccer_used=ccer_planned,
        ccer_cap=acc.ccer_cap,
        price_band=market.price_band,
        carry_forward=carry,
    )
    for ad in alert_dicts:
        due = ad.get("due_at")
        if isinstance(due, datetime):
            due = due.isoformat()
        ent_row.setdefault("alerts", []).append(
            {
                "id": _uuid(),
                "enterprise_id": enterprise_id,
                "user_id": str(user_id),
                "level": ad["level"],
                "alert_type": ad["alert_type"],
                "message": ad["message"],
                "due_at": due,
                "acked": False,
                "created_at": _now_iso(),
            }
        )
    _save_store(store)

    if notify and alert_dicts:
        try:
            top = alert_dicts[0]
            # 无通知服务时静默跳过
            _ = top
        except Exception:  # noqa: BLE001
            pass

    return _Row(run)


def list_strategy_runs(
    db: Any = None, user_id: str = DEFAULT_USER_ID, enterprise_id: str = "", limit: int = 20
) -> list:
    if not get_enterprise(db, user_id, enterprise_id):
        raise LookupError("enterprise not found")
    store = _load_store()
    ent = _find_enterprise(store, enterprise_id)
    rows = sorted(ent.get("strategy_runs") or [], key=lambda r: r.get("created_at"), reverse=True)
    return [_Row(r) for r in rows[:limit]]


def list_alerts(
    db: Any = None,
    user_id: str = DEFAULT_USER_ID,
    *,
    enterprise_id: str | None = None,
    unacked_only: bool = False,
    limit: int = 50,
) -> list:
    store = _load_store()
    out: list = []
    for e in store.get("enterprises") or []:
        if str(e.get("user_id")) != str(user_id):
            continue
        if enterprise_id and str(e.get("id")) != str(enterprise_id):
            continue
        for a in e.get("alerts") or []:
            if unacked_only and a.get("acked"):
                continue
            out.append(_Row(a))
    out.sort(key=lambda a: a.get("created_at") or "", reverse=True)
    return out[:limit]


def ack_alert(db: Any = None, user_id: str = DEFAULT_USER_ID, alert_id: str = "") -> _Row:
    store = _load_store()
    for e in store.get("enterprises") or []:
        if str(e.get("user_id")) != str(user_id):
            continue
        for a in e.get("alerts") or []:
            if str(a.get("id")) == str(alert_id):
                a["acked"] = True
                _save_store(store)
                return _Row(a)
    raise LookupError("alert not found")


# ---------------------------------------------------------------- import
# 排放台账改版后（年度值 → 年度值 + 逐月明细），模板表头与解析别名必须同源，
# 否则用户照着模板填、导入却认不出列，数据就"对不齐"。
# 本模板只负责排放台账（排放月度 + 排放年度）；CEA / CCER / 绿电 / 绿证仍走各自的台账页录入，
# 不放进模板里——混在一份表里既容易填错单位，也会让"这份表该填到哪"变得含糊。
_IMPORT_KEYS: tuple[str, ...] = (
    "emissions_month",
    "emissions",
)


@dataclass(frozen=True)
class _Col:
    """一列台账字段。模板表头由 name + unit 生成，解析别名与之同源。"""

    field: str
    name: str
    unit: str = ""
    aliases: tuple[str, ...] = ()
    kind: str = "float"  # float / int / bool / date / ccer_type / str
    required: bool = False
    note: str = ""
    example: str = ""

    @property
    def header(self) -> str:
        return f"{self.name}({self.unit})" if self.unit else self.name


@dataclass(frozen=True)
class _Sheet:
    """一个数据页：标题、历史别名（兼容旧版英文页名）与列定义。"""

    key: str
    title: str
    cols: tuple[_Col, ...]
    aliases: tuple[str, ...] = ()
    note: str = ""


# 排放台账的 6 个指标在「月度」与「年度」两页里同名同单位：
# 年度值就是 12 个月的合计，所以两页共用这份列定义，避免两处口径漂移
_EMISSION_METRIC_COLS: tuple[_Col, ...] = (
    _Col(
        "verified_total",
        "核查排放",
        "万吨",
        ("核查排放量", "核查排放总计"),
        note="经核查的排放总量，核算与报告的主口径",
        example="1600",
    ),
    _Col(
        "scope1_combustion",
        "范畴1燃料燃烧",
        "万吨",
        ("范畴一燃料燃烧", "化石燃料燃烧", "燃料燃烧"),
        example="1350",
    ),
    _Col(
        "scope1_process",
        "范畴1工业过程",
        "万吨",
        ("范畴一工业过程", "工业过程"),
        example="250",
    ),
    _Col(
        "scope2_power",
        "范畴2净购入电力",
        "万吨",
        ("范畴二净购入电力", "净购入电力", "范畴2电力"),
        example="114",
    ),
    _Col(
        "purchased_mwh",
        "净购入电量",
        "MWh",
        ("外购电量", "净购入电力量"),
        note="注意是电量（MWh），不是万吨",
        example="220000",
    ),
    _Col(
        "ccer_used",
        "CCER已用",
        "万吨",
        ("已用CCER", "CCER已用量"),
        note="该月/该年已用于抵销的 CCER 数量",
        example="0",
    ),
)

_IMPORT_SHEETS: tuple[_Sheet, ...] = (
    _Sheet(
        "emissions_month",
        "排放月度",
        (
            _Col("year", "年份", aliases=("年度",), kind="int", required=True, example="2027"),
            _Col("month", "月份", aliases=("月",), kind="int", required=True, note="1-12", example="1"),
            *_EMISSION_METRIC_COLS,
        ),
        aliases=("emissions_month", "monthly", "月度排放", "排放明细", "排放月度明细"),
        note="逐月上报明细。填了月度，年度值由 12 个月加总得出。",
    ),
    _Sheet(
        "emissions",
        "排放年度",
        (
            _Col("year", "年份", aliases=("年度",), kind="int", required=True, example="2027"),
            *_EMISSION_METRIC_COLS,
            _Col(
                "historical_gap",
                "历史缺口",
                "万吨",
                ("历史履约缺口",),
                note="历史年度遗留的履约缺口，没有就留空",
                example="0",
            ),
        ),
        aliases=("emissions", "emission", "排放台账", "排放年度值"),
        note="年度核定值。与「排放月度」12 个月合计不一致时以这里为准（界面显示「核定」）。",
    ),
)

_UNIT_TAIL_RE = re.compile(r"\([^()]*\)\s*$")
_BARE_UNIT_RE = re.compile(r"[_\-－]?(万吨|万mwh|mwh)$", re.IGNORECASE)
_EMPTY_TEXTS = {"", "-", "--", "—", "–", "/", "无", "n/a", "na", "none", "null"}


def _norm_header(value: Any) -> str:
    """表头归一化：去单位、去必填星号、去空格、全角括号转半角、英文转小写。

    这样模板里的「核查排放(万吨)」、旧模板里的「verified_total_万吨」、
    用户手改的「核查排放（万吨）*」都会落到同一个键上，新旧表格都能导入。
    """
    text = str(value or "").strip()
    text = text.replace("（", "(").replace("）", ")").replace("\u3000", "")
    text = re.sub(r"[*＊]+\s*$", "", text)
    text = _UNIT_TAIL_RE.sub("", text)
    text = _BARE_UNIT_RE.sub("", text)
    text = re.sub(r"[\s:：]+", "", text)
    return text.lower()


def _norm_sheet_name(value: Any) -> str:
    return re.sub(r"[\s_\-]+", "", str(value or "")).lower()


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if text.lower() in _EMPTY_TEXTS:
        return None
    # 容忍「1,200.5 万吨」「约 30」这类人读写法，取第一段数字
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text.replace(",", "").replace("，", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _to_int(value: Any) -> int | None:
    num = _to_float(value)
    return None if num is None else int(round(num))


_COERCERS: dict[str, Any] = {
    "float": _to_float,
    "int": _to_int,
}


def _col_letter(index: int) -> str:
    if get_column_letter is not None:
        return get_column_letter(index)
    return chr(64 + index) if index <= 26 else str(index)


def _sheet_alias_index(sheet: _Sheet) -> dict[str, str]:
    """归一化表头 → 字段名。模板表头、字段名本身、历史别名都能命中。"""
    index: dict[str, str] = {}
    for col in sheet.cols:
        for text in (col.header, col.name, col.field, *col.aliases):
            key = _norm_header(text)
            if key and key not in index:
                index[key] = col.field
    return index


def _find_import_sheet(wb: Any, sheet: _Sheet) -> Any:
    wanted = {_norm_sheet_name(sheet.title), _norm_sheet_name(sheet.key)}
    wanted.update(_norm_sheet_name(a) for a in sheet.aliases)
    for name in wb.sheetnames:
        if _norm_sheet_name(name) in wanted:
            return wb[name]
    return None


def _read_import_sheet(
    ws: Any, sheet: _Sheet, errors: list[str]
) -> list[tuple[int, dict[str, Any]]]:
    """读一个数据页 → [(Excel 行号, 字段字典)]。

    表头行允许出现在前 8 行里（用户常在顶部加标题/说明），取命中字段最多的那行；
    单元格留空视为「不修改该字段」，非法值只记一条错误、不影响其它行入库。
    """
    rows = list(ws.iter_rows(values_only=True))
    index = _sheet_alias_index(sheet)
    header_row = -1
    col_map: dict[int, str] = {}
    best = 0
    for i, row in enumerate(rows[:8]):
        found: dict[int, str] = {}
        for j, cell in enumerate(row):
            field = index.get(_norm_header(cell))
            if field and field not in found.values():
                found[j] = field
        if len(found) > best:
            best, header_row, col_map = len(found), i, found
    if header_row < 0 or not col_map:
        return []

    missing_cols = [c.header for c in sheet.cols if c.required and c.field not in col_map.values()]
    if missing_cols:
        errors.append(
            f"「{sheet.title}」缺少必填列：{'、'.join(missing_cols)}，该页已跳过"
        )
        return []

    out: list[tuple[int, dict[str, Any]]] = []
    for r in range(header_row + 1, len(rows)):
        row = rows[r]
        cells: dict[str, Any] = {}
        for j, field in col_map.items():
            if j < len(row):
                cells[field] = row[j]
        if all(v is None or (isinstance(v, str) and not v.strip()) for v in cells.values()):
            continue
        data: dict[str, Any] = {}
        for col in sheet.cols:
            if col.field not in cells:
                continue
            raw = cells[col.field]
            if col.kind == "str":
                value: Any = str(raw).strip() if raw is not None else ""
                value = value or None
            else:
                try:
                    value = _COERCERS[col.kind](raw)
                except (TypeError, ValueError):
                    value = None
            if value is None:
                if raw is not None and str(raw).strip() and col.kind != "str":
                    errors.append(
                        f"「{sheet.title}」第 {r + 1} 行「{col.header}」的值「{raw}」无法识别，已忽略该单元格"
                    )
                continue
            data[col.field] = value
        missing = [c.header for c in sheet.cols if c.required and data.get(c.field) is None]
        if missing:
            errors.append(
                f"「{sheet.title}」第 {r + 1} 行缺少必填项：{'、'.join(missing)}，已跳过该行"
            )
            continue
        # 年份 / 月份这类范围错误也在解析阶段拦下：否则「先解析、后写入」会让
        # 错误列表的顺序和表格行号对不上，用户按行号找过去会找错行
        bad_year = next(
            (
                c
                for c in sheet.cols
                if c.field in ("year", "vintage_year", "issue_year")
                and data.get(c.field) is not None
                and int(data[c.field]) <= 0
            ),
            None,
        )
        if bad_year is not None:
            errors.append(f"「{sheet.title}」第 {r + 1} 行：「{bad_year.header}」不是有效年份，已跳过该行")
            continue
        if sheet.key == "emissions_month":
            month = int(data.get("month") or 0)
            if not 1 <= month <= 12:
                errors.append(f"「{sheet.title}」第 {r + 1} 行：月份必须在 1-12 之间（当前 {month}），已跳过该行")
                continue
        out.append((r + 1, data))
    return out


def _apply_emission_month(
    store: dict, enterprise_id: str, year: int, month: int, values: dict
) -> dict:
    """把某月指标并进该年度明细并重算年度值（不落盘）。

    单独拎出来是为了让「界面单月上报」和「台账导入」走同一段逻辑：
    导入 12 个月与逐月手工填报必须产生完全一样的存储结构。
    """
    ent = _find_enterprise(store, enterprise_id)
    if ent is None:
        raise LookupError("enterprise not found")
    row = _find_emission_row(ent, int(year))
    if not row:
        row = {"id": _uuid(), "year": int(year)}
        ent.setdefault("emissions", []).append(row)

    _freeze_legacy_annual(row)
    months = _normalize_months(row.get("monthly_detail"))
    cell = dict(months.get(month) or {})
    for f in EMISSION_METRICS:
        if values.get(f) is None:
            continue
        try:
            cell[f] = float(values[f])
        except (TypeError, ValueError):
            continue
    if not cell:
        raise ValueError("no metric provided")
    months[month] = cell
    row["monthly_detail"] = _emission_months_payload(months)
    _recompute_emission_year(row)
    return row


def _import_emission_months(
    user_id: str, enterprise_id: str, rows: list[tuple[int, dict[str, Any]]], errors: list[str]
) -> int:
    """月度明细一次性写进同一个 store、只落盘一次（几十行逐行 save 太慢）。"""
    if not rows:
        return 0
    store = _load_store()
    done = 0
    for lineno, data in rows:
        year = int(data["year"])
        month = int(data["month"])
        if not year or not (1 <= month <= 12):
            errors.append(
                f"「排放月度」第 {lineno} 行：年份/月份不合法（{year} / {month}），已跳过"
            )
            continue
        try:
            _apply_emission_month(store, enterprise_id, year, month, data)
            done += 1
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"「排放月度」第 {lineno} 行写入失败：{exc}")
    if done:
        _save_store(store)
    return done


def _import_emission_years(
    user_id: str, enterprise_id: str, rows: list[tuple[int, dict[str, Any]]], errors: list[str]
) -> int:
    """年度值走 upsert_emission_year：它会自动判断「与月度合计一致」→ 不写核定覆盖。"""
    done = 0
    for lineno, data in rows:
        if not int(data.get("year") or 0):
            errors.append(f"「排放年度」第 {lineno} 行：年份不能为空，已跳过")
            continue
        try:
            upsert_emission_year(None, user_id, enterprise_id, data)
            done += 1
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"「排放年度」第 {lineno} 行写入失败：{exc}")
    return done


def _import_cross_checks(parsed: dict[str, list[tuple[int, dict[str, Any]]]]) -> list[str]:
    """导入后的一致性提醒：年度值与月度合计对不上、只有年度值没有月度明细。

    这两条正是"台账改版后对不齐"的典型症状，导入时直接说明比让用户去报告里找强。
    """
    notes: list[str] = []
    months_sum: dict[int, float] = {}
    months_count: dict[int, int] = {}
    for _lineno, data in parsed.get("emissions_month") or []:
        year = int(data.get("year") or 0)
        months_count[year] = months_count.get(year, 0) + 1
        if data.get("verified_total") is not None:
            months_sum[year] = months_sum.get(year, 0.0) + float(data["verified_total"])

    only_annual: list[int] = []
    for _lineno, data in parsed.get("emissions") or []:
        year = int(data.get("year") or 0)
        annual = data.get("verified_total")
        if year not in months_count:
            only_annual.append(year)
            continue
        total = months_sum.get(year)
        if annual is None or total is None:
            continue
        if abs(float(annual) - total) > 0.01:
            notes.append(
                f"{year} 年：年度值 {float(annual):g} 与月度合计 {total:g} 万吨不一致，"
                "已按年度值（核定口径）核算；若要以月度为准，请把年度值改成与合计一致或留空。"
            )
    if only_annual:
        years = "、".join(str(y) for y in sorted(set(only_annual)))
        notes.append(
            f"{years} 年只填了年度值、没有月度明细：核算按年度口径进行，"
            "报告中的逐月构成会留空，建议把已上报的月份补进「排放月度」页。"
        )
    return notes


def build_import_template_bytes(enterprise_name: str = "") -> bytes:
    """生成与当前台账字段一一对应的导入模板。

    只放表头和「说明」页，不放示例数据行 —— 示例行导入后会变成真实台账记录，
    这正是旧模板最容易"和真实数据对不齐"的地方（示例 2024 年那行会被当成数据入库）。
    示例值统一放进「说明」页的字段清单里。
    """
    if Workbook is None:
        raise RuntimeError("openpyxl not installed")
    wb = Workbook()
    guide = wb.active
    guide.title = "说明"
    for sheet in _IMPORT_SHEETS:
        ws = wb.create_sheet(sheet.title)
        ws.append([c.header + ("*" if c.required else "") for c in sheet.cols])
        if Font is not None:
            fill = PatternFill("solid", fgColor="E8EFF7")
            for cell in ws[1]:
                cell.font = Font(bold=True, color="1F3A5F")
                cell.fill = fill
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for j, col in enumerate(sheet.cols, start=1):
            ws.column_dimensions[_col_letter(j)].width = max(12, min(32, len(col.header) * 2 + 4))
        ws.freeze_panes = "A2"
    _write_template_guide(guide, enterprise_name)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _write_template_guide(ws: Any, enterprise_name: str) -> None:
    lines: list[list[Any]] = [
        ["碳资产管理 · 排放台账导入模板", ""],
        ["适用企业", enterprise_name or "（未指定）"],
        ["生成时间", datetime.now().strftime("%Y-%m-%d %H:%M")],
        ["", ""],
        ["填写前请先看这几条", ""],
        ["1", "只填数据行，不要改表头文字；列顺序可以调整，模板以外的多余列会被忽略。"],
        ["2", "重量统一「万吨」；净购入电量按表头括号里的单位填（MWh，不是万吨）。"],
        ["3", "单元格留空 = 不修改该字段（不会清零）；确实要清零请填 0。要删除记录请回台账页点「删」。"],
        ["4", "导入按业务键合并，同一份表重复导入不会产生重复记录：月度按「年份 + 月份」、年度按「年份」。"],
        ["5", "排放以「排放月度」为主口径：填满 12 个月后年度值 = 12 个月合计；只有「排放年度」页的年度值与合计不一致时，才按年度核定值核算（界面显示「核定」）。"],
        ["6", "只填年度值也能导入，但报告里的逐月构成会留空——建议把已上报的月份填进「排放月度」页。"],
        ["7", "带 * 的表头是必填项。本「说明」页不会被导入。"],
        ["8", "本模板不含 CEA 配额、CCER、绿电 / 绿证——这几块仍在对应台账页录入。"],
        ["", ""],
        ["数据页", "表头", "单位", "必填", "填写说明", "示例值"],
    ]
    for line in lines:
        ws.append(line)
    head_index = len(lines)  # 字段清单表头所在行（1 起算）
    next_row = head_index + 1
    group_rows: list[int] = []
    for sheet in _IMPORT_SHEETS:
        # 每个数据页先给一行分组标题 + 该页的合并口径说明，下面再逐字段列
        ws.append([sheet.title, sheet.note])
        group_rows.append(next_row)
        next_row += 1
        for col in sheet.cols:
            ws.append(
                [
                    sheet.title,
                    col.header,
                    col.unit or "—",
                    "是" if col.required else "否",
                    col.note,
                    col.example,
                ]
            )
            next_row += 1
    if Font is not None:
        ws["A1"].font = Font(bold=True, size=14)
        ws["A5"].font = Font(bold=True, color="1F3A5F")
        fill = PatternFill("solid", fgColor="E8EFF7")
        for cell in ws[head_index]:
            cell.font = Font(bold=True, color="1F3A5F")
            cell.fill = fill
            cell.alignment = Alignment(horizontal="center")
        for r in group_rows:
            ws.cell(row=r, column=1).font = Font(bold=True, color="1F3A5F")
            ws.cell(row=r, column=2).font = Font(bold=True, color="1F3A5F")
    for j, width in enumerate((16, 22, 10, 8, 72, 16), start=1):
        ws.column_dimensions[_col_letter(j)].width = width


def import_enterprise_excel(
    db: Any = None,
    user_id: str = DEFAULT_USER_ID,
    enterprise_id: str = "",
    content: bytes = b"",
) -> dict[str, Any]:
    """把填好的模板合并进企业台账。

    返回 {"counts": {...}, "warnings": [...], "errors": [...], "total": n}。
    只有整份文件读不出来才抛异常；单行问题记进 errors、不影响其它行入库 ——
    台账一次几十行，因为一格写错就整份失败最让人崩溃。
    """
    if load_workbook is None:
        raise RuntimeError("openpyxl not installed")
    if not get_enterprise(db, user_id, enterprise_id):
        raise LookupError("enterprise not found")
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception as exc:  # noqa: BLE001 - 用户上传的任意文件都可能坏
        raise ValueError("文件无法解析，请确认是本系统下载的 .xlsx 台账模板") from exc

    errors: list[str] = []
    parsed: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for sheet in _IMPORT_SHEETS:
        ws = _find_import_sheet(wb, sheet)
        parsed[sheet.key] = _read_import_sheet(ws, sheet, errors) if ws is not None else []

    # 一行都没读出来：有具体错误就照常返回报告（前端要把每一行的问题列全），
    # 完全没有错误才说明是空模板 / 页名不对，这时直接报错更好定位
    if not any(parsed.values()) and not errors:
        titles = "」「".join(s.title for s in _IMPORT_SHEETS)
        raise ValueError(f"没有读到台账数据行，请把数据填在「{titles}」这些页里")

    counts = {
        # 月度先写：随后写年度值时若与月度合计一致，会自动解除「核定」，
        # 年度值不会永远压着月度合计（这正是改版后口径对不齐的主因）
        "emissions_month": _import_emission_months(user_id, enterprise_id, parsed["emissions_month"], errors),
        "emissions": _import_emission_years(user_id, enterprise_id, parsed["emissions"], errors),
    }
    return {
        "counts": counts,
        "warnings": _import_cross_checks(parsed),
        "errors": errors,
        "total": sum(counts.values()),
    }


def enterprise_to_dict(e: Any) -> dict:
    return {
        "id": str(e.get("id")),
        "name": e.get("name"),
        "uscc": e.get("uscc"),
        "industry": e.get("industry"),
        "market_start_year": e.get("market_start_year"),
        "compliance_cycle": e.get("compliance_cycle"),
        "risk_profile": e.get("risk_profile"),
        "annual_budget_cap": e.get("annual_budget_cap"),
        "single_trade_limit": e.get("single_trade_limit"),
        "enterprise_attrs": e.get("enterprise_attrs") or {},
        "created_at": e.get("created_at"),
        "updated_at": e.get("updated_at"),
    }


def run_to_dict(r: Any) -> dict:
    return {
        "id": str(r.get("id")),
        "enterprise_id": str(r.get("enterprise_id")),
        "compliance_year": r.get("compliance_year"),
        "accounting_snapshot": r.get("accounting_snapshot"),
        "market_tags": r.get("market_tags"),
        "plans": r.get("plans"),
        "status": r.get("status"),
        "report_md": r.get("report_md"),
        "created_at": r.get("created_at"),
    }


def alert_to_dict(a: Any) -> dict:
    return {
        "id": str(a.get("id")),
        "enterprise_id": str(a.get("enterprise_id")),
        "level": a.get("level"),
        "alert_type": a.get("alert_type"),
        "message": a.get("message"),
        "due_at": a.get("due_at"),
        "acked": a.get("acked"),
        "created_at": a.get("created_at"),
    }
