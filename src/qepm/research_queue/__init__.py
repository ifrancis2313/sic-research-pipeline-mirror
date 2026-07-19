"""Weekly factor-need proposals for PM-controlled student research briefs."""

from __future__ import annotations

from qepm.contracts import Direction, FactorScoreMatrix, Holdings, PortfolioPolicy, ResearchNeed
from qepm.portfolio_state import validate_long_only_holdings, validate_portfolio_policy

__all__ = ["propose_weekly_research_queue"]


def _portfolio_factor_score(
    factor: str,
    scores: FactorScoreMatrix,
    holdings: Holdings,
    policy: PortfolioPolicy,
) -> float | None:
    positions = holdings.positions["dollar_value"]
    held_scores = scores.scores.reindex(positions.index)[factor]
    if held_scores.isna().any():
        return None
    return float((positions * held_scores).sum() / policy.portfolio_nav)


def _priority(score: float, policy: PortfolioPolicy) -> str | None:
    if score < policy.factor_priority_score:
        return "priority"
    if score < policy.factor_watch_score:
        return "watch"
    return None


def propose_weekly_research_queue(
    scores: FactorScoreMatrix,
    holdings: Holdings,
    policy: PortfolioPolicy,
) -> tuple[ResearchNeed, ...]:
    """Propose up to five underweight approved factor needs for PM review.

    The proposal is deliberately not a trade list: it tells the PM which
    methodologies need research attention. The PM may reorder, suppress, or
    add briefs before students see the weekly queue.
    """
    validate_long_only_holdings(holdings)
    validate_portfolio_policy(policy)
    if scores.as_of != holdings.as_of:
        raise ValueError("weekly queue requires factor scores and holdings from the same snapshot")

    needs: list[ResearchNeed] = []
    for factor, weight in scores.weights.items():
        if weight <= 0:
            continue
        current_score = _portfolio_factor_score(factor, scores, holdings, policy)
        if current_score is None:
            needs.append(
                ResearchNeed(
                    factor=factor,
                    direction=Direction.BUY,
                    current_score=None,
                    target_score=policy.factor_target_score,
                    priority="priority",
                    rationale="Factor data is unavailable for one or more current holdings; resolve before treating this exposure as measured.",
                )
            )
            continue
        priority = _priority(current_score, policy)
        if priority is None:
            continue
        needs.append(
            ResearchNeed(
                factor=factor,
                direction=Direction.BUY,
                current_score=current_score,
                target_score=policy.factor_target_score,
                priority=priority,
                rationale=(
                    f"Portfolio {factor} score is {current_score:.1f}, below the "
                    f"{priority} threshold; seek names that strengthen {factor}."
                ),
            )
        )

    return tuple(
        sorted(
            needs,
            key=lambda need: (
                need.current_score is not None,
                need.current_score if need.current_score is not None else float("-inf"),
            ),
        )[: policy.max_research_briefs]
    )
