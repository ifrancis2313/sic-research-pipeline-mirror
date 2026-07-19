from dataclasses import replace

import pytest

from qepm.contracts import FactorChangeProposal
from qepm.factor_registry import FactorRegistry
from qepm.factor_registry.stub_factors import STUB_MOMENTUM


def _approved_proposal(report_path: str, *, factor_name: str = "momentum") -> FactorChangeProposal:
    return FactorChangeProposal(
        factor_name=factor_name,
        research_report_path=report_path,
        independently_validated=True,
        approvals=("PM", "Board Chair", "Lead Analyst", "Faculty Advisor"),
        theory="Momentum can improve research prioritization.",
        exact_definition="Twelve-minus-one price momentum percentile.",
        point_in_time_treatment="Use only prices available by the Friday snapshot.",
        limitations="Momentum can reverse sharply.",
        expected_portfolio_effect="Increase measured momentum exposure.",
        proposed_definition=replace(STUB_MOMENTUM, weight=0.5),
    )


def test_registry_amendment_requires_a_validated_proposal_for_the_same_factor(tmp_path):
    report = tmp_path / "momentum-v2.md"
    report.write_text("# Momentum v2\n", encoding="utf-8")
    registry = FactorRegistry()
    registry.register(STUB_MOMENTUM)

    registry.amend("momentum", _approved_proposal(str(report)))

    assert registry.get("momentum").weight == 0.5

    with pytest.raises(ValueError, match="does not match"):
        registry.amend("momentum", _approved_proposal(str(report), factor_name="value"))


def test_registry_rejects_unbound_or_mismatched_definition_changes(tmp_path):
    report = tmp_path / "momentum-v2.md"
    report.write_text("# Momentum v2\n", encoding="utf-8")
    registry = FactorRegistry()
    registry.register(STUB_MOMENTUM)

    unbound = replace(_approved_proposal(str(report)), proposed_definition=None)
    with pytest.raises(ValueError, match="exact proposed definition"):
        registry.amend("momentum", unbound)

    wrong_name = replace(_approved_proposal(str(report)), proposed_definition=replace(STUB_MOMENTUM, name="value"))
    with pytest.raises(ValueError, match="does not match amendment target"):
        registry.amend("momentum", wrong_name)


@pytest.mark.parametrize("weight", [-0.01, float("inf"), float("-inf"), float("nan")])
def test_registry_rejects_nonfinite_or_negative_weights(weight):
    registry = FactorRegistry()
    with pytest.raises(ValueError, match="finite and non-negative"):
        registry.register(replace(STUB_MOMENTUM, weight=weight))


def test_registry_rejects_duplicate_registration_instead_of_overwriting_an_adopted_factor():
    registry = FactorRegistry()
    registry.register(STUB_MOMENTUM)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(STUB_MOMENTUM)
