"""Local-first V1 market-data readiness contract; no vendor calls live here."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from qepm.contracts import PhaseGateError, Snapshot

__all__ = [
    "PolygonConfiguration",
    "v1_snapshot_missing_fields",
    "validate_v1_snapshot_ready_for_live_use",
]

_V1_SECURITY_FIELDS = (
    "sector", "market_cap", "free_cash_flow_ttm", "revenue_ttm", "cost_of_revenue_ttm", "total_assets",
    "momentum_12_1", "market_beta_90d", "market_beta_252d", "median_daily_dollar_volume",
    "is_russell_1000", "is_us_listed", "instrument_type", "is_core_market_etf", "price",
    "has_price_history",
)
_V1_AVAILABILITY_FIELDS = (
    "momentum_12_1_asof",
    "market_beta_90d_asof",
    "market_beta_252d_asof",
)


@dataclass(frozen=True)
class PolygonConfiguration:
    """Credential location only; live retrieval is deliberately not implemented."""

    api_key_env_var: str = "POLYGON_API_KEY"


def v1_snapshot_missing_fields(snapshot: Snapshot) -> tuple[str, ...]:
    """Return required V1 live columns absent from a local or future vendor snapshot.

    The score fixtures intentionally remain lightweight.  Production callers
    must use :func:`validate_v1_snapshot_ready_for_live_use` before a weekly
    run; it requires availability stamps for rolling market-derived fields.
    """
    required = _V1_SECURITY_FIELDS + _V1_AVAILABILITY_FIELDS
    return tuple(field for field in required if field not in snapshot.securities.columns)


def validate_v1_snapshot_ready_for_live_use(snapshot: Snapshot) -> None:
    """Enforce the V1 live-data readiness and availability-date contract.

    Availability stamps are distinct from observation dates: they document
    when each rolling signal was known.  Missing stamps or future stamps make
    a live snapshot ineligible, but do not turn unit-test fixtures into fake
    live feeds.
    """
    missing = v1_snapshot_missing_fields(snapshot)
    if missing:
        raise PhaseGateError(f"V1 live snapshot is missing required fields: {list(missing)}")

    as_of = pd.Timestamp(snapshot.as_of)
    for field in _V1_AVAILABILITY_FIELDS:
        values = pd.to_datetime(snapshot.securities[field], errors="coerce")
        invalid = values.isna()
        if invalid.any():
            figis = snapshot.securities.index[invalid].tolist()
            raise PhaseGateError(f"V1 availability field '{field}' must contain dates for {figis[:5]}")
        future = values.notna() & (values > as_of)
        if future.any():
            figis = snapshot.securities.index[future].tolist()
            raise PhaseGateError(
                f"leakage: V1 availability field '{field}' is after snapshot.as_of for {figis[:5]}"
            )
