import pytest

from qepm.contracts import FactorChangeProposal
from qepm.factor_governance import validate_factor_change


def test_factor_change_requires_report_validation_and_all_four_approvals(tmp_path):
    report = tmp_path / "quality-v2.md"
    report.write_text("# Quality v2\n", encoding="utf-8")
    proposal = FactorChangeProposal(
        "quality", str(report), True, ("PM", "Board Chair", "Lead Analyst", "Faculty Advisor"),
        theory="Economic profitability persists.", exact_definition="Gross profit/assets.",
        point_in_time_treatment="Use only filings available at the Friday snapshot.",
        limitations="Accounting comparability varies.", expected_portfolio_effect="Increase quality exposure.",
    )
    validate_factor_change(proposal)

    missing_advisor = FactorChangeProposal(
        "quality", str(report), True, ("PM", "Board Chair", "Lead Analyst"),
        theory="Economic profitability persists.", exact_definition="Gross profit/assets.",
        point_in_time_treatment="Use only filings available at the Friday snapshot.",
        limitations="Accounting comparability varies.", expected_portfolio_effect="Increase quality exposure.",
    )
    with pytest.raises(ValueError, match="requires PM"):
        validate_factor_change(missing_advisor)


def test_factor_change_rejects_an_unattached_or_pitch_driven_report(tmp_path):
    proposal = FactorChangeProposal(
        "quality", "research/quality-v2.md", True, ("PM", "Board Chair", "Lead Analyst", "Faculty Advisor"),
        theory="Economic profitability persists.", exact_definition="Gross profit/assets.",
        point_in_time_treatment="Use only filings available at the Friday snapshot.",
        limitations="Accounting comparability varies.", expected_portfolio_effect="Increase quality exposure.",
    )
    with pytest.raises(ValueError, match="attached"):
        validate_factor_change(proposal)

    report = tmp_path / "quality-v2.md"
    report.write_text("# Quality v2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="independent"):
        validate_factor_change(
            FactorChangeProposal(
                **{**proposal.__dict__, "research_report_path": str(report), "triggering_pitch_id": "PITCH-1"}
            )
        )
