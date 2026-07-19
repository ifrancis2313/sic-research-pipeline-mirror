"""Durable advisor workbook for approved, unexecuted SIC trade changes."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from math import isclose, isfinite
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, cast
from zipfile import BadZipFile

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from openpyxl.worksheet.worksheet import Worksheet

from qepm.advisor_queue import execution_status
from qepm.contracts import Holdings, PortfolioFitResult, ProposedTrade, Snapshot
from qepm.governance import exception_matches_fit

__all__ = [
    "PendingTradeReview",
    "AdvisorHandoffDuplicate",
    "AdvisorHandoffRecord",
    "WorkbookRevisionConflict",
    "review_pending_trade",
    "prepare_advisor_handoff",
    "exception_fingerprint",
    "proposal_fingerprint",
    "workbook_revision",
    "write_advisor_workbook",
]

_HISTORY_HEADERS = ("Executed on", "FIGI", "Direction", "Dollar amount", "Executor", "Notes")
_HANDOFF_LEDGER_HEADERS = (
    "Prepared at (UTC)", "Status", "Fingerprint", "Pitch", "Brief", "Target", "FIGI", "Direction",
    "Dollar amount", "Approved on", "Snapshot as of", "Current fit as of", "Reference price",
    "Execution limit", "Fair value per share", "Approval rule", "Approvers", "Prepared by", "Evidence",
)
_EXCEPTION_LOG_HEADERS = (
    "Recorded in workbook at (UTC)", "Status", "Fingerprint", "Pitch", "FIGI", "Direction", "Dollar amount",
    "Snapshot as of", "Hard-limit violations", "Rationale", "Approvers",
)


class WorkbookRevisionConflict(ValueError):
    """Raised instead of overwriting an advisor workbook changed since it was read."""


class AdvisorHandoffDuplicate(ValueError):
    """Raised when an exact approved proposal has already been prepared for an advisor."""


@dataclass(frozen=True)
class AdvisorHandoffRecord:
    """Immutable evidence that one proposal was prepared for the advisor, not executed."""

    fingerprint: str
    prepared_at: datetime
    workbook_path: Path


@dataclass(frozen=True)
class PendingTradeReview:
    """Human-review state for an approved trade that has not yet executed."""

    requires_review: bool
    reasons: tuple[str, ...]


def review_pending_trade(
    proposal: ProposedTrade, snapshot: Snapshot, current_fit: PortfolioFitResult | None = None
) -> PendingTradeReview:
    """Surface actual price/time/fit exceptions; never auto-cancel a trade."""
    reasons: list[str] = []
    status = execution_status(proposal, snapshot.as_of)
    if status.requires_retest:
        reasons.append("30-day-retest-required")
    elif not status.eligible_for_execution:
        reasons.append("execution-status-ineligible")

    if current_fit is None:
        reasons.append("current-portfolio-fit-missing")
    elif (
        current_fit.pitch_id != proposal.order.pitch_id
        or current_fit.brief_id != proposal.order.brief_id
        or current_fit.target_id != proposal.order.target_id
        or current_fit.order != proposal.order
    ):
        reasons.append("current-portfolio-fit-mismatch")
    elif current_fit.as_of != snapshot.as_of:
        reasons.append("current-portfolio-fit-stale")
    elif not current_fit.passed and not exception_matches_fit(proposal.exception, current_fit, proposal.order):
        reasons.append("current-portfolio-fit-failed")
    elif set(current_fit.warnings).difference(proposal.approved_fit.warnings):
        reasons.append("new-portfolio-fit-warning")

    limit = proposal.price_limit
    if limit is None:
        reasons.append("missing-pitch-price-limit")
        return PendingTradeReview(True, tuple(reasons))

    if proposal.order.figi not in snapshot.securities.index or "price" not in snapshot.securities.columns:
        reasons.append("current-price-missing")
        return PendingTradeReview(True, tuple(reasons))

    current_price = snapshot.securities.loc[proposal.order.figi, "price"]
    try:
        current = float(current_price)
    except (TypeError, ValueError):
        reasons.append("current-price-invalid")
        return PendingTradeReview(True, tuple(reasons))
    if not isfinite(current) or current <= 0:
        reasons.append("current-price-invalid")
        return PendingTradeReview(True, tuple(reasons))

    if proposal.order.direction.value == "buy" and current > limit.limit_price:
        reasons.insert(0, "price-above-buy-limit")
    if proposal.order.direction.value == "sell" and current < limit.limit_price:
        reasons.insert(0, "price-below-sell-limit")
    price_move = abs(current / limit.reference_price - 1)
    if limit.material_move_fraction is not None and (
        price_move > limit.material_move_fraction
        or isclose(price_move, limit.material_move_fraction, rel_tol=0.0, abs_tol=1e-12)
    ):
        insert_at = 1 if reasons and reasons[0].startswith("price-") else 0
        reasons.insert(insert_at, "material-price-move")
    return PendingTradeReview(bool(reasons), tuple(reasons))


def write_advisor_workbook(
    path: Path,
    snapshot: Snapshot,
    holdings: Holdings,
    proposed_trades: tuple[ProposedTrade, ...],
    current_fits: Mapping[str, PortfolioFitResult],
    *,
    expected_revision: str | None = None,
) -> Path:
    """Refresh live queue sheets while preserving history and avoiding lost edits.

    Existing workbooks require a revision obtained through
    :func:`workbook_revision`. This optimistic-concurrency check fails closed
    if another user saved the workbook after the caller read it. It is not a
    replacement for serializing simultaneous weekly refreshes.
    """
    if holdings.as_of != snapshot.as_of:
        raise ValueError("holdings and snapshot must use the same as_of date")
    if path.suffix.lower() != ".xlsx":
        raise ValueError(f"advisor workbook path must use a .xlsx extension: {path}")

    if path.exists():
        actual_revision = workbook_revision(path)
        if expected_revision is None:
            raise WorkbookRevisionConflict(
                "existing advisor workbook requires expected_revision; read workbook_revision(path) before refreshing it"
            )
        if expected_revision != actual_revision:
            raise WorkbookRevisionConflict("advisor workbook changed since it was read; reload it before refreshing")
        try:
            workbook = load_workbook(path)
        except (BadZipFile, InvalidFileException, OSError, KeyError) as error:
            raise ValueError(f"advisor workbook is not a readable .xlsx file: {path}") from error
    else:
        if expected_revision is not None:
            raise WorkbookRevisionConflict("advisor workbook does not yet exist; do not supply expected_revision")
        workbook = Workbook()
    if "Sheet" in workbook.sheetnames and len(workbook.sheetnames) == 1:
        del workbook["Sheet"]
    _replace_sheet(workbook, "Run Summary", (("Run field", "Value"), ("As of", snapshot.as_of.isoformat())))
    _replace_sheet(workbook, "Positions", _position_rows(snapshot, holdings))
    _replace_sheet(workbook, "Pending Trades", _pending_rows(snapshot, proposed_trades, current_fits))
    if "Execution History" not in workbook.sheetnames:
        _write_rows(workbook.create_sheet("Execution History"), (_HISTORY_HEADERS,))
    if "Handoff Ledger" not in workbook.sheetnames:
        _write_rows(workbook.create_sheet("Handoff Ledger"), (_HANDOFF_LEDGER_HEADERS,))
    _record_exceptions(workbook, proposed_trades)

    _atomic_save(workbook, path)
    return path


def proposal_fingerprint(proposal: ProposedTrade) -> str:
    """Return a deterministic fingerprint for the immutable approved proposal and order.

    The fingerprint deliberately excludes current market data and preparation time:
    those are recorded separately, while an identical approved proposal must never
    be handed to the advisor twice merely because a later weekly snapshot exists.
    """
    limit = proposal.price_limit
    decision = proposal.decision
    fit = proposal.approved_fit
    evidence = {
        "schema": "sic-advisor-handoff-v1",
        "order": {
            "figi": proposal.order.figi,
            "direction": proposal.order.direction.value,
            "dollar_amount": format(proposal.order.dollar_amount, ".12g"),
            "pitch_id": proposal.order.pitch_id,
            "brief_id": proposal.order.brief_id,
            "target_id": proposal.order.target_id,
        },
        "approved_on": proposal.approved_on.isoformat(),
        "approval_nav": format(proposal.approval_nav, ".12g"),
        "price_limit": None if limit is None else {
            "reference_price": format(limit.reference_price, ".12g"),
            "limit_price": format(limit.limit_price, ".12g"),
            "fair_value_per_share": None if limit.fair_value_per_share is None else format(limit.fair_value_per_share, ".12g"),
            "material_move_fraction": None if limit.material_move_fraction is None else format(limit.material_move_fraction, ".12g"),
            "rationale": limit.rationale,
        },
        "decision": None if decision is None else {
            "pitch_id": decision.pitch_id, "approved": decision.approved,
            "decided_on": decision.decided_on.isoformat(), "approvers": decision.approvers,
            "ordinary_rule_id": decision.ordinary_rule_id,
        },
        "exception": None if proposal.exception is None else {
            "fingerprint": exception_fingerprint(proposal),
            "as_of": proposal.exception.as_of.isoformat(),
            "hard_limit_violations": proposal.exception.hard_limit_violations,
            "rationale": proposal.exception.rationale,
            "approvers": proposal.exception.approvers,
        },
        "approved_fit": {
            "pitch_id": fit.pitch_id, "brief_id": fit.brief_id, "target_id": fit.target_id,
            "as_of": fit.as_of.isoformat(), "passed": fit.passed, "requires_exception": fit.requires_exception,
            "hard_limit_violations": fit.hard_limit_violations, "warnings": fit.warnings, "notes": fit.notes,
        },
    }
    serialized = json.dumps(evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(serialized.encode("utf-8")).hexdigest()


def exception_fingerprint(proposal: ProposedTrade) -> str | None:
    """Return a stable ledger identity for the proposal's structured exception."""
    record = proposal.exception
    if record is None:
        return None
    evidence = {
        "schema": "sic-hard-limit-exception-v1",
        "order": {
            "figi": record.order.figi, "direction": record.order.direction.value,
            "dollar_amount": format(record.order.dollar_amount, ".12g"), "pitch_id": record.order.pitch_id,
            "brief_id": record.order.brief_id, "target_id": record.order.target_id,
        },
        "as_of": record.as_of.isoformat(), "hard_limit_violations": record.hard_limit_violations,
        "rationale": record.rationale, "approvers": record.approvers,
    }
    return sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def prepare_advisor_handoff(
    path: Path,
    proposal: ProposedTrade,
    snapshot: Snapshot,
    current_fit: PortfolioFitResult,
    *,
    expected_revision: str,
    prepared_by: str,
) -> AdvisorHandoffRecord:
    """Atomically record one governed advisor handoff in the configured workbook.

    This deliberately records *prepared_for_advisor*, not an execution, fill,
    cancellation, or exception decision. The manual Execution History sheet is
    preserved for the advisor/PM workflow to enter confirmed fills later.
    """
    if not prepared_by.strip():
        raise ValueError("advisor handoff requires the non-blank operator who prepared it")
    if path.suffix.lower() != ".xlsx":
        raise ValueError(f"advisor workbook path must use a .xlsx extension: {path}")
    if not path.exists():
        raise ValueError("advisor workbook must be refreshed before preparing a live advisor handoff")
    actual_revision = workbook_revision(path)
    if expected_revision != actual_revision:
        raise WorkbookRevisionConflict("advisor workbook changed since it was read; reload it before preparing a handoff")
    try:
        workbook = load_workbook(path)
    except (BadZipFile, InvalidFileException, OSError, KeyError) as error:
        raise ValueError(f"advisor workbook is not a readable .xlsx file: {path}") from error
    if "Handoff Ledger" not in workbook.sheetnames:
        _write_rows(workbook.create_sheet("Handoff Ledger"), (_HANDOFF_LEDGER_HEADERS,))

    fingerprint = proposal_fingerprint(proposal)
    ledger = workbook["Handoff Ledger"]
    if any(row[2].value == fingerprint for row in ledger.iter_rows(min_row=2)):
        raise AdvisorHandoffDuplicate("this exact approved proposal was already prepared for advisor handoff")

    prepared_at = datetime.now(UTC)
    limit = proposal.price_limit
    decision = proposal.decision
    ledger.append((
        prepared_at.isoformat(), "prepared_for_advisor", fingerprint,
        proposal.order.pitch_id, proposal.order.brief_id, proposal.order.target_id,
        proposal.order.figi, proposal.order.direction.value, proposal.order.dollar_amount,
        proposal.approved_on.isoformat(), snapshot.as_of.isoformat(), current_fit.as_of.isoformat(),
        limit.reference_price if limit else None, limit.limit_price if limit else None,
        limit.fair_value_per_share if limit else None,
        decision.ordinary_rule_id if decision else None,
        ", ".join(decision.approvers) if decision else None,
        prepared_by,
        json.dumps({
            "approved_fit_passed": proposal.approved_fit.passed,
            "approved_fit_as_of": proposal.approved_fit.as_of.isoformat(),
            "current_fit_passed": current_fit.passed,
            "current_fit_warnings": current_fit.warnings,
            "price_rationale": limit.rationale if limit else None,
            "exception_fingerprint": exception_fingerprint(proposal),
        }, sort_keys=True),
    ))
    _atomic_save(workbook, path)
    return AdvisorHandoffRecord(fingerprint, prepared_at, path)


