from dataclasses import replace
from datetime import date

import pytest

from qepm.advisor_queue import admit_proposed_trade
from qepm.contracts import (
    DecisionRecord,
    Direction,
    ExecutionPriceLimit,
    PortfolioFitResult,
    ProposedTrade,
    SizingRecommendation,
    TradeOrder,
)
from qepm.governance import DEFAULT_ORDINARY_RULE_ID


def _proposal() -> ProposedTrade:
    order = TradeOrder("FIGI", Direction.BUY, 3_000.0, "PITCH", "BRIEF", "TARGET")
    approved_on = date(2026, 7, 10)
    return ProposedTrade(
        order=order,
        approved_on=approved_on,
        pitch_ready=True,
        approved_fit=PortfolioFitResult("PITCH", "BRIEF", "TARGET", approved_on, True, False, {}, {}, order=order),
        sizing=SizingRecommendation(0.8, 0.03, 0.03, False, False),
        approval_nav=100_000.0,
        decision=DecisionRecord("PITCH", True, approved_on, ("Board Chair", "PM"), DEFAULT_ORDINARY_RULE_ID),
        price_limit=ExecutionPriceLimit(95.0, 100.0, "DCF-supported purchase ceiling.", 120.0, 0.10),
    )


@pytest.mark.parametrize("fit_date", (date(2026, 7, 9), date(2026, 7, 11)))
def test_advisor_queue_rejects_stale_or_future_approval_fit_attestations(fit_date: date):
    proposal = _proposal()
    proposal = replace(proposal, approved_fit=replace(proposal.approved_fit, as_of=fit_date))

    with pytest.raises(ValueError, match="approval date"):
        admit_proposed_trade(proposal)


def test_advisor_queue_rejects_approval_fit_for_a_different_exact_order():
    proposal = _proposal()
    proposal = replace(proposal, approved_fit=replace(proposal.approved_fit, order=replace(proposal.order, dollar_amount=2_999.0)))

    with pytest.raises(ValueError, match="exact proposed order"):
        admit_proposed_trade(proposal)


def test_advisor_queue_rejects_order_above_approved_sizing_cap():
    proposal = replace(_proposal(), order=replace(_proposal().order, dollar_amount=3_000.01))
    proposal = replace(proposal, approved_fit=replace(proposal.approved_fit, order=proposal.order))

    with pytest.raises(ValueError, match="approved sizing maximum"):
        admit_proposed_trade(proposal)


def test_advisor_queue_accepts_order_at_approved_sizing_cap():
    assert admit_proposed_trade(_proposal()).order.dollar_amount == 3_000.0


@pytest.mark.parametrize(
    "sizing",
    (
        SizingRecommendation(float("nan"), 0.03, 0.03, False, False),
        SizingRecommendation(0.8, 0.04, 0.03, False, False),
        SizingRecommendation(0.8, 0.03, 1.01, False, False),
    ),
)
def test_advisor_queue_rejects_invalid_sizing_attestation(sizing: SizingRecommendation):
    with pytest.raises(ValueError, match="sizing"):
        admit_proposed_trade(replace(_proposal(), sizing=sizing))
