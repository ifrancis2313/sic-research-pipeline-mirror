"""Brief -> Backtest phase gate: validates a pitch/target/brief triple before evaluation.

check_no_leakage confirms none of the backtest's inputs (the universe
snapshot, the factor scores, the current holdings) carry a date later
than the evaluation date - the same "don't let future data leak into a
point-in-time decision" principle as Phase 1's and the Factor
Registry's own leakage checks, applied here to the backtest's own three
composite inputs' as_of stamps.
"""

from __future__ import annotations

from datetime import date

from qepm.contracts import (
    CompetingPitch,
    ExposureTarget,
    FactorScoreMatrix,
    Holdings,
    PhaseGateError,
    ResearchBrief,
    Snapshot,
)
from qepm.portfolio_state import (
    validate_exposure_target,
    validate_long_only_holdings,
    validate_snapshot_identities,
)


def validate_pitch_for_backtest(
    pitch: CompetingPitch,
    target: ExposureTarget,
    brief: ResearchBrief,
    scores: FactorScoreMatrix,
    snapshot: Snapshot,
    portfolio: Holdings,
    evaluation_date: date,
) -> None:
    validate_exposure_target(target)
    validate_snapshot_identities(snapshot)
    validate_long_only_holdings(portfolio)
    if pitch.brief_id != brief.id:
        raise PhaseGateError(
            f"Pitch {pitch.id} references brief {pitch.brief_id!r}, not the given brief {brief.id!r}"
        )

    if brief.target.id != target.id:
        raise PhaseGateError(
            f"Brief {brief.id} was created for target {brief.target.id!r}, not the given target {target.id!r}"
        )

    if pitch.figi not in scores.scores.index:
        raise PhaseGateError(f"Pitch {pitch.id}'s security {pitch.figi} has no factor score - cannot backtest")

    check_no_leakage(snapshot, scores, portfolio, evaluation_date)


def validate_pitch_for_portfolio_fit(
    pitch: CompetingPitch,
    target: ExposureTarget,
    brief: ResearchBrief,
    scores: FactorScoreMatrix,
    snapshot: Snapshot,
    portfolio: Holdings,
    evaluation_date: date,
) -> None:
    """Validate identity and as-of consistency without requiring a factor score."""
    validate_exposure_target(target)
    validate_snapshot_identities(snapshot)
    validate_long_only_holdings(portfolio)
    if pitch.brief_id != brief.id:
        raise PhaseGateError(
            f"Pitch {pitch.id} references brief {pitch.brief_id!r}, not the given brief {brief.id!r}"
        )

    if brief.target.id != target.id:
        raise PhaseGateError(
            f"Brief {brief.id} was created for target {brief.target.id!r}, not the given target {target.id!r}"
        )

    if pitch.figi not in snapshot.securities.index:
        raise PhaseGateError(f"Pitch {pitch.id}'s security {pitch.figi} has no snapshot identity")
    if "dollar_value" not in portfolio.positions.columns:
        raise PhaseGateError("Portfolio Fit Check requires dollar_value position data")

    if snapshot.as_of != evaluation_date or scores.as_of != evaluation_date or portfolio.as_of != evaluation_date:
        raise PhaseGateError(
            "Portfolio Fit Check requires snapshot, scores, holdings, and evaluation date from the same as_of date"
        )
    check_no_leakage(snapshot, scores, portfolio, evaluation_date)


def check_no_leakage(
    snapshot: Snapshot, scores: FactorScoreMatrix, portfolio: Holdings, evaluation_date: date
) -> None:
    violations = []
    if snapshot.as_of > evaluation_date:
        violations.append(f"snapshot.as_of={snapshot.as_of}")
    if scores.as_of > evaluation_date:
        violations.append(f"scores.as_of={scores.as_of}")
    if portfolio.as_of > evaluation_date:
        violations.append(f"portfolio.as_of={portfolio.as_of}")

    if violations:
        raise PhaseGateError(
            f"leakage: backtest inputs reference data dated after evaluation_date={evaluation_date}: "
            f"{', '.join(violations)}"
        )
