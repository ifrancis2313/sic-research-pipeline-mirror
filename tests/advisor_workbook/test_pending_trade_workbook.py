from dataclasses import replace
from datetime import date

import pandas as pd
import pytest
from openpyxl import Workbook, load_workbook

from qepm.advisor_workbook import (
    WorkbookRevisionConflict,
    review_pending_trade,
    workbook_revision,
    write_advisor_workbook,
)
from qepm.contracts import (
    DecisionRecord,
    Direction,
    ExceptionRecord,
    ExecutionPriceLimit,
    Holdings,
    PortfolioFitResult,
    PortfolioPolicy,
    ProposedTrade,
    SizingRecommendation,
    Snapshot,
    TradeOrder,
)


def _proposal(*, approved_on: date = date(2026, 7, 1), limit: float = 100.0, material_move_fraction: float = 0.10) -> ProposedTrade:
    order = TradeOrder("FIGI", Direction.BUY, 3_000, "PITCH", "BRIEF", "TARGET")
    return ProposedTrade(
        order=order,
        approved_on=approved_on,
        pitch_ready=True,
        approved_fit=PortfolioFitResult("PITCH", "BRIEF", "TARGET", approved_on, True, False, {}, {}, order=order),
        sizing=SizingRecommendation(0.8, 0.03, 0.03, False, False),
        approval_nav=100_000.0,
        decision=DecisionRecord("PITCH", True, approved_on, ("Board Chair", "PM"), "chair-plus-pm-or-lead-v1"),
        price_limit=ExecutionPriceLimit(
            reference_price=95.0,
            limit_price=limit,
            rationale="DCF base case supports buying below the approved ceiling.",
            fair_value_per_share=120.0,
            material_move_fraction=material_move_fraction,
        ),
    )


def _snapshot(as_of: date, price: object) -> Snapshot:
    return Snapshot(as_of, pd.DataFrame({"price": [price]}, index=["FIGI"]), pd.DataFrame())


def _fit(*, as_of: date = date(2026, 7, 18), passed: bool = True) -> PortfolioFitResult:
    return PortfolioFitResult(
        "PITCH", "BRIEF", "TARGET", as_of, passed, False, {}, {},
        order=TradeOrder("FIGI", Direction.BUY, 3_000, "PITCH", "BRIEF", "TARGET"),
    )


def test_pending_trade_review_requires_human_recheck_only_for_detected_exceptions():
    review = review_pending_trade(_proposal(), _snapshot(date(2026, 7, 18), 112.0), _fit())

    assert review.requires_review is True
    assert review.reasons == (
        "price-above-buy-limit",
        "material-price-move",
    )


def test_pending_trade_review_flags_a_current_fit_failure_but_not_a_current_fit_pass():
    proposal = _proposal(material_move_fraction=0.20)
    snapshot = _snapshot(date(2026, 7, 18), 98.0)

    assert review_pending_trade(proposal, snapshot, _fit()).requires_review is False
    assert review_pending_trade(proposal, snapshot, _fit(passed=False)).reasons == ("current-portfolio-fit-failed",)


def test_pending_trade_review_only_escalates_new_current_fit_warnings():
    proposal = _proposal(material_move_fraction=0.20)
    proposal = replace(proposal, approved_fit=PortfolioFitResult(
        "PITCH", "BRIEF", "TARGET", proposal.approved_on, True, False, {}, {}, warnings=("beta-warning",), order=proposal.order,
    ))
    snapshot = _snapshot(date(2026, 7, 18), 98.0)
    unchanged = PortfolioFitResult("PITCH", "BRIEF", "TARGET", snapshot.as_of, True, False, {}, {}, warnings=("beta-warning",), order=proposal.order)
    new_warning = PortfolioFitResult("PITCH", "BRIEF", "TARGET", snapshot.as_of, True, False, {}, {}, warnings=("beta-warning", "factor-fit-warning"), order=proposal.order)

    assert review_pending_trade(proposal, snapshot, unchanged).requires_review is False
    assert review_pending_trade(proposal, snapshot, new_warning).reasons == ("new-portfolio-fit-warning",)


def test_pending_trade_review_flags_fit_evidence_from_another_snapshot():
    review = review_pending_trade(_proposal(), _snapshot(date(2026, 7, 18), 98.0), _fit(as_of=date(2026, 7, 11)))

    assert review.reasons == ("current-portfolio-fit-stale",)


@pytest.mark.parametrize(
    ("direction", "price"),
    ((Direction.BUY, 104.5), (Direction.SELL, 85.5)),
)
def test_pending_trade_review_flags_the_exact_ten_percent_boundary_in_either_direction(
    direction: Direction, price: float,
):
    proposal = _proposal(limit=110.0)
    order = replace(proposal.order, direction=direction)
    if direction is Direction.SELL:
        proposal = replace(proposal, price_limit=replace(proposal.price_limit, limit_price=80.0))
    proposal = replace(proposal, order=order, approved_fit=replace(proposal.approved_fit, order=order))
    fit = replace(_fit(), order=order)

    assert review_pending_trade(proposal, _snapshot(date(2026, 7, 18), price), fit).reasons == ("material-price-move",)


