"""Time-based status recommendations for the rolling research-brief queue."""

from __future__ import annotations

from datetime import date

from qepm.contracts import ResearchBrief

__all__ = ["advance_lifecycle", "lifecycle_action"]


def lifecycle_action(brief: ResearchBrief, as_of: date, meetings_without_update: int = 0) -> str:
    """Return the required PM action without silently changing a student's assignment."""
    if brief.claimed_on is None:
        return "available"
    if meetings_without_update >= 2:
        return "release"
    age_days = (as_of - brief.claimed_on).days
    if age_days >= 28:
        return "pitch-extend-narrow-or-release"
    if age_days >= 14:
        return "progress-check"
    return "in-progress"


def advance_lifecycle(brief: ResearchBrief, as_of: date, meetings_without_update: int = 0) -> str:
    """Apply non-investment brief queue transitions; trade approval stays separate."""
    action = lifecycle_action(brief, as_of, meetings_without_update)
    if action == "in-progress":
        brief.status = "in-progress"
    elif action == "release":
        brief.status = "released"
        brief.assigned_pods.clear()
        brief.claimed_on = None
    elif action == "pitch-extend-narrow-or-release":
        brief.status = "expired"
    return action
