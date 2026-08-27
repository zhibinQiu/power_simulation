"""控排企业履约策略：平台默认配置与行业常量。"""

from __future__ import annotations

INDUSTRIES = ("power", "steel", "cement", "aluminum")

INDUSTRY_LABELS = {
    "power": "火电",
    "steel": "钢铁",
    "cement": "水泥",
    "aluminum": "电解铝",
}

RISK_PROFILES = ("conservative", "balanced", "aggressive")

RISK_PROFILE_LABELS = {
    "conservative": "保守",
    "balanced": "平衡",
    "aggressive": "进取",
}


def default_settings() -> dict:
    """platform_carbon_strategy_settings 单例默认 payload。"""
    return {
        "compliance": {
            "ccer_max_ratio": 0.05,
            "clearance_warn_days": [90, 30, 15],
            "price_low_percentile": 0.30,
            "price_mid_percentile": 0.70,
            "single_trade_cap_default": 0.0,
            "annual_position_cap_default": 100.0,  # 万吨
            "large_trade_split_threshold": 5.0,  # 万吨
            # CEA 结转：政策可能调整，默认 6/10
            "carry_forward_deadline_md": "06-10",
            # 基础结转额度（万吨）；0 表示策略侧用当年免费配额作基础
            "carry_base_qty": 0.0,
            "carry_net_sell_multiplier": 1.5,
        },
        "strategy_profiles": {
            "conservative": {
                "allow_stockpile": False,
                "allow_sell_surplus": False,
                "allow_buy_external_ccer": False,
            },
            "balanced": {
                "allow_stockpile": False,
                "allow_sell_surplus": True,
                "allow_buy_external_ccer": True,
            },
            "aggressive": {
                "allow_stockpile": True,
                "allow_sell_surplus": True,
                "allow_buy_external_ccer": True,
            },
        },
        # 交易渠道：公开侧无挂单，推荐默认优先线下撮合
        "channel": {
            "prefer_offline": True,
            # 假定线下成交价较公开日均/预测参考价更低的比例（仅用于成本估算）
            "offline_discount_vs_listed": 0.03,
        },
        "cost": {
            # 手续费 = 成交总额 × 单边费率；买入应付=总额+手续费，卖出实收=总额−手续费
            "listing_fee_rate": 0.0,  # 挂牌协议交易（单边），指导价参考 0.006
            "block_fee_rate": 0.0,  # 大宗协议转让（单边），指导价参考 0.005
            "trade_fee_rate": 0.0,  # 旧字段：未填挂牌/大宗时回退
            "tax_rate": 0.0,
            "grid_emission_factor": 0.5703,
            "overdue_penalty_per_t": 200.0,
            "holding_cost_annual_rate": 0.04,
        },
        "industry_params": {
            "power": {
                "quota_baseline": 0.0,
                "capacity_factor": 1.0,
                "free_quota_issue_month": 3,
                "carry_years": 1,
                "carry_cap_ratio": 1.0,
                "clearance_deadline_md": "12-31",
                "overdue_penalty_per_t": 200.0,
                "grid_emission_factor": 0.5703,
            },
            "steel": {
                "quota_baseline": 0.0,
                "capacity_factor": 1.0,
                "free_quota_issue_month": 3,
                "carry_years": 1,
                "carry_cap_ratio": 1.0,
                "clearance_deadline_md": "12-31",
                "overdue_penalty_per_t": 200.0,
                "grid_emission_factor": 0.5703,
            },
            "cement": {
                "quota_baseline": 0.0,
                "capacity_factor": 1.0,
                "free_quota_issue_month": 3,
                "carry_years": 1,
                "carry_cap_ratio": 1.0,
                "clearance_deadline_md": "12-31",
                "overdue_penalty_per_t": 200.0,
                "grid_emission_factor": 0.5703,
            },
            "aluminum": {
                "quota_baseline": 0.0,
                "capacity_factor": 1.0,
                "free_quota_issue_month": 3,
                "carry_years": 1,
                "carry_cap_ratio": 1.0,
                "clearance_deadline_md": "12-31",
                "overdue_penalty_per_t": 200.0,
                "grid_emission_factor": 0.5703,
            },
        },
        "integrations": {
            "market_sync_period": "day",
            "market_sync_enabled": True,
            "erp_api_url": "",
            "erp_api_key": "",
            "excel_import_enabled": True,
        },
    }


def deep_merge(base: dict, overlay: dict | None) -> dict:
    """递归合并配置，overlay 覆盖 base。"""
    if not overlay:
        return dict(base)
    out = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out