def test_pending_trade_review_does_not_flag_a_9_99_percent_move():
    proposal = _proposal(limit=110.0)

    assert review_pending_trade(proposal, _snapshot(date(2026, 7, 18), 104.4905), _fit()).requires_review is False


def test_workbook_only_reviews_trades_still_in_the_pending_queue(tmp_path):
    workbook_path = tmp_path / "SIC Advisor Queue.xlsx"
    snapshot = _snapshot(date(2026, 7, 18), 120.0)
    holdings = Holdings(snapshot.as_of, pd.DataFrame({"dollar_value": [10_500.0]}, index=["FIGI"]))

    write_advisor_workbook(workbook_path, snapshot, holdings, (), {})

    assert load_workbook(workbook_path)["Pending Trades"].max_row == 1


def test_admission_freezes_policy_threshold_and_later_policy_changes_only_affect_new_approvals():
    from qepm.advisor_queue import admit_proposed_trade

    draft = _proposal(material_move_fraction=None)
    first = admit_proposed_trade(draft, PortfolioPolicy(portfolio_nav=100_000.0, material_price_move_fraction=0.10))
    second = admit_proposed_trade(draft, PortfolioPolicy(portfolio_nav=100_000.0, material_price_move_fraction=0.20))

    assert first.price_limit is not None and first.price_limit.material_move_fraction == 0.10
    assert second.price_limit is not None and second.price_limit.material_move_fraction == 0.20
    # Existing evidence remains usable as-is; it must not be rewritten by a
    # later policy setting during weekly checks or advisor handoff.
    assert first.price_limit.material_move_fraction == 0.10


def test_admission_rejects_a_draft_without_a_frozen_threshold_when_policy_is_not_supplied():
    from qepm.advisor_queue import admit_proposed_trade

    with pytest.raises(ValueError, match="material price-move threshold frozen at approval"):
        admit_proposed_trade(_proposal(material_move_fraction=None))


@pytest.mark.parametrize("price", [float("nan"), float("inf"), float("-inf"), 0.0, -1.0, "not-a-price"])
def test_pending_trade_review_fails_closed_for_missing_or_nonfinite_current_prices(price: object):
    review = review_pending_trade(
        _proposal(), _snapshot(date(2026, 7, 18), price), _fit()
    )

    assert review.requires_review is True
    assert review.reasons == ("current-price-invalid",)


def test_workbook_reuses_one_path_and_preserves_execution_history(tmp_path):
    workbook_path = tmp_path / "SIC Advisor Queue.xlsx"
    holdings = Holdings(date(2026, 7, 18), pd.DataFrame({"dollar_value": [10_500.0]}, index=["FIGI"]))

    write_advisor_workbook(workbook_path, _snapshot(date(2026, 7, 18), 105.0), holdings, (_proposal(),), {"PITCH": _fit()})
    first = load_workbook(workbook_path)
    assert first.sheetnames == ["Run Summary", "Positions", "Pending Trades", "Execution History", "Handoff Ledger", "Exception Log"]
    assert first["Positions"]["A2"].value == "FIGI"
    assert first["Pending Trades"]["K2"].value == "review: price-above-buy-limit; material-price-move"
    assert first["Pending Trades"]["J2"].value == 120.0

    first["Execution History"].append(["2026-07-18", "FIGI", "buy", 3_000.0, "Faculty Advisor", "executed"])
    first.save(workbook_path)

    updated_holdings = Holdings(date(2026, 7, 25), holdings.positions)
    write_advisor_workbook(
        workbook_path, _snapshot(date(2026, 7, 25), 98.0), updated_holdings, (), {},
        expected_revision=workbook_revision(workbook_path),
    )
    second = load_workbook(workbook_path)
    assert second["Run Summary"]["B2"].value == "2026-07-25"
    assert second["Pending Trades"].max_row == 1
    assert second["Execution History"]["A2"].value == "2026-07-18"
    assert [cell.value for cell in second["Positions"][1]] == ["FIGI", "Current price", "Dollar value"]


