from copy import deepcopy
from dataclasses import replace
from datetime import date

import pandas as pd
import pytest

from qepm.advisor_queue import reconcile_pending_trade_fits
from qepm.contracts import (
    CompetingPitch,
    DecisionRecord,
    DimensionSpec,
    Direction,
    ExecutionPriceLimit,
    ExposureTarget,
    FactorScoreMatrix,
    Holdings,
    PhaseGateError,
    PortfolioFitResult,
    PortfolioPolicy,
    ProposedTrade,
    ResearchBrief,
    SizingRecommendation,
    Snapshot,
    TradeOrder,
)


def _artifacts() -> tuple[CompetingPitch, ResearchBrief, ExposureTarget, ProposedTrade]:
    target = ExposureTarget("TARGET", Direction.BUY, 3_000.0, DimensionSpec(factor="quality"), "Add quality exposure.")
    brief = ResearchBrief("BRIEF", target, "Research the candidate.")
    pitch = CompetingPitch("PITCH", brief.id, "Pod A", "FIGI", "Durable free-cash-flow growth.")
    order = TradeOrder("FIGI", Direction.BUY, 3_000.0, pitch.id, brief.id, target.id)
    proposal = ProposedTrade(
        order,
        approved_on=date(2026, 7, 10),
        pitch_ready=True,
        approved_fit=PortfolioFitResult(pitch.id, brief.id, target.id, date(2026, 7, 10), True, False, {}, {}, order=order),
        sizing=SizingRecommendation(0.8, 0.03, 0.03, False, False),
        approval_nav=100_000.0,
        decision=DecisionRecord(pitch.id, True, date(2026, 7, 10), ("Board Chair", "PM"), "chair-plus-pm-or-lead-v1"),
        price_limit=ExecutionPriceLimit(95.0, 100.0, "DCF-supported purchase ceiling.", material_move_fraction=0.10),
    )
    return pitch, brief, target, proposal


def _current_inputs(*, position_value: float = 0.0) -> tuple[Snapshot, FactorScoreMatrix, Holdings, PortfolioPolicy]:
    as_of = date(2026, 7, 17)
    securities = pd.DataFrame(
        {
            "quality": [70.0],
            "median_daily_dollar_volume": [10_000_000.0],
            "market_beta_90d": [0.8],
            "has_price_history": [True],
            "is_russell_1000": [True],
        },
        index=pd.Index(["FIGI"], name="figi"),
    )
    snapshot = Snapshot(as_of, securities, pd.DataFrame())
    scores = FactorScoreMatrix(as_of, pd.DataFrame({"quality": [70.0]}, index=securities.index), {"quality": 1.0})
    holdings = Holdings(as_of, pd.DataFrame({"dollar_value": [position_value]}, index=securities.index))
    return snapshot, scores, holdings, PortfolioPolicy(portfolio_nav=100_000.0)


def _reconcile(*, position_value: float = 0.0):
    pitch, brief, target, proposal = _artifacts()
    snapshot, scores, holdings, policy = _current_inputs(position_value=position_value)
    fits = reconcile_pending_trade_fits(
        snapshot, scores, holdings, policy, (proposal,), {pitch.id: pitch}, {brief.id: brief}, {target.id: target}
    )
    return fits, snapshot, brief


def test_reconciliation_recomputes_a_current_fit_with_the_snapshot_date():
    fits, snapshot, brief = _reconcile()

    assert fits["PITCH"].passed is True
    assert fits["PITCH"].as_of == snapshot.as_of
    assert brief.status == "open"  # reconciliation did not mutate canonical research state


def test_reconciliation_does_not_mutate_any_canonical_brief_lifecycle_collections():
    pitch, brief, target, proposal = _artifacts()
    brief.assigned_pods.extend(("Pod A", "Pod B"))
    brief.pitches.append(pitch)
    brief.status = "in-progress"
    original = deepcopy(brief)
    snapshot, scores, holdings, policy = _current_inputs()

    reconcile_pending_trade_fits(
        snapshot, scores, holdings, policy, (proposal,), {pitch.id: pitch}, {brief.id: brief}, {target.id: target}
    )

    assert brief == original
    assert brief.assigned_pods == ["Pod A", "Pod B"]
    assert brief.pitches == [pitch]
    assert brief.status == "in-progress"


def test_reconciliation_detects_a_changed_current_portfolio_condition():
    fits, _, _ = _reconcile(position_value=9_000.0)

    assert fits["PITCH"].passed is False
    assert fits["PITCH"].hard_limit_violations == ("single-name-cap",)


@pytest.mark.parametrize("kind", ["missing", "mismatched"])
def test_reconciliation_fails_closed_for_missing_or_mismatched_canonical_provenance(kind: str):
    pitch, brief, target, proposal = _artifacts()
    snapshot, scores, holdings, policy = _current_inputs()
    pitches = {pitch.id: pitch}
    briefs = {brief.id: brief}
    targets = {target.id: target}
    if kind == "missing":
        pitches = {}
    else:
        mismatched_target = ExposureTarget("TARGET", Direction.BUY, 4_000.0, DimensionSpec(factor="quality"), "Different target.")
        targets = {target.id: mismatched_target}

    with pytest.raises(PhaseGateError, match="canonical|does not contain"):
        reconcile_pending_trade_fits(snapshot, scores, holdings, policy, (proposal,), pitches, briefs, targets)


def test_reconciliation_rejects_misaligned_current_input_dates():
    pitch, brief, target, proposal = _artifacts()
    snapshot, scores, holdings, policy = _current_inputs()
    stale_holdings = Holdings(date(2026, 7, 16), holdings.positions)

    with pytest.raises(PhaseGateError, match="same as_of"):
        reconcile_pending_trade_fits(
            snapshot, scores, stale_holdings, policy, (proposal,), {pitch.id: pitch}, {brief.id: brief}, {target.id: target}
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (("figi", "OTHER-FIGI"), ("direction", Direction.SELL), ("dollar_amount", 3_001.0)),
)
def test_reconciliation_rejects_order_fields_that_differ_from_canonical_pitch_or_target(field: str, value: object):
    pitch, brief, target, proposal = _artifacts()
    snapshot, scores, holdings, policy = _current_inputs()
    altered = replace(proposal, order=replace(proposal.order, **{field: value}))

    with pytest.raises(PhaseGateError, match="FIGI|direction or dollar amount"):
        reconcile_pending_trade_fits(
            snapshot, scores, holdings, policy, (altered,), {pitch.id: pitch}, {brief.id: brief}, {target.id: target}
        )


def test_reconciliation_rejects_conflicting_pending_orders_for_one_figi():
    pitch, brief, target, proposal = _artifacts()
    second = replace(proposal, order=replace(proposal.order, pitch_id="PITCH-2"))
    snapshot, scores, holdings, policy = _current_inputs()

    with pytest.raises(PhaseGateError, match="same FIGI"):
        reconcile_pending_trade_fits(
            snapshot, scores, holdings, policy, (proposal, second), {pitch.id: pitch}, {brief.id: brief}, {target.id: target}
        )
