"""Trade execution with an advisor-queue control boundary.

``execute_live_proposed_trade`` is the only supported V1 advisor-handoff
seam. It requires a live-ready snapshot as well as proposal governance and a
review-clear current fit. The retained walking-skeleton helper is demo-only.
"""

from __future__ import annotations

from pathlib import Path

from qepm.advisor_queue import execution_status, validate_admitted_proposed_trade
from qepm.advisor_workbook import prepare_advisor_handoff, review_pending_trade
from qepm.contracts import (
    BacktestResult,
    ExecutionResult,
    PhaseGateError,
    PortfolioFitResult,
    ProposedTrade,
    Snapshot,
    TradeOrder,
)
from qepm.trade_execution.executors import Executor, _AdvisorPassthroughExecutor
from qepm.trade_execution.gate import validate_backtest_passed
from qepm.universe_data_store.v1_snapshot import validate_v1_snapshot_ready_for_live_use

__all__ = [
    "execute_walking_skeleton_demo",
    "execute_proposed_trade",
    "execute_live_proposed_trade",
    "Executor",
]

_DEFAULT_ADVISOR_EXECUTOR = _AdvisorPassthroughExecutor()


class _WalkingSkeletonDemoExecutor(Executor):
    """Formatting-only demo backend, deliberately separate from advisor handoff."""

    def execute(self, order: TradeOrder) -> ExecutionResult:
        return ExecutionResult(
            order=order,
            status="demo_complete",
            backend="WalkingSkeletonDemoExecutor",
            confirmation_note=(
                f"DEMO ONLY: simulated {order.direction.value.upper()} ${order.dollar_amount:,.0f} of {order.figi} "
                f"(pitch {order.pitch_id}, brief {order.brief_id}, target {order.target_id})."
            ),
        )


def execute_walking_skeleton_demo(
    order: TradeOrder, backtest_result: BacktestResult, executor: Executor | None = None
) -> ExecutionResult:
    """Run the original simulated walking-skeleton demonstration; never a live path."""
    validate_backtest_passed(order, backtest_result)
    return (executor or _WalkingSkeletonDemoExecutor()).execute(order)


def execute_proposed_trade(
    proposal: ProposedTrade, snapshot: Snapshot, current_fit: PortfolioFitResult, executor: Executor | None = None
) -> ExecutionResult:
    """V1 execution seam: require governance admission and a review-clear current snapshot."""
    validate_admitted_proposed_trade(proposal)
    status = execution_status(proposal, snapshot.as_of)
    if not status.eligible_for_execution:
        raise PhaseGateError(status.reason)
    review = review_pending_trade(proposal, snapshot, current_fit)
    if review.requires_review:
        raise PhaseGateError("; ".join(review.reasons))
    return (executor or _DEFAULT_ADVISOR_EXECUTOR).execute(proposal.order)


def execute_live_proposed_trade(
    proposal: ProposedTrade,
    snapshot: Snapshot,
    current_fit: PortfolioFitResult,
    *,
    workbook_path: Path | None = None,
    expected_workbook_revision: str | None = None,
    prepared_by: str | None = None,
) -> ExecutionResult:
    """Create an advisor handoff only from a V1 live-ready snapshot.

    This is the supported production entry point.  The lower-level
    ``execute_proposed_trade`` remains usable for deterministic local tests and
    controlled fixture exercises, but must not be represented as a live run.
    """
    validate_v1_snapshot_ready_for_live_use(snapshot)
    if workbook_path is None or expected_workbook_revision is None or prepared_by is None:
        raise PhaseGateError(
            "live advisor handoff requires workbook_path, expected_workbook_revision, and prepared_by for durable ledger recording"
        )
    result = execute_proposed_trade(proposal, snapshot, current_fit)
    prepare_advisor_handoff(
        workbook_path,
        proposal,
        snapshot,
        current_fit,
        expected_revision=expected_workbook_revision,
        prepared_by=prepared_by,
    )
    return result
