"""Four-person evidence gate for live factor-methodology changes."""

from __future__ import annotations

from pathlib import Path

from qepm.contracts import FactorChangeProposal

__all__ = ["validate_factor_change"]

_REQUIRED_APPROVERS = {"PM", "Board Chair", "Lead Analyst", "Faculty Advisor"}


def validate_factor_change(proposal: FactorChangeProposal) -> None:
    """Reject a factor change until the complete agreed evidence gate is satisfied."""
    if not proposal.research_report_path.strip():
        raise ValueError("factor change requires a substantive research report")
    if not Path(proposal.research_report_path).is_file():
        raise ValueError("factor change requires a locally attached research report")
    if proposal.triggering_pitch_id is not None:
        raise ValueError("factor changes require independent methodology research, not a live pitch")
    if not proposal.independently_validated:
        raise ValueError("factor change requires independent validation")
    required_evidence = {
        "theory": proposal.theory,
        "exact definition": proposal.exact_definition,
        "point-in-time treatment": proposal.point_in_time_treatment,
        "limitations": proposal.limitations,
        "expected portfolio effect": proposal.expected_portfolio_effect,
    }
    missing = [label for label, value in required_evidence.items() if not value.strip()]
    if missing:
        raise ValueError(f"factor change report is incomplete: {', '.join(missing)}")
    if not _REQUIRED_APPROVERS.issubset(proposal.approvals):
        raise ValueError("factor change requires PM, Board Chair, Lead Analyst, and Faculty Advisor approval")
