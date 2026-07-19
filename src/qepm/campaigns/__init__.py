"""Binding recheck of the exact approved subset of a research campaign."""

from __future__ import annotations

from datetime import date

from qepm.contracts import (
    CampaignFitResult,
    CampaignLeg,
    FactorScoreMatrix,
    Holdings,
    PortfolioPolicy,
    Snapshot,
)
from qepm.portfolio_fit import evaluate_portfolio_fit

__all__ = ["evaluate_approved_subset"]


def evaluate_approved_subset(
    legs: tuple[CampaignLeg, ...], holdings: Holdings, scores: FactorScoreMatrix,
    snapshot: Snapshot, evaluation_date: date, policy: PortfolioPolicy,
) -> CampaignFitResult:
    """Recheck approved legs cumulatively, so partial approval cannot bypass portfolio limits."""
    working_positions = holdings.positions.copy()
    results = []
    for leg in legs:
        current = Holdings(holdings.as_of, working_positions)
        result = evaluate_portfolio_fit(leg.pitch, leg.brief.target, leg.brief, current, scores, snapshot, evaluation_date, policy)
        results.append(result)
        if result.passed:
            existing = float(working_positions.loc[leg.pitch.figi, "dollar_value"]) if leg.pitch.figi in working_positions.index else 0.0
            delta = leg.brief.target.dollar_amount if leg.brief.target.direction.value == "buy" else -leg.brief.target.dollar_amount
            working_positions.loc[leg.pitch.figi, "dollar_value"] = existing + delta
    return CampaignFitResult(tuple(leg.pitch.id for leg in legs), tuple(results))
