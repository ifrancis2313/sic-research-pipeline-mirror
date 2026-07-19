"""Friday-close local operating cycle for SIC's weekly research pulse."""

from __future__ import annotations

from qepm.beta_monitoring import portfolio_beta_status
from qepm.contracts import (
    FactorScoreMatrix,
    Holdings,
    PortfolioPolicy,
    ProposedTrade,
    Snapshot,
    WeeklyCycleResult,
)
from qepm.portfolio_pulse import eboard_pulse, student_pulse
from qepm.research_queue import propose_weekly_research_queue
from qepm.sleeves import sleeve_status, sleeve_weights
from qepm.universe_data_store.v1_snapshot import validate_v1_snapshot_ready_for_live_use

__all__ = ["run_weekly_cycle", "run_live_weekly_cycle"]


def run_weekly_cycle(
    snapshot: Snapshot, scores: FactorScoreMatrix, holdings: Holdings, policy: PortfolioPolicy,
    sleeve_by_identifier: dict[str, str], brief_statuses: dict[str, str], proposed_trades: tuple[ProposedTrade, ...] = (),
) -> WeeklyCycleResult:
    """Produce student and Eboard Friday pulses from one point-in-time state."""
    if snapshot.as_of.weekday() != 4:
        raise ValueError("weekly portfolio snapshot must use Friday close")
    if snapshot.as_of != scores.as_of or snapshot.as_of != holdings.as_of:
        raise ValueError("weekly cycle inputs must share one as-of date")
    needs = propose_weekly_research_queue(scores, holdings, policy)
    beta_status = portfolio_beta_status(holdings, snapshot, policy).status
    sleeves = sleeve_weights(holdings, policy, sleeve_by_identifier)
    statuses = sleeve_status(sleeves, policy)
    student = student_pulse(needs, beta_status, brief_statuses, sleeves, statuses)
    board = eboard_pulse(holdings, needs, beta_status, proposed_trades, brief_statuses, sleeves, statuses)
    return WeeklyCycleResult(student, board)


def run_live_weekly_cycle(
    snapshot: Snapshot, scores: FactorScoreMatrix, holdings: Holdings, policy: PortfolioPolicy,
    sleeve_by_identifier: dict[str, str], brief_statuses: dict[str, str], proposed_trades: tuple[ProposedTrade, ...] = (),
) -> WeeklyCycleResult:
    """Run the production weekly path after proving the snapshot is live-ready.

    ``run_weekly_cycle`` remains the deliberately local/fixture-friendly calculation
    seam.  Production callers must use this named entry point so availability
    dates and the complete V1 live-input schema are checked before any weekly
    operating result is represented as live.
    """
    validate_v1_snapshot_ready_for_live_use(snapshot)
    return run_weekly_cycle(snapshot, scores, holdings, policy, sleeve_by_identifier, brief_statuses, proposed_trades)
