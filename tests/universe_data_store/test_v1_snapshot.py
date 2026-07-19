from datetime import date

import pandas as pd
import pytest

from qepm.contracts import PhaseGateError, Snapshot
from qepm.universe_data_store.v1_snapshot import (
    PolygonConfiguration,
    v1_snapshot_missing_fields,
    validate_v1_snapshot_ready_for_live_use,
)


def test_v1_snapshot_contract_exposes_missing_vendor_fields_without_network_access():
    snapshot = Snapshot(date(2026, 7, 17), pd.DataFrame({"sector": []}), pd.DataFrame())

    missing = v1_snapshot_missing_fields(snapshot)

    assert "market_beta_90d" in missing
    assert "momentum_12_1_asof" in missing
    assert "market_beta_90d_asof" in missing
    assert "market_beta_252d_asof" in missing
    assert "price" in missing
    assert "has_price_history" in missing
    assert PolygonConfiguration().api_key_env_var == "POLYGON_API_KEY"


def test_live_v1_readiness_requires_availability_dates_without_affecting_fixtures():
    as_of = date(2026, 7, 17)
    fields = {
        "sector": ["Technology"], "market_cap": [1.0], "free_cash_flow_ttm": [1.0],
        "revenue_ttm": [1.0], "cost_of_revenue_ttm": [1.0], "total_assets": [1.0],
        "momentum_12_1": [0.1], "market_beta_90d": [0.8], "market_beta_252d": [0.9],
        "median_daily_dollar_volume": [1.0], "is_russell_1000": [True], "is_us_listed": [True],
        "instrument_type": ["stock"], "is_core_market_etf": [False], "price": [10.0],
        "has_price_history": [True],
    }
    fixture = Snapshot(as_of, pd.DataFrame(fields, index=pd.Index(["F1"], name="figi")), pd.DataFrame())
    with pytest.raises(PhaseGateError, match="momentum_12_1_asof"):
        validate_v1_snapshot_ready_for_live_use(fixture)

    live = Snapshot(
        as_of,
        fixture.securities.assign(
            momentum_12_1_asof=[as_of], market_beta_90d_asof=[as_of], market_beta_252d_asof=[as_of]
        ),
        fixture.macro,
    )
    validate_v1_snapshot_ready_for_live_use(live)


def test_live_v1_readiness_rejects_future_availability_dates():
    as_of = date(2026, 7, 17)
    securities = pd.DataFrame(
        {field: [1.0] for field in (
            "market_cap", "free_cash_flow_ttm", "revenue_ttm", "cost_of_revenue_ttm", "total_assets",
            "momentum_12_1", "market_beta_90d", "market_beta_252d", "median_daily_dollar_volume", "price",
        )}, index=pd.Index(["F1"], name="figi")
    ).assign(
        sector=["Technology"], is_russell_1000=[True], is_us_listed=[True], instrument_type=["stock"],
        is_core_market_etf=[False], has_price_history=[True], momentum_12_1_asof=[as_of],
        market_beta_90d_asof=[as_of], market_beta_252d_asof=[date(2026, 7, 18)],
    )
    with pytest.raises(PhaseGateError, match="leakage"):
        validate_v1_snapshot_ready_for_live_use(Snapshot(as_of, securities, pd.DataFrame()))
