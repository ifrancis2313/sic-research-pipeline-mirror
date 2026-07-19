from dataclasses import replace
from datetime import date, timedelta
from inspect import signature

import pandas as pd
import pytest

import qepm.trade_execution as trade_execution
from qepm.contracts import (
    BacktestResult,
    DecisionRecord,
    Direction,
    ExceptionRecord,
    ExecutionPriceLimit,
    ExecutionResult,
    PhaseGateError,
    PortfolioFitResult,
    ProposedTrade,
    SizingRecommendation,
    Snapshot,
    TradeOrder,
)
from qepm.governance import DEFAULT_ORDINARY_RULE_ID
from qepm.trade_execution import (
    Executor,
    execute_live_proposed_trade,
    execute_proposed_trade,
    execute_walking_skeleton_demo,
)

ORDER = TradeOrder(
    figi="BBG-FIXTURE-007",
    direction=Direction.BUY,
    dollar_amount=21_882.35,
    pitch_id="CP-1",
    brief_id="RB-ET-BUY-ENERGY",
    target_id="ET-BUY-ENERGY",
)

PASSED_BACKTEST = BacktestResult(
    pitch_id="CP-1",
    brief_id="RB-ET-BUY-ENERGY",
    target_id="ET-BUY-ENERGY",
    passed=True,
    factor_fit={"momentum": 0.11},
    estimated_impact={"dollar_impact": 21_882.35},
)

CURRENT_FIT = PortfolioFitResult(
    "CP-1", "RB-ET-BUY-ENERGY", "ET-BUY-ENERGY", date(2026, 7, 1), True, False, {}, {}, order=ORDER
)


def _proposal() -> ProposedTrade:
    return ProposedTrade(
        order=ORDER,
        approved_on=date(2026, 7, 1),
        pitch_ready=True,
        approved_fit=CURRENT_FIT,
        sizing=SizingRecommendation(0.8, 0.25, 0.30, False, False),
        approval_nav=100_000.0,
        decision=DecisionRecord("CP-1", True, date(2026, 7, 1), ("Board Chair", "PM"), DEFAULT_ORDINARY_RULE_ID),
        price_limit=ExecutionPriceLimit(95.0, 100.0, "DCF-supported purchase ceiling.", material_move_fraction=0.10),
    )


def test_walking_skeleton_demo_produces_a_correctly_formatted_advisor_handoff():
    result = execute_walking_skeleton_demo(ORDER, PASSED_BACKTEST)

    assert result.status == "demo_complete"
    assert result.backend == "WalkingSkeletonDemoExecutor"
    assert "DEMO ONLY" in result.confirmation_note
    assert "BUY" in result.confirmation_note
    assert "$21,882" in result.confirmation_note
    assert ORDER.figi in result.confirmation_note


def test_walking_skeleton_demo_accepts_a_test_double_without_changing_upstream_code():
    class FakePaperTradeExecutor(Executor):
        """A stand-in backend defined entirely in this test, not in trade_execution/."""

        def execute(self, order: TradeOrder) -> ExecutionResult:
            return ExecutionResult(
                order=order, status="paper_filled", backend="FakePaperTradeExecutor", confirmation_note="test double"
            )

    # same order, same backtest result, same call shape as the default-backend test above -
    # only the executor argument changes.
    result = execute_walking_skeleton_demo(ORDER, PASSED_BACKTEST, executor=FakePaperTradeExecutor())

    assert result.status == "paper_filled"
    assert result.backend == "FakePaperTradeExecutor"


def test_live_execution_does_not_accept_an_arbitrary_executor_backend():
    # SIC policy requires the advisor handoff.  Only the demo seam accepts a
    # test executor; the live entry point has no direct-broker injection path.
    assert "executor" not in signature(execute_live_proposed_trade).parameters


def test_direct_broker_stub_is_not_part_of_the_execution_architecture():
    import qepm.trade_execution.executors as executors

    assert "IBKRExecutor" not in trade_execution.__all__
    assert not hasattr(trade_execution, "IBKRExecutor")
    assert not hasattr(executors, "IBKRExecutor")


def test_execution_result_traces_back_to_pitch_brief_and_target():
    result = execute_walking_skeleton_demo(ORDER, PASSED_BACKTEST)

    assert result.order.pitch_id == "CP-1"
    assert result.order.brief_id == "RB-ET-BUY-ENERGY"
    assert result.order.target_id == "ET-BUY-ENERGY"
    # The simulated demo preserves the trace chain without using the advisor formatter.
    assert "CP-1" in result.confirmation_note
    assert "RB-ET-BUY-ENERGY" in result.confirmation_note
    assert "ET-BUY-ENERGY" in result.confirmation_note


def test_v1_execution_requires_an_admitted_current_proposed_trade():
    proposal = _proposal()

    snapshot = Snapshot(date(2026, 7, 1), pd.DataFrame({"price": [95.0]}, index=[ORDER.figi]), pd.DataFrame())
    result = execute_proposed_trade(proposal, snapshot, CURRENT_FIT)

    assert result.status == "sent_to_advisor"

    with pytest.raises(PhaseGateError, match="must be retested"):
        stale_snapshot = Snapshot(proposal.approved_on + timedelta(days=31), pd.DataFrame({"price": [95.0]}, index=[ORDER.figi]), pd.DataFrame())
        execute_proposed_trade(proposal, stale_snapshot, CURRENT_FIT)


