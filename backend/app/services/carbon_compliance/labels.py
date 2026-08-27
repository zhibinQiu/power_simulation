"""履约报告展示用中文标签（除 CEA/CCER 等专有名词外避免英文）。"""

from __future__ import annotations

from typing import Any

from app.services.carbon_compliance.defaults import INDUSTRY_LABELS, RISK_PROFILE_LABELS

PRICE_BAND_LABELS = {
    "low": "低位",
    "mid": "中位",
    "high": "高位",
    "unknown": "未知",
}

TIME_WINDOW_LABELS = {
    "early": "年初窗口",
    "mid": "年中窗口",
    "late": "年末窗口",
}

ACTION_TAG_LABELS = {
    "buy": "建议采购",
    "sell": "建议出售",
    "hold": "观望持有",
}

ALERT_TYPE_LABELS = {
    "clearance_countdown": "清缴倒计时",
    "price_spike": "价格偏高",
    "price_low": "价格偏低",
    "ccer_over_cap": "CCER 超限",
    "carry_forward_excess": "结转超额",
}

ALERT_LEVEL_LABELS = {
    "critical": "紧急",
    "warning": "关注",
    "info": "提示",
}

PLAN_ACTION_LABELS = {
    "buy_cea": "买入 CEA",
    "sell_cea": "卖出 CEA",
    "use_ccer": "使用自有 CCER",
    "buy_ccer": "外购 CCER",
    "buy_green_power": "采购绿电",
    "buy_green_cert": "采购绿证",
}

FORECAST_METHOD_LABELS = {
    "rule": "规则模型",
    "ets": "指数平滑",
    "sarimax": "回归季节模型",
    "prophet": "先知季节模型",
}

CCER_SUPPLY_LABELS = {
    "loose": "偏宽松",
    "tight": "偏紧张",
    "unknown": "未知",
}


def zh(mapping: dict[str, str], key: Any, default: str | None = None) -> str:
    k = str(key or "").strip()
    if not k:
        return default or "—"
    return mapping.get(k, default if default is not None else k)


def industry_zh(industry: Any) -> str:
    return zh(INDUSTRY_LABELS, industry, str(industry or "—") or "—")


def risk_profile_zh(profile: Any) -> str:
    return zh(RISK_PROFILE_LABELS, profile, str(profile or "—") or "—")


def bool_zh(v: Any) -> str:
    if v is True:
        return "是"
    if v is False:
        return "否"
    return "—"


def plan_action_zh(action: Any) -> str:
    return zh(PLAN_ACTION_LABELS, action, str(action or "—") or "—")
