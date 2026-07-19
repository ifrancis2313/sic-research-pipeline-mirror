from datetime import date

import pytest

from qepm.contracts import (
    DecisionRecord,
    Direction,
    ExceptionRecord,
    GovernancePolicy,
    TradeOrder,
)
from qepm.governance import (
    DEFAULT_ORDINARY_RULE_ID,
    validate_decision_record,
    validate_exception_record,
)

_ORDER = TradeOrder("FIGI", Direction.BUY, 1_000.0, "P", "B", "T")


def test_exception_requires_chair_plus_one_designated_governance_voice():
    valid = ExceptionRecord(_ORDER, date(2026, 7, 17), ("name-cap",), "Documented reason.", ("Board Chair", "Lead Analyst"))
    validate_exception_record(valid)

    invalid = ExceptionRecord(_ORDER, date(2026, 7, 17), ("name-cap",), "Documented reason.", ("PM", "Lead Analyst"))
    with pytest.raises(ValueError, match="requires Board Chair"):
        validate_exception_record(invalid)


@pytest.mark.parametrize("blank_rationale", ["", "   ", "\t\n"])
def test_exception_rejects_a_blank_rationale(blank_rationale):
    record = ExceptionRecord(_ORDER, date(2026, 7, 17), ("name-cap",), blank_rationale, ("Board Chair", "PM"))

    with pytest.raises(ValueError, match="rationale"):
        validate_exception_record(record)


def test_exception_rejects_an_empty_violations_tuple():
    record = ExceptionRecord(_ORDER, date(2026, 7, 17), (), "Documented reason.", ("Board Chair", "PM"))

    with pytest.raises(ValueError, match="hard-limit violation"):
        validate_exception_record(record)


def test_exception_rejects_a_blank_violation_entry():
    record = ExceptionRecord(_ORDER, date(2026, 7, 17), ("name-cap", "  "), "Documented reason.", ("Board Chair", "PM"))

    with pytest.raises(ValueError, match="hard-limit violation"):
        validate_exception_record(record)


def test_exception_rejects_duplicate_violation_entries():
    record = ExceptionRecord(
        _ORDER, date(2026, 7, 17), ("name-cap", "name-cap"), "Documented reason.", ("Board Chair", "PM")
    )

    with pytest.raises(ValueError, match="duplicate"):
        validate_exception_record(record)


def test_ordinary_approval_requires_chair_plus_pm_or_lead_analyst():
    valid = DecisionRecord("P", True, date(2026, 7, 17), ("Board Chair", "PM"), DEFAULT_ORDINARY_RULE_ID)
    validate_decision_record(valid)

    invalid = DecisionRecord("P", True, date(2026, 7, 17), ("PM",), DEFAULT_ORDINARY_RULE_ID)
    with pytest.raises(ValueError, match="ordinary approval"):
        validate_decision_record(invalid)


def test_exception_allows_chair_plus_advisor():
    validate_exception_record(ExceptionRecord(_ORDER, date(2026, 7, 17), ("name-cap",), "Documented reason.", ("Board Chair", "Faculty Advisor")))


def test_ordinary_rule_can_be_changed_through_an_explicit_policy():
    policy = GovernancePolicy(ordinary_rule_id="chair-plus-pm-v2", ordinary_alternatives=("PM",))
    validate_decision_record(
        DecisionRecord("P", True, date(2026, 7, 17), ("Board Chair", "PM"), "chair-plus-pm-v2"), policy
    )


@pytest.mark.parametrize(
    "policy",
    (
        GovernancePolicy(chair=""),
        GovernancePolicy(ordinary_alternatives=("PM", "PM")),
        GovernancePolicy(exception_alternatives=("PM", "", "Faculty Advisor")),
        GovernancePolicy(ordinary_alternatives=("Board Chair", "PM")),
        GovernancePolicy(exception_alternatives=("PM", "Board Chair")),
    ),
)
def test_policy_rejects_blank_duplicate_or_chair_duplicated_roles(policy):
    with pytest.raises(ValueError, match="governance policy"):
        validate_decision_record(
            DecisionRecord("P", True, date(2026, 7, 17), ("Board Chair", "PM"), policy.ordinary_rule_id), policy
        )


@pytest.mark.parametrize("approvers", (("Board Chair", ""), ("Board Chair", "PM", "PM")))
def test_decision_rejects_blank_or_duplicate_approvers(approvers):
    with pytest.raises(ValueError, match="approvers"):
        validate_decision_record(
            DecisionRecord("P", True, date(2026, 7, 17), approvers, DEFAULT_ORDINARY_RULE_ID)
        )
