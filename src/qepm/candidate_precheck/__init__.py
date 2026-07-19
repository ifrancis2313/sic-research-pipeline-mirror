"""Non-reserving candidate fit cards for SIC student research."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from qepm.contracts import (
    CandidateFitCard,
    CompetingPitch,
    FactorScoreMatrix,
    Holdings,
    PortfolioPolicy,
    ResearchBrief,
    Snapshot,
)
from qepm.portfolio_fit import evaluate_portfolio_fit

__all__ = ["create_candidate_fit_card"]


def create_candidate_fit_card(
    pitch: CompetingPitch,
    brief: ResearchBrief,
    holdings: Holdings,
    scores: FactorScoreMatrix,
    snapshot: Snapshot,
    evaluation_date: date,
    policy: PortfolioPolicy,
) -> CandidateFitCard:
    """Expose the current fit diagnostic without claiming the name or blocking research."""
    fit = evaluate_portfolio_fit(
        pitch, brief.target, replace(brief), holdings, scores, snapshot, evaluation_date, policy
    )
    completeness = "binding-data-missing" if any(note.startswith("missing-") for note in fit.hard_limit_violations) else (
        "factor-n/a" if any(value is None for value in fit.factor_fit.values()) else "complete"
    )
    current_weight = float(holdings.positions["dollar_value"].get(pitch.figi, 0.0)) / policy.portfolio_nav
    return CandidateFitCard(
        figi=pitch.figi,
        research_permitted=True,
        fit=fit,
        available_name_room=round(max(0.0, policy.max_single_name_weight - current_weight), 10),
        data_completeness=completeness,
    )
