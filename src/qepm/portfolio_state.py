"""Shared validation for a coherent, long-only portfolio state.

These checks sit at receiving boundaries rather than in the frozen contract
dataclasses: constructing a fixture remains lightweight, while every module
that calculates or approves portfolio consequences fails closed on malformed
inputs.
"""

from __future__ import annotations

from math import isfinite
from numbers import Real

import pandas as pd

from qepm.contracts import (
    Direction,
    ExposureTarget,
    Holdings,
    PhaseGateError,
    PortfolioPolicy,
    Snapshot,
    TradeOrder,
)


def _finite_real(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and isfinite(float(value))


def _validate_figi_index(index: pd.Index, owner: str) -> None:
    if not index.is_unique:
        raise PhaseGateError(f"{owner} must have a unique FIGI index")
    for figi in index:
        if not isinstance(figi, str) or not figi.strip():
            raise PhaseGateError(f"{owner} has a missing or invalid FIGI index value")


def validate_snapshot_identities(snapshot: Snapshot) -> None:
    """Ensure security lookups cannot silently return multiple issuer rows."""
    _validate_figi_index(snapshot.securities.index, "Snapshot.securities")


def validate_long_only_holdings(holdings: Holdings) -> None:
    """Require one finite, nonnegative dollar value per FIGI."""
    positions = holdings.positions
    _validate_figi_index(positions.index, "Holdings.positions")
    if "dollar_value" not in positions.columns:
        raise PhaseGateError("Holdings.positions requires a dollar_value column")
    for figi, value in positions["dollar_value"].items():
        if not _finite_real(value) or float(value) < 0:
            raise PhaseGateError(f"Holdings.positions has a non-finite or negative dollar_value for {figi}")


def validate_portfolio_policy(policy: PortfolioPolicy) -> None:
    """Validate numeric controls before they determine portfolio eligibility."""
    finite_nonnegative = (
        "max_single_name_weight",
        "min_median_daily_dollar_volume",
        "max_trade_volume_fraction",
        "beta_warning",
        "beta_ceiling",
        "beta_target_minimum",
        "beta_target_maximum",
        "factor_target_score",
        "factor_watch_score",
        "factor_priority_score",
        "core_sleeve_minimum",
        "core_sleeve_maximum",
        "experimental_sleeve_minimum",
        "experimental_sleeve_maximum",
        "normal_cash_maximum",
        "material_price_move_fraction",
    )
    if not _finite_real(policy.portfolio_nav) or float(policy.portfolio_nav) <= 0:
        raise PhaseGateError("PortfolioPolicy.portfolio_nav must be finite and positive")
    for name in finite_nonnegative:
        value = getattr(policy, name)
        if not _finite_real(value) or float(value) < 0:
            raise PhaseGateError(f"PortfolioPolicy.{name} must be finite and nonnegative")
    if not isinstance(policy.max_research_briefs, int) or isinstance(policy.max_research_briefs, bool) or policy.max_research_briefs < 0:
        raise PhaseGateError("PortfolioPolicy.max_research_briefs must be a nonnegative integer")

    fractions = (
        "max_single_name_weight",
        "max_trade_volume_fraction",
        "core_sleeve_minimum",
        "core_sleeve_maximum",
        "experimental_sleeve_minimum",
        "experimental_sleeve_maximum",
        "normal_cash_maximum",
    )
    if any(float(getattr(policy, name)) > 1 for name in fractions):
        raise PhaseGateError("PortfolioPolicy weight and fraction controls must not exceed 1")
    if policy.material_price_move_fraction <= 0:
        raise PhaseGateError("PortfolioPolicy.material_price_move_fraction must be finite and positive")
    if not (
        policy.beta_target_minimum <= policy.beta_target_maximum <= policy.beta_warning <= policy.beta_ceiling
    ):
        raise PhaseGateError("PortfolioPolicy beta thresholds must satisfy target_minimum <= target_maximum <= warning <= ceiling")
    if not (policy.factor_priority_score <= policy.factor_watch_score <= policy.factor_target_score <= 100):
        raise PhaseGateError("PortfolioPolicy factor thresholds must satisfy priority <= watch <= target <= 100")
    if policy.core_sleeve_minimum > policy.core_sleeve_maximum:
        raise PhaseGateError("PortfolioPolicy core sleeve minimum cannot exceed maximum")
    if policy.experimental_sleeve_minimum > policy.experimental_sleeve_maximum:
        raise PhaseGateError("PortfolioPolicy experimental sleeve minimum cannot exceed maximum")


def validate_exposure_target(target: ExposureTarget) -> None:
    if not isinstance(target.direction, Direction):
        raise PhaseGateError("ExposureTarget.direction must be a Direction")
    if not _finite_real(target.dollar_amount):
        label = "NaN" if isinstance(target.dollar_amount, Real) and pd.isna(target.dollar_amount) else "non-finite"
        raise PhaseGateError(f"ExposureTarget.dollar_amount is {label}")
    if float(target.dollar_amount) <= 0:
        raise PhaseGateError("ExposureTarget.dollar_amount is non-positive")


def validate_trade_order(order: TradeOrder) -> None:
    if not isinstance(order.direction, Direction):
        raise PhaseGateError("TradeOrder.direction must be a Direction")
    if not _finite_real(order.dollar_amount) or float(order.dollar_amount) <= 0:
        raise PhaseGateError("TradeOrder.dollar_amount must be finite and positive")