def workbook_revision(path: Path) -> str:
    """Return the content revision of an existing readable advisor workbook."""
    if path.suffix.lower() != ".xlsx":
        raise ValueError(f"advisor workbook path must use a .xlsx extension: {path}")
    try:
        contents = path.read_bytes()
        # A hash alone is not enough: only a readable workbook may be safely
        # preserved during a future refresh.
        check = load_workbook(path, read_only=True)
        check.close()
    except (BadZipFile, InvalidFileException, OSError, KeyError) as error:
        raise ValueError(f"advisor workbook is not a readable .xlsx file: {path}") from error
    return sha256(contents).hexdigest()


def _position_rows(snapshot: Snapshot, holdings: Holdings) -> tuple[tuple[object, ...], ...]:
    rows: list[tuple[object, ...]] = [("FIGI", "Current price", "Dollar value")]
    for figi, position in holdings.positions.iterrows():
        security = snapshot.securities.loc[figi] if figi in snapshot.securities.index else pd.Series(dtype=object)
        price = security.get("price", None)
        rows.append((figi, _finite_price_or_none(price), float(position["dollar_value"])))
    return tuple(rows)


def _finite_price_or_none(value: object) -> float | None:
    """Keep missing/non-finite vendor values out of a human-facing price cell."""
    try:
        price = float(cast(Any, value))
    except (TypeError, ValueError):
        return None
    return price if isfinite(price) else None


