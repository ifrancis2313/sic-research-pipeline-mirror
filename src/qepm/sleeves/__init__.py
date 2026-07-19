"""Starting transition sleeve map (sample data) and allocation summaries."""

from __future__ import annotations

from qepm.contracts import Holdings, PortfolioPolicy
from qepm.portfolio_state import validate_long_only_holdings, validate_portfolio_policy

__all__ = ["STARTING_SLEEVE_BY_FIGI", "STARTING_SLEEVE_BY_TICKER", "cash_posture", "sleeve_status", "sleeve_weights"]

STARTING_SLEEVE_BY_TICKER: dict[str, str] = {
    "SAMPLE-CORE-1": "core",
    "SAMPLE-CORE-2": "core",
    "SAMPLE-ACTIVE-1": "active",
    "SAMPLE-ACTIVE-2": "active",
    "SAMPLE-ACTIVE-3": "active",
    "SAMPLE-ACTIVE-4": "active",
    "SAMPLE-ACTIVE-5": "active",
    "SAMPLE-ACTIVE-6": "active",
    "SAMPLE-ACTIVE-7": "active",
    "SAMPLE-ACTIVE-8": "active",
    "SAMPLE-EXPERIMENTAL-1": "experimental",
    "SAMPLE-EXPERIMENTAL-2": "experimental",
}

STARTING_SLEEVE_BY_FIGI: dict[str, str] = {
    "BBG-FIXTURE-013": "core",
    "BBG-FIXTURE-002": "core",
    "BBG-FIXTURE-011": "active",
    "BBG-FIXTURE-009": "active",
    "BBG-FIXTURE-020": "active",
    "BBG-FIXTURE-004": "active",
    "BBG-FIXTURE-006": "active",
    "BBG-FIXTURE-015": "active",
    "BBG-FIXTURE-008": "active",
    "BBG-FIXTURE-019": "active",
    "BBG-FIXTURE-016": "experimental",
    "BBG-FIXTURE-010": "experimental",
}


def sleeve_weights(holdings: Holdings, policy: PortfolioPolicy, sleeve_by_identifier: dict[str, str]) -> dict[str, float]:
    """Summarize FIGI-keyed sleeves while keeping unmapped inherited positions visible."""
    validate_long_only_holdings(holdings)
    validate_portfolio_policy(policy)
    result = {"core": 0.0, "active": 0.0, "experimental": 0.0, "unassigned": 0.0}
    for identifier, value in holdings.positions["dollar_value"].items():
        sleeve = sleeve_by_identifier.get(str(identifier), "unassigned")
        result[sleeve] = result.get(sleeve, 0.0) + float(value) / policy.portfolio_nav
    return result


def cash_posture(holdings: Holdings, policy: PortfolioPolicy) -> dict[str, float | bool]:
    """Flag excess operating cash without prescribing an investment action."""
    validate_long_only_holdings(holdings)
    validate_portfolio_policy(policy)
    cash_weight = round(max(0.0, 1.0 - float(holdings.positions["dollar_value"].sum()) / policy.portfolio_nav), 10)
    return {"cash_weight": cash_weight, "flagged": cash_weight > policy.normal_cash_maximum}


def sleeve_status(weights: dict[str, float], policy: PortfolioPolicy) -> dict[str, str]:
    """Describe long-run sleeve gaps for research planning, never as forced rebalances."""
    validate_portfolio_policy(policy)
    status: dict[str, str] = {}
    for sleeve, minimum, maximum in (
        ("core", policy.core_sleeve_minimum, policy.core_sleeve_maximum),
        ("experimental", policy.experimental_sleeve_minimum, policy.experimental_sleeve_maximum),
    ):
        value = weights.get(sleeve, 0.0)
        status[sleeve] = "underweight" if value < minimum else "overweight" if value > maximum else "within-band"
    status["active"] = "transition-build" if weights.get("active", 0.0) < 0.60 else "at-or-above-long-run-intent"
    return status