def test_live_execution_rejects_a_fixture_snapshot_before_advisor_handoff():
    proposal = _proposal()
    fixture_snapshot = Snapshot(
        date(2026, 7, 1), pd.DataFrame({"price": [95.0]}, index=[ORDER.figi]), pd.DataFrame()
    )

    with pytest.raises(PhaseGateError, match="V1 live snapshot is missing required fields"):
        execute_live_proposed_trade(proposal, fixture_snapshot, CURRENT_FIT)


def test_raw_advisor_executor_is_not_a_public_trade_execution_api():
    import qepm.trade_execution.executors as executors

    assert "AdvisorPassthroughExecutor" not in trade_execution.__all__
    assert not hasattr(trade_execution, "AdvisorPassthroughExecutor")
    assert not hasattr(executors, "AdvisorPassthroughExecutor")


def test_v1_execution_stops_when_current_snapshot_flags_pending_trade_for_review():
    proposal = _proposal()
    outside_limit = Snapshot(date(2026, 7, 1), pd.DataFrame({"price": [101.0]}, index=[ORDER.figi]), pd.DataFrame())

    with pytest.raises(PhaseGateError, match="price-above-buy-limit"):
        execute_proposed_trade(proposal, outside_limit, CURRENT_FIT)


def test_v1_execution_blocks_a_fit_result_from_another_snapshot():
    proposal = _proposal()
    snapshot = Snapshot(date(2026, 7, 8), pd.DataFrame({"price": [95.0]}, index=[ORDER.figi]), pd.DataFrame())

    with pytest.raises(PhaseGateError, match="current-portfolio-fit-stale"):
        execute_proposed_trade(proposal, snapshot, CURRENT_FIT)


def test_matched_hard_limit_exception_can_proceed_but_never_bypasses_price_or_retest_reviews():
    failed_fit = replace(CURRENT_FIT, passed=False, requires_exception=True, hard_limit_violations=("name-cap",))
    proposal = replace(
        _proposal(), approved_fit=failed_fit,
        exception=ExceptionRecord(ORDER, date(2026, 7, 1), ("name-cap",), "Temporary concentration is approved.", ("Board Chair", "Faculty Advisor")),
    )
    snapshot = Snapshot(date(2026, 7, 1), pd.DataFrame({"price": [95.0]}, index=[ORDER.figi]), pd.DataFrame())
    assert execute_proposed_trade(proposal, snapshot, failed_fit).status == "sent_to_advisor"

    outside_limit = Snapshot(date(2026, 7, 1), pd.DataFrame({"price": [101.0]}, index=[ORDER.figi]), pd.DataFrame())
    with pytest.raises(PhaseGateError, match="price-above-buy-limit"):
        execute_proposed_trade(proposal, outside_limit, failed_fit)

    retest_snapshot = Snapshot(date(2026, 7, 31), pd.DataFrame({"price": [95.0]}, index=[ORDER.figi]), pd.DataFrame())
    with pytest.raises(PhaseGateError, match="30-calendar-day retest"):
        execute_proposed_trade(proposal, retest_snapshot, replace(failed_fit, as_of=date(2026, 7, 31)))


def test_exception_cannot_cover_a_different_current_hard_limit_violation():
    failed_fit = replace(CURRENT_FIT, passed=False, requires_exception=True, hard_limit_violations=("name-cap",))
    proposal = replace(
        _proposal(), approved_fit=failed_fit,
        exception=ExceptionRecord(ORDER, date(2026, 7, 1), ("name-cap",), "Temporary concentration is approved.", ("Board Chair", "Faculty Advisor")),
    )
    snapshot = Snapshot(date(2026, 7, 1), pd.DataFrame({"price": [95.0]}, index=[ORDER.figi]), pd.DataFrame())
    different_violation = replace(failed_fit, hard_limit_violations=("liquidity-participation",))

    with pytest.raises(PhaseGateError, match="current-portfolio-fit-failed"):
        execute_proposed_trade(proposal, snapshot, different_violation)


@pytest.mark.parametrize(
    ("field", "value"),
    (("figi", "OTHER-FIGI"), ("direction", Direction.SELL), ("dollar_amount", 1.0), ("pitch_id", "OTHER"), ("brief_id", "OTHER"), ("target_id", "OTHER")),
)
def test_v1_execution_rejects_a_fit_bound_to_a_different_order(field: str, value: object):
    proposal = _proposal()
    snapshot = Snapshot(date(2026, 7, 1), pd.DataFrame({"price": [95.0]}, index=[ORDER.figi]), pd.DataFrame())
    mismatched_fit = replace(CURRENT_FIT, order=replace(ORDER, **{field: value}))

    with pytest.raises(PhaseGateError, match="current-portfolio-fit-mismatch"):
        execute_proposed_trade(proposal, snapshot, mismatched_fit)
