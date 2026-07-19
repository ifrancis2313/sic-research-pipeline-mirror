from dataclasses import replace
from datetime import date, timedelta

import pytest

from qepm.advisor_queue import admit_proposed_trade, execution_status
from qepm.contracts import (
    DecisionRecord,
    Direction,
    ExceptionRecord,
    ExecutionPriceLimit,
    PortfolioFitResult,
    ProposedTrade,
    SizingRecommendation,
    TradeOrder,
)
from qepm.governance import DEFAULT_ORDINARY_RULE_ID


def _proposal(*, approved_on: date = date(2026, 7, 1), passed: bool = True, pitch_ready: bool = True) -> ProposedTrade:
    order = TradeOrder("FIGI", Direction.BUY, 3_000.0, "PITCH", "BRIEF", "TARGET")
    return ProposedTrade(
        order=order,
        approved_on=approved_on,
        pitch_ready=pitch_ready,
        approved_fit=PortfolioFitResult("PITCH", "BRIEF", "TARGET", approved_on, passed, not passed, {}, {}, order=order),
        sizing=SizingRecommendation(0.8, 0.03, 0.03, False, False),
        approval_nav=100_000.0,
        decision=DecisionRecord("PITCH", True, approved_on, ("Board Chair", "PM"), DEFAULT_ORDINARY_RULE_ID),
        price_limit=ExecutionPriceLimit(95.0, 100.0, "DCF-supported purchase ceiling.", 120.0, 0.10),
    )


def test_proposed_trade_requires_retest_after_thirty_days():
    approved_on = date(2026, 7, 1)
    proposal = _proposal(approved_on=approved_on)

    assert execution_status(proposal, approved_on + timedelta(days=29)).eligible_for_execution is True
    assert execution_status(proposal, approved_on + timedelta(days=30)).requires_retest is True


def test_advisor_queue_rejects_incomplete_approval_artifacts():
    with pytest.raises(ValueError, match="requires ready pitch"):
        admit_proposed_trade(_proposal(pitch_ready=False))


def test_advisor_queue_requires_an_approved_decision_for_the_same_pitch():
    proposal = replace(_proposal(), decision=DecisionRecord("OTHER", True, date(2026, 7, 1), ("PM",), DEFAULT_ORDINARY_RULE_ID))
    with pytest.raises(ValueError, match="approved Eboard"):
        admit_proposed_trade(proposal)


def test_approved_exception_can_enter_the_advisor_queue_after_a_failed_fit_check():
    proposal = replace(
        _proposal(passed=False),
        exception=ExceptionRecord(
            order=_proposal().order,
            as_of=date(2026, 7, 1),
            hard_limit_violations=("liquidity-participation",),
            rationale="The advisor confirmed a controlled block execution is appropriate.",
            approvers=("Board Chair", "Faculty Advisor"),
        ),
        approved_fit=PortfolioFitResult(
            "PITCH", "BRIEF", "TARGET", date(2026, 7, 1), False, True, {}, {},
            hard_limit_violations=("liquidity-participation",), order=_proposal().order,
        ),
    )
    assert admit_proposed_trade(proposal) is proposal
    assert execution_status(proposal, date(2026, 7, 2)).eligible_for_execution is True


@pytest.mark.parametrize(
    "changed",
    (
        lambda proposal: replace(proposal.exception, as_of=date(2026, 7, 2)),
        lambda proposal: replace(proposal.exception, order=replace(proposal.order, dollar_amount=2_999.0)),
        lambda proposal: replace(proposal.exception, hard_limit_violations=("name-cap",)),
    ),
)
def test_exception_must_bind_the_approved_order_snapshot_and_exact_hard_violations(changed):
    proposal = replace(
        _proposal(passed=False),
        approved_fit=PortfolioFitResult(
            "PITCH", "BRIEF", "TARGET", date(2026, 7, 1), False, True, {}, {},
            hard_limit_violations=("liquidity-participation",), order=_proposal().order,
        ),
        exception=ExceptionRecord(
            _proposal().order, date(2026, 7, 1), ("liquidity-participation",),
            "The advisor confirmed a controlled block execution is appropriate.", ("Board Chair", "Faculty Advisor"),
        ),
    )

    with pytest.raises(ValueError, match="exception"):
        admit_proposed_trade(replace(proposal, exception=changed(proposal)))


def test_advisor_queue_requires_decision_on_the_recorded_approval_date():
    proposal = replace(_proposal(approved_on=date(2026, 7, 2)), decision=DecisionRecord("PITCH", True, date(2026, 7, 1), ("PM",), DEFAULT_ORDINARY_RULE_ID))
    with pytest.raises(ValueError, match="decided_on"):
        admit_proposed_trade(proposal)


def test_execution_status_rejects_a_date_before_approval():
    assert execution_status(_proposal(approved_on=date(2026, 7, 2)), date(2026, 7, 1)).eligible_for_execution is False


@pytest.mark.parametrize("amount", (0.0, -1.0, float("nan"), float("inf"), float("-inf")))
def test_advisor_queue_rejects_non_positive_or_non_finite_trade_amounts(amount: float):
    proposal = _proposal()
    order = replace(proposal.order, dollar_amount=amount)
    proposal = replace(proposal, order=order, approved_fit=replace(proposal.approved_fit, order=order))
    with pytest.raises(ValueError, match="finite, positive trade dollar amount"):
        admit_proposed_trade(proposal)


@pytest.mark.parametrize("field", ("reference_price", "limit_price", "fair_value_per_share"))
@pytest.mark.parametrize("value", (0.0, -1.0, float("nan"), float("inf"), float("-inf")))
def test_advisor_queue_rejects_non_positive_or_non_finite_valuation_values(field: str, value: float):
    proposal = _proposal()
    with pytest.raises(ValueError, match="finite, positive price values"):
        admit_proposed_trade(replace(proposal, price_limit=replace(proposal.price_limit, **{field: value})))


@pytest.mark.parametrize("threshold", (0.0, -0.1, float("nan"), float("inf"), float("-inf")))
def test_advisor_queue_rejects_non_positive_or_non_finite_material_move_threshold(threshold: float):
    proposal = _proposal()
    with pytest.raises(ValueError, match="finite, positive"):
        admit_proposed_trade(replace(proposal, price_limit=replace(proposal.price_limit, material_move_fraction=threshold)))
