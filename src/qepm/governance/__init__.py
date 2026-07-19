"""Governance validation for configurable ordinary decisions and fixed exceptions."""

from __future__ import annotations

from qepm.contracts import DecisionRecord, ExceptionRecord, GovernancePolicy, PortfolioFitResult, TradeOrder

__all__ = [
    "DEFAULT_GOVERNANCE_POLICY", "DEFAULT_ORDINARY_RULE_ID", "validate_decision_record",
    "validate_exception_record", "exception_matches_fit",
]

DEFAULT_GOVERNANCE_POLICY = GovernancePolicy()
DEFAULT_ORDINARY_RULE_ID = DEFAULT_GOVERNANCE_POLICY.ordinary_rule_id


def validate_decision_record(record: DecisionRecord, policy: GovernancePolicy = DEFAULT_GOVERNANCE_POLICY) -> None:
    """Validate a recorded decision against the supplied ordinary-governance policy."""
    _validate_policy(policy)
    _validate_approvers(record)
    if record.ordinary_rule_id != policy.ordinary_rule_id:
        raise ValueError("ordinary_rule_id must identify the approved Eboard decision procedure")
    if record.approved and (
        policy.chair not in record.approvers or not set(policy.ordinary_alternatives).intersection(record.approvers)
    ):
        raise ValueError(f"an ordinary approval requires {policy.chair} plus an ordinary governance voice")


def validate_exception_record(record: ExceptionRecord, policy: GovernancePolicy = DEFAULT_GOVERNANCE_POLICY) -> None:
    """Validate the human-entered evidence for a hard-limit exception."""
    _validate_policy(policy)
    if not record.rationale.strip():
        raise ValueError("exception rationale must be non-blank")
    if not record.hard_limit_violations or any(not violation.strip() for violation in record.hard_limit_violations):
        raise ValueError("exception must name one or more non-blank hard-limit violations")
    if len(record.hard_limit_violations) != len(set(record.hard_limit_violations)):
        raise ValueError("exception hard-limit violations cannot contain duplicates")
    _validate_approvers_values(record.approvers, "exception")
    if policy.chair not in record.approvers or not set(policy.exception_alternatives).intersection(record.approvers):
        raise ValueError(f"an exception requires {policy.chair} plus an exception governance voice")


def exception_matches_fit(record: ExceptionRecord | None, fit: PortfolioFitResult, order: TradeOrder) -> bool:
    """True only when a valid exception names this exact failed-fit evidence."""
    if record is None:
        return False
    try:
        validate_exception_record(record)
    except ValueError:
        return False
    return (
        record.order == order
        and record.as_of == fit.as_of
        and record.hard_limit_violations == fit.hard_limit_violations
        and bool(fit.hard_limit_violations)
    )


def _validate_policy(policy: GovernancePolicy) -> None:
    """Reject ambiguous role definitions before evaluating a quorum."""
    role_groups = (policy.ordinary_alternatives, policy.exception_alternatives)
    roles = (policy.chair, *policy.ordinary_alternatives, *policy.exception_alternatives)
    if not all(isinstance(role, str) and role.strip() for role in roles):
        raise ValueError("governance policy roles must be non-blank strings")
    if any(len(group) != len(set(group)) for group in role_groups):
        raise ValueError("governance policy alternatives cannot contain duplicate roles")
    if any(policy.chair in group for group in role_groups):
        raise ValueError("governance policy chair cannot also be an alternative")


def _validate_approvers(record: DecisionRecord) -> None:
    _validate_approvers_values(record.approvers, "decision")


def _validate_approvers_values(approvers: tuple[str, ...], label: str) -> None:
    if not all(isinstance(approver, str) and approver.strip() for approver in approvers):
        raise ValueError(f"{label} approvers must be non-blank strings")
    if len(approvers) != len(set(approvers)):
        raise ValueError(f"{label} approvers cannot contain duplicates")
