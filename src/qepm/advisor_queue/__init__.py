"""Dated, advisor-facing proposed-trade queue controls.

The queue owns the reconciliation seam because an approved proposal is a
durable record, while its Portfolio Fit Check is intentionally a current,
same-snapshot assessment.  Callers cannot substitute a previously computed
fit result for that assessment.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from datetime import date
from math import isfinite

from qepm.contracts import (
    CompetingPitch,
    ExposureTarget,
    FactorScoreMatrix,
    Holdings,
    PhaseGateError,
    PortfolioFitResult,
    PortfolioPolicy,
    ProposedTrade,
    ProposedTradeStatus,
    ResearchBrief,
    Snapshot,
    TradeOrder,
)
from qepm.governance import exception_matches_fit, validate_decision_record, validate_exception_record
from qepm.portfolio_fit import evaluate_portfolio_fit
from qepm.portfolio_state import validate_portfolio_policy, validate_trade_order

__all__ = [
    "admit_proposed_trade", "execution_status", "reconcile_pending_trade_fits", "validate_admitted_proposed_trade",
    "validate_current_fit_for_order",
]


def admit_proposed_trade(proposal: ProposedTrade, policy: PortfolioPolicy | None = None) -> ProposedTrade:
    """Admit a new trade and freeze the governing price-move threshold on it.

    The production path supplies the policy used for the board decision.  The
    threshold is then copied into frozen proposal evidence, so policy changes
    affect future approvals only.  The optional no-policy form solely validates
    a previously admitted historical record.
    """
    if proposal.price_limit is None:
        raise ValueError("advisor queue requires a pitch-owned price limit")
    if policy is not None:
        validate_portfolio_policy(policy)
        existing = proposal.price_limit.material_move_fraction
        if existing is None:
            proposal = replace(
                proposal,
                price_limit=replace(proposal.price_limit, material_move_fraction=policy.material_price_move_fraction),
            )
        elif existing != policy.material_price_move_fraction:
            raise ValueError("advisor queue admission requires the price-move threshold from the current approval policy")
    validate_admitted_proposed_trade(proposal)
    return proposal


def validate_admitted_proposed_trade(proposal: ProposedTrade) -> None:
    """Validate immutable evidence for a previously admitted proposal."""
    has_approved_exception = exception_matches_fit(proposal.exception, proposal.approved_fit, proposal.order)
    if not all((proposal.approved_fit.passed or has_approved_exception, proposal.pitch_ready)):
        if not proposal.approved_fit.passed and proposal.exception is not None:
            raise ValueError("advisor queue exception must bind the approved order, snapshot, and exact hard-limit violations")
        raise ValueError("advisor queue requires ready pitch, sizing recommendation, and binding fit check")
    if proposal.decision is None or not proposal.decision.approved or proposal.decision.pitch_id != proposal.order.pitch_id:
        raise ValueError("advisor queue requires an approved Eboard decision for the same pitch")
    if proposal.decision.decided_on != proposal.approved_on:
        raise ValueError("advisor queue requires decision.decided_on to equal approved_on")
    _validate_order_numbers(proposal.order)
    _validate_approval_attestations(proposal)
    limit = proposal.price_limit
    if limit is None:
        raise ValueError("advisor queue requires a pitch-owned price limit")
    prices = (limit.reference_price, limit.limit_price, limit.fair_value_per_share)
    if any(value is not None and (not isfinite(value) or value <= 0) for value in prices) or not limit.rationale.strip():
        raise ValueError("advisor queue requires finite, positive price values and a price rationale")
    if limit.material_move_fraction is None or not isfinite(limit.material_move_fraction) or limit.material_move_fraction <= 0:
        raise ValueError("advisor queue requires a finite, positive material price-move threshold frozen at approval")
    validate_decision_record(proposal.decision)
    if proposal.exception is not None:
        try:
            validate_exception_record(proposal.exception)
        except ValueError as exc:
            raise ValueError(f"advisor queue requires a valid exception record: {exc}") from exc
        if not proposal.approved_fit.passed and not has_approved_exception:
            raise ValueError("advisor queue exception must bind the approved order, snapshot, and exact hard-limit violations")


def validate_current_fit_for_order(current_fit: PortfolioFitResult, order: TradeOrder) -> None:
    """Fail closed unless a current fit was calculated for this exact order."""
    if current_fit.order != order:
        raise PhaseGateError("current portfolio fit is not bound to the exact proposed order")


def execution_status(proposal: ProposedTrade, as_of: date) -> ProposedTradeStatus:
    """Reject incomplete approvals and require a fresh check after 30 days."""
    has_approved_exception = exception_matches_fit(proposal.exception, proposal.approved_fit, proposal.order)
    if not all((proposal.approved_fit.passed or has_approved_exception, proposal.pitch_ready)):
        return ProposedTradeStatus(False, False, "Proposal is missing a required approval artifact.")
    if as_of < proposal.approved_on:
        return ProposedTradeStatus(False, False, "Execution date cannot be before proposal approval.")
    age_days = (as_of - proposal.approved_on).days
    if age_days >= 30:
        return ProposedTradeStatus(False, True, "Proposal has reached its 30-calendar-day retest deadline and must be retested.")
    return ProposedTradeStatus(True, False)


def reconcile_pending_trade_fits(
    snapshot: Snapshot,
    scores: FactorScoreMatrix,
    holdings: Holdings,
    policy: PortfolioPolicy,
    pending_trades: tuple[ProposedTrade, ...],
    pitches_by_id: Mapping[str, CompetingPitch],
    briefs_by_id: Mapping[str, ResearchBrief],
    targets_by_id: Mapping[str, ExposureTarget],
) -> dict[str, PortfolioFitResult]:
    """Recompute each pending trade's current, canonical portfolio fit.

    This is deliberately pure: no queue state, approval state, or canonical
    brief status is changed.  It fails closed when a proposal cannot be tied
    to the exact pitch, brief, and target records that produced it.
    """
    if snapshot.as_of != scores.as_of or snapshot.as_of != holdings.as_of:
        raise PhaseGateError("pending-trade reconciliation requires snapshot, scores, and holdings from the same as_of date")

    pitch_ids = [proposal.order.pitch_id for proposal in pending_trades]
    if len(pitch_ids) != len(set(pitch_ids)):
        raise PhaseGateError("pending-trade reconciliation requires at most one proposal per pitch")
    figis = [proposal.order.figi for proposal in pending_trades]
    if len(figis) != len(set(figis)):
        raise PhaseGateError("pending-trade reconciliation rejects conflicting proposals for the same FIGI")

    fits: dict[str, PortfolioFitResult] = {}
    for proposal in pending_trades:
        pitch, brief, target = _canonical_artifacts_for(proposal, pitches_by_id, briefs_by_id, targets_by_id)
        # ``evaluate_portfolio_fit`` records a lifecycle status on its brief.
        # Reconciliation must not mutate canonical research history, including
        # its mutable pod/pitch lists, so it receives an isolated working copy.
        working_brief = deepcopy(brief)
        fits[pitch.id] = evaluate_portfolio_fit(
            pitch, target, working_brief, holdings, scores, snapshot, snapshot.as_of, policy
        )
    return fits


def _canonical_artifacts_for(
    proposal: ProposedTrade,
    pitches_by_id: Mapping[str, CompetingPitch],
    briefs_by_id: Mapping[str, ResearchBrief],
    targets_by_id: Mapping[str, ExposureTarget],
) -> tuple[CompetingPitch, ResearchBrief, ExposureTarget]:
    """Return exact provenance records for one proposal or fail closed."""
    order = proposal.order
    pitch = pitches_by_id.get(order.pitch_id)
    brief = briefs_by_id.get(order.brief_id)
    target = targets_by_id.get(order.target_id)
    if pitch is None or brief is None or target is None:
        raise PhaseGateError(f"pending trade {order.pitch_id} lacks canonical pitch, brief, or target provenance")
    if pitch.id != order.pitch_id or brief.id != order.brief_id or target.id != order.target_id:
        raise PhaseGateError(f"pending trade {order.pitch_id} has mismatched canonical record keys")
    if pitch.brief_id != brief.id:
        raise PhaseGateError(f"pending trade {order.pitch_id} pitch does not belong to proposal brief {order.brief_id}")
    if brief.target != target:
        raise PhaseGateError(f"pending trade {order.pitch_id} brief does not contain the proposal's canonical target")
    if order.figi != pitch.figi:
        raise PhaseGateError(f"pending trade {order.pitch_id} FIGI differs from its canonical pitch")
    if order.direction != target.direction or order.dollar_amount != target.dollar_amount:
        raise PhaseGateError(f"pending trade {order.pitch_id} direction or dollar amount differs from its canonical target")
    return pitch, brief, target


def _validate_order_numbers(order: TradeOrder) -> None:
    try:
        validate_trade_order(order)
    except PhaseGateError as exc:
        raise ValueError("advisor queue requires a finite, positive trade dollar amount and Direction") from exc


def _validate_approval_attestations(proposal: ProposedTrade) -> None:
    """Verify immutable evidence supports this exact approved order and NAV."""
    fit = proposal.approved_fit
    if fit.order != proposal.order:
        raise ValueError("advisor queue requires approval fit for the exact proposed order")
    if fit.as_of != proposal.approved_on:
        raise ValueError("advisor queue requires approval fit dated on the decision approval date")
    if (fit.pitch_id, fit.brief_id, fit.target_id) != (
        proposal.order.pitch_id,
        proposal.order.brief_id,
        proposal.order.target_id,
    ):
        raise ValueError("advisor queue requires approval fit provenance matching the proposed order")
    sizing = proposal.sizing
    values = (proposal.approval_nav, sizing.confidence, sizing.recommended_weight, sizing.maximum_weight)
    if any(not isfinite(value) for value in values) or proposal.approval_nav <= 0:
        raise ValueError("advisor queue requires finite, positive approval NAV and sizing values")
    if not 0 <= sizing.confidence <= 1 or not 0 < sizing.recommended_weight <= sizing.maximum_weight <= 1:
        raise ValueError("advisor queue requires sizing weights within (0, 1] and recommendation no greater than maximum")
    maximum_dollars = sizing.maximum_weight * proposal.approval_nav
    if proposal.order.dollar_amount > maximum_dollars:
        raise ValueError("advisor queue order exceeds approved sizing maximum")
