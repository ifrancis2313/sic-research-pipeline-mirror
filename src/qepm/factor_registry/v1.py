"""Approved SIC V1 factor definitions.

These definitions produce 0–100 percentile scores suitable for the weekly
portfolio snapshot. Value and Quality are compared only with sector peers;
Momentum and Size are compared with the full Russell 1000 factor universe.
Market beta is a portfolio-risk control and therefore lives in the Portfolio
Fit Check policy rather than this selection-oriented registry.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from qepm.contracts import FactorDefinition, PhaseGateError, Snapshot
from qepm.factor_registry.registry import FactorRegistry

V1_FACTOR_NAMES = frozenset({"value", "quality", "momentum", "size"})
_V1_NUMERIC_FIELDS = (
    "free_cash_flow_ttm",
    "market_cap",
    "revenue_ttm",
    "cost_of_revenue_ttm",
    "total_assets",
    "momentum_12_1",
)


def validate_v1_numeric_inputs(snapshot: Snapshot) -> None:
    """Reject supplied V1 factor inputs that cannot safely enter its formulas.

    Missing observations are retained as N/A for the fundamental review path.
    Negative free cash flow is also valid economic information. Market cap and
    total assets are denominators (and market cap is logged for Size), so their
    supplied values must be strictly positive.
    """
    for field in _V1_NUMERIC_FIELDS:
        supplied = snapshot.securities[field]
        numeric = pd.to_numeric(supplied, errors="coerce")
        non_numeric = supplied.notna() & numeric.isna()
        if non_numeric.any():
            figis = snapshot.securities.index[non_numeric].tolist()
            raise PhaseGateError(f"V1 factor input '{field}' must be numeric for {figis[:5]}")

        non_finite = numeric.notna() & ~np.isfinite(numeric)
        if non_finite.any():
            figis = snapshot.securities.index[non_finite].tolist()
            raise PhaseGateError(f"V1 factor input '{field}' has non-finite values for {figis[:5]}")

        if field in {"market_cap", "total_assets"}:
            invalid_denominator = numeric.notna() & (numeric <= 0)
            if invalid_denominator.any():
                figis = snapshot.securities.index[invalid_denominator].tolist()
                raise PhaseGateError(
                    f"V1 factor input '{field}' must be strictly positive for {figis[:5]}"
                )


def _sector_percentile(snapshot: Snapshot, values: pd.Series) -> pd.Series:
    sectors = snapshot.securities["sector"]
    peer_counts = values.notna().groupby(sectors).transform("sum")
    # A one-security sector has no cross-sectional information.  Preserve it
    # as N/A instead of presenting a mechanically perfect 100 score.
    return (values.groupby(sectors).rank(pct=True) * 100.0).where(peer_counts >= 2)


def _universe_percentile(values: pd.Series) -> pd.Series:
    return values.rank(pct=True) * 100.0


def value_score(snapshot: Snapshot) -> pd.Series:
    values = snapshot.securities["free_cash_flow_ttm"] / snapshot.securities["market_cap"]
    return _sector_percentile(snapshot, values)


def quality_score(snapshot: Snapshot) -> pd.Series:
    gross_profitability_to_assets = (
        snapshot.securities["revenue_ttm"] - snapshot.securities["cost_of_revenue_ttm"]
    ) / snapshot.securities["total_assets"]
    return _sector_percentile(snapshot, gross_profitability_to_assets)


def momentum_score(snapshot: Snapshot) -> pd.Series:
    return _universe_percentile(snapshot.securities["momentum_12_1"])


def size_score(snapshot: Snapshot) -> pd.Series:
    return _universe_percentile(snapshot.securities["market_cap"].map(math.log))


def v1_factor_registry() -> FactorRegistry:
    """Return the approved V1 registry; Size is visible but excluded from the blend."""
    registry = FactorRegistry()
    registry.register(
        FactorDefinition(
            name="value",
            formula=value_score,
            weight=1.0,
            description="Sector-relative trailing-twelve-month free-cash-flow yield.",
            required_fields=("sector", "free_cash_flow_ttm", "market_cap"),
        )
    )
    registry.register(
        FactorDefinition(
            name="quality",
            formula=quality_score,
            weight=1.0,
            description="Sector-relative trailing-twelve-month gross profitability to assets.",
            required_fields=("sector", "revenue_ttm", "cost_of_revenue_ttm", "total_assets"),
        )
    )
    registry.register(
        FactorDefinition(
            name="momentum",
            formula=momentum_score,
            weight=1.0,
            description="Full-universe 12-minus-1 price momentum percentile.",
            required_fields=("momentum_12_1",),
        )
    )
    registry.register(
        FactorDefinition(
            name="size",
            formula=size_score,
            weight=0.0,
            description="Full-universe log-market-cap monitor; not a directional V1 objective.",
            required_fields=("market_cap",),
        )
    )
    return registry