def test_workbook_preserves_a_structured_exception_log_across_refreshes(tmp_path):
    workbook_path = tmp_path / "SIC Advisor Queue.xlsx"
    snapshot = _snapshot(date(2026, 7, 18), 98.0)
    holdings = Holdings(snapshot.as_of, pd.DataFrame({"dollar_value": [10_500.0]}, index=["FIGI"]))
    proposal = _proposal()
    proposal = replace(
        proposal,
        approved_fit=replace(
            proposal.approved_fit, passed=False, requires_exception=True, hard_limit_violations=("name-cap",),
        ),
        exception=ExceptionRecord(
            proposal.order, proposal.approved_on, ("name-cap",), "Temporary concentration is documented.", ("Board Chair", "Faculty Advisor"),
        ),
    )

    write_advisor_workbook(workbook_path, snapshot, holdings, (proposal,), {"PITCH": _fit()})
    first = load_workbook(workbook_path)
    assert first["Exception Log"]["I2"].value == "name-cap"
    assert first["Exception Log"]["J2"].value == "Temporary concentration is documented."

    first["Exception Log"].append(["manual", "note", "manual-entry"])
    first.save(workbook_path)
    write_advisor_workbook(
        workbook_path, snapshot, holdings, (proposal,), {"PITCH": _fit()},
        expected_revision=workbook_revision(workbook_path),
    )
    second = load_workbook(workbook_path)
    assert second["Exception Log"].max_row == 3
    assert second["Exception Log"]["C3"].value == "manual-entry"


def test_workbook_never_marks_an_execution_ineligible_trade_as_eligible(tmp_path):
    workbook_path = tmp_path / "SIC Advisor Queue.xlsx"
    proposal = _proposal()
    snapshot = _snapshot(date(2026, 6, 30), 95.0)
    holdings = Holdings(snapshot.as_of, pd.DataFrame({"dollar_value": [10_500.0]}, index=["FIGI"]))

    write_advisor_workbook(workbook_path, snapshot, holdings, (proposal,), {"PITCH": _fit(as_of=snapshot.as_of)})

    workbook = load_workbook(workbook_path)
    assert workbook["Pending Trades"]["K2"].value == "review: execution-status-ineligible"


def test_existing_workbook_requires_a_matching_revision_and_never_overwrites_human_edit(tmp_path):
    workbook_path = tmp_path / "SIC Advisor Queue.xlsx"
    snapshot = _snapshot(date(2026, 7, 18), 98.0)
    holdings = Holdings(snapshot.as_of, pd.DataFrame({"dollar_value": [10_500.0]}, index=["FIGI"]))
    write_advisor_workbook(workbook_path, snapshot, holdings, (), {})
    revision_before_human_edit = workbook_revision(workbook_path)

    human = load_workbook(workbook_path)
    human["Execution History"].append(["2026-07-18", "FIGI", "buy", 3_000.0, "Faculty Advisor", "executed"])
    human.save(workbook_path)

    with pytest.raises(WorkbookRevisionConflict, match="changed since it was read"):
        write_advisor_workbook(
            workbook_path, snapshot, holdings, (), {}, expected_revision=revision_before_human_edit
        )
    assert load_workbook(workbook_path)["Execution History"]["A2"].value == "2026-07-18"

    with pytest.raises(WorkbookRevisionConflict, match="requires expected_revision"):
        write_advisor_workbook(workbook_path, snapshot, holdings, (), {})


def test_workbook_rejects_corruption_or_non_xlsx_paths_without_replacing_an_existing_file(tmp_path):
    corrupt_path = tmp_path / "SIC Advisor Queue.xlsx"
    corrupt_path.write_bytes(b"not a workbook")
    snapshot = _snapshot(date(2026, 7, 18), 98.0)
    holdings = Holdings(snapshot.as_of, pd.DataFrame({"dollar_value": [10_500.0]}, index=["FIGI"]))

    with pytest.raises(ValueError, match="not a readable .xlsx"):
        write_advisor_workbook(corrupt_path, snapshot, holdings, (), {}, expected_revision="any")
    assert corrupt_path.read_bytes() == b"not a workbook"

    with pytest.raises(ValueError, match="must use a .xlsx extension"):
        write_advisor_workbook(tmp_path / "SIC Advisor Queue.csv", snapshot, holdings, (), {})


def test_failed_atomic_save_never_replaces_the_last_good_workbook(tmp_path, monkeypatch):
    workbook_path = tmp_path / "SIC Advisor Queue.xlsx"
    snapshot = _snapshot(date(2026, 7, 18), 98.0)
    holdings = Holdings(snapshot.as_of, pd.DataFrame({"dollar_value": [10_500.0]}, index=["FIGI"]))
    write_advisor_workbook(workbook_path, snapshot, holdings, (), {})
    last_good_contents = workbook_path.read_bytes()

    def fail_save(self: Workbook, filename: object) -> None:
        raise OSError("disk write failed")

    monkeypatch.setattr(Workbook, "save", fail_save)
    with pytest.raises(OSError, match="disk write failed"):
        write_advisor_workbook(
            workbook_path, snapshot, holdings, (), {}, expected_revision=workbook_revision(workbook_path)
        )

    assert workbook_path.read_bytes() == last_good_contents
    assert load_workbook(workbook_path)["Run Summary"]["B2"].value == "2026-07-18"