def _pending_rows(
    snapshot: Snapshot, proposals: tuple[ProposedTrade, ...], current_fits: Mapping[str, PortfolioFitResult]
) -> tuple[tuple[object, ...], ...]:
    rows: list[tuple[object, ...]] = [
        (
            "Pitch", "FIGI", "Direction", "Dollar amount", "Approved on", "Reference price", "Execution limit",
            "Material move threshold", "Current price", "Fair value per share", "Review status", "Price rationale",
        )
    ]
    for proposal in proposals:
        limit = proposal.price_limit
        review = review_pending_trade(proposal, snapshot, current_fits.get(proposal.order.pitch_id))
        eligibility = execution_status(proposal, snapshot.as_of)
        status = "review: " + "; ".join(review.reasons) if review.requires_review else "current: eligible for execution"
        if not eligibility.eligible_for_execution and not review.requires_review:
            status = "ineligible: " + eligibility.reason
        rows.append((
            proposal.order.pitch_id,
            proposal.order.figi,
            proposal.order.direction.value,
            proposal.order.dollar_amount,
            proposal.approved_on.isoformat(),
            limit.reference_price if limit else None,
            limit.limit_price if limit else None,
            limit.material_move_fraction if limit else None,
            _finite_price_or_none(snapshot.securities.loc[proposal.order.figi, "price"])
            if proposal.order.figi in snapshot.securities.index and "price" in snapshot.securities.columns else None,
            limit.fair_value_per_share if limit else None,
            status,
            limit.rationale if limit else None,
        ))
    return tuple(rows)


