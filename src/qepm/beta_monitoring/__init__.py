"""Portfolio beta target and long-window context for weekly SIC reporting."""

from __future__ import annotations

from qepm.contracts import BetaStatus, Holdings, PortfolioPolicy, Snapshot
from qepm.portfolio_state import (
    validate_long_only_holdings,
    validate_portfolio_policy,
    validate_snapshot_identities,
)

__all__ = ["portfolio_beta_status"]


def portfolio_beta_status(holdings: Holdings, snapshot: Snapshot, policy: PortfolioPolicy) -> BetaStatus:
    """Report 90-day operational beta plus 252-day context without forcing a trade."""
    validate_long_only_holdings(holdings)
    validate_snapshot_identities(snapshot)
    validate_portfolio_policy(policy)
    if holdings.as_of != snapshot.as_of:
        raise ValueError("portfolio beta monitoring requires holdings and snapshot from the same as_of date")
    positions = holdings.positions["dollar_value"]
    operational = snapshot.securities.get(policy.beta_column)
    if operational is None or operational.reindex(positions.index).isna().any():
        return BetaStatus(None, None, "data-missing", False)
    beta = float((positions / policy.portfolio_nav * operational.reindex(positions.index)).sum())
    context = snapshot.securities.get(policy.beta_context_column)
    context_beta = None if context is None or context.reindex(positions.index).isna().any() else float(
        (positions / policy.portfolio_nav * context.reindex(positions.index)).sum()
    )
    status = (
        "below-target" if beta < policy.beta_target_minimum else "target" if beta <= policy.beta_target_maximum
        else "above-target" if beta < policy.beta_warning else "warning" if beta < policy.beta_ceiling else "ceiling-breach"
    )
    requires_exception_review = beta >= policy.beta_ceiling or (
        context_beta is not None and beta >= policy.beta_warning and context_beta >= policy.beta_warning
    )
    return BetaStatus(beta, context_beta, status, requires_exception_review)
