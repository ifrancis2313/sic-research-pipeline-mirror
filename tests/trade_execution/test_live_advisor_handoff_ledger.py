from dataclasses import replace
from datetime import date

import pandas as pd
import pytest
from openpyxl import load_workbook

from qepm.advisor_workbook import (
    AdvisorHandoffDuplicate,
    WorkbookRevisionConflict,
    workbook_revision,
    write_advisor_workbook,
)
from qepm.contracts import (
    DecisionRecord,
    Direction,
    ExecutionPriceLimit,
    Holdings,
    PortfolioFitResult,
    ProposedTrade,
    SizingRecommendation,
    Snapshot,
    TradeOrder,
)
from qepm.governance import DEFAULT_ORDINARY_RULE_ID
from qepm.trade_execution import execute_live_proposed_trade


def _order(*, pitch_id: str = "PITCH-1") -> TradeOrder:
    return TradeOrder("FIGI", Direction.BUY, 3_000.0, pitch_id, "BRIEF-1", "TARGET-1")


def _proposal(*, pitch_id: str = "PITCH-1") -> ProposedTrade:
    order = _order(pitch_id=pitch_id)
    return ProposedTrade(
        order=order,
        approved_on=date(2026, 7, 18),
        pitch_ready=True,
        approved_fit=PortfolioFitResult(pitch_id, "BRIEF-1", "TARGET-1", date(2026, 7, 18), True, False, {}, {}, order=order),
        sizing=SizingRecommendation(0.8, 0.03, 0.03, False, False),
        approval_nav=100_000.0,
        decision=DecisionRecord(pitch_id, True, date(2026, 7, 18), ("Board Chair", "PM"), DEFAULT_ORDINARY_RULE_ID),
        price_limit=ExecutionPriceLimit(95.0, 100.0, "DCF supports the approved ceiling.", material_move_fraction=0.10),
    )


def _live_snapshot() -> Snapshot:
    as_of = date(2026, 7, 18)
    return Snapshot(as_of, pd.DataFrame({
        "sector": ["Technology"], "market_cap": [1e9], "free_cash_flow_ttm": [1.0], "revenue_ttm": [2.0],
        "cost_of_revenue_ttm": [1.0], "total_assets": [3.0], "momentum_12_1": [0.1],
        "market_beta_90d": [1.0], "market_beta_252d": [1.0], "median_daily_dollar_volume": [1e7],
        "is_russell_1000": [True], "is_us_listed": [True], "instrument_type": ["common_stock"],
        "is_core_market_etf": [False], "price": [95.0], "has_price_history": [True],
        "momentum_12_1_asof": [as_of], "market_beta_90d_asof": [as_of], "market_beta_252d_asof": [as_of],
    }, index=["FIGI"]), pd.DataFrame())


def _fit(proposal: ProposedTrade) -> PortfolioFitResult:
    return replace(proposal.approved_fit, as_of=date(2026, 7, 18))


def _refresh_workbook(path, snapshot, proposals=()):
    holdings = Holdings(snapshot.as_of, pd.DataFrame({"dollar_value": [10_000.0]}, index=["FIGI"]))
    write_advisor_workbook(path, snapshot, holdings, proposals, {proposal.order.pitch_id: _fit(proposal) for proposal in proposals})


def test_live_handoff_records_once_and_rejects_duplicate_without_touching_manual_execution_history(tmp_path):
    path = tmp_path / "SIC Advisor Queue.xlsx"
    snapshot = _live_snapshot()
    proposal = _proposal()
    _refresh_workbook(path, snapshot, (proposal,))

    result = execute_live_proposed_trade(
        proposal, snapshot, _fit(proposal), workbook_path=path, expected_workbook_revision=workbook_revision(path), prepared_by="PM"
    )

    assert result.status == "sent_to_advisor"
    workbook = load_workbook(path)
    assert workbook["Handoff Ledger"].max_row == 2
    assert workbook["Handoff Ledger"]["B2"].value == "prepared_for_advisor"
    assert workbook["Handoff Ledger"]["D2"].value == "PITCH-1"
    assert workbook["Handoff Ledger"]["R2"].value == "PM"
    assert workbook["Execution History"].max_row == 1

    with pytest.raises(AdvisorHandoffDuplicate, match="already prepared"):
        execute_live_proposed_trade(
            proposal, snapshot, _fit(proposal), workbook_path=path, expected_workbook_revision=workbook_revision(path), prepared_by="PM"
        )
    assert load_workbook(path)["Handoff Ledger"].max_row == 2


def test_live_handoff_accepts_a_distinct_approved_proposal_and_ledger_survives_refresh(tmp_path):
    path = tmp_path / "SIC Advisor Queue.xlsx"
    snapshot = _live_snapshot()
    first, second = _proposal(), _proposal(pitch_id="PITCH-2")
    _refresh_workbook(path, snapshot, (first, second))
    execute_live_proposed_trade(first, snapshot, _fit(first), workbook_path=path, expected_workbook_revision=workbook_revision(path), prepared_by="PM")
    execute_live_proposed_trade(second, snapshot, _fit(second), workbook_path=path, expected_workbook_revision=workbook_revision(path), prepared_by="PM")

    refreshed_holdings = Holdings(snapshot.as_of, pd.DataFrame({"dollar_value": [11_000.0]}, index=["FIGI"]))
    write_advisor_workbook(
        path, snapshot, refreshed_holdings, (second,), {second.order.pitch_id: _fit(second)},
        expected_revision=workbook_revision(path),
    )

    ledger = load_workbook(path)["Handoff Ledger"]
    assert ledger.max_row == 3
    assert [ledger.cell(row, 4).value for row in (2, 3)] == ["PITCH-1", "PITCH-2"]


def test_live_handoff_rejects_stale_workbook_revision_and_preserves_ledger(tmp_path):
    path = tmp_path / "SIC Advisor Queue.xlsx"
    snapshot = _live_snapshot()
    proposal = _proposal()
    _refresh_workbook(path, snapshot, (proposal,))
    stale_revision = workbook_revision(path)
    human = load_workbook(path)
    human["Execution History"].append(["2026-07-18", "FIGI", "buy", 3_000.0, "Faculty Advisor", "manual note"])
    human.save(path)

    with pytest.raises(WorkbookRevisionConflict, match="changed since it was read"):
        execute_live_proposed_trade(
            proposal, snapshot, _fit(proposal), workbook_path=path, expected_workbook_revision=stale_revision, prepared_by="PM"
        )
    workbook = load_workbook(path)
    assert workbook["Handoff Ledger"].max_row == 1
    assert workbook["Execution History"]["A2"].value == "2026-07-18"