def _record_exceptions(workbook: Workbook, proposals: tuple[ProposedTrade, ...]) -> None:
    """Append each structured exception once; never replace the human audit trail."""
    if "Exception Log" not in workbook.sheetnames:
        _write_rows(workbook.create_sheet("Exception Log"), (_EXCEPTION_LOG_HEADERS,))
    log = workbook["Exception Log"]
    known = {row[2].value for row in log.iter_rows(min_row=2) if row[2].value}
    recorded_at = datetime.now(UTC).isoformat()
    for proposal in proposals:
        record = proposal.exception
        fingerprint = exception_fingerprint(proposal)
        if record is None or fingerprint is None or fingerprint in known:
            continue
        log.append((
            recorded_at, "approved_hard_limit_exception", fingerprint, proposal.order.pitch_id,
            record.order.figi, record.order.direction.value, record.order.dollar_amount, record.as_of.isoformat(),
            "; ".join(record.hard_limit_violations), record.rationale, ", ".join(record.approvers),
        ))
        known.add(fingerprint)


def _replace_sheet(workbook: Workbook, title: str, rows: tuple[tuple[object, ...], ...]) -> None:
    if title in workbook.sheetnames:
        del workbook[title]
    _write_rows(workbook.create_sheet(title), rows)


def _write_rows(sheet: Worksheet, rows: tuple[tuple[object, ...], ...]) -> None:
    for row in rows:
        sheet.append(row)


def _atomic_save(workbook: Workbook, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, suffix=".xlsx", delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        workbook.save(temporary_path)
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
