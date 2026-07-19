"""Ownership and inherited-holding review controls."""

from __future__ import annotations

from datetime import date

from qepm.contracts import HoldingOwnership

__all__ = ["ownership_refresh_due", "validate_holding_ownership"]


def validate_holding_ownership(record: HoldingOwnership) -> None:
    """Ensure every non-core holding has a pod and inherited positions receive review."""
    if record.sleeve not in {"active", "experimental"}:
        raise ValueError("holding ownership only applies to active or experimental sleeves")
    if not record.pod.strip():
        raise ValueError("an active or experimental holding requires a pod owner")
    if record.inherited and not record.legacy_review_complete:
        raise ValueError("an inherited holding requires a legacy review before ownership is complete")


def ownership_refresh_due(record: HoldingOwnership, as_of: date) -> tuple[str, ...]:
    """Return the recorded ownership reviews due at the weekly review date.

    Earnings dates come from the eventual data/calendar source, so V1 records whether
    the latest earnings review occurred. Quarterly review is enforceable locally at
    a 90-day maximum interval.
    """
    due: list[str] = []
    if record.last_earnings_review is None:
        due.append("earnings-review-unrecorded")
    if record.last_quarterly_review is None or (as_of - record.last_quarterly_review).days > 90:
        due.append("quarterly-review-due")
    return tuple(due)
