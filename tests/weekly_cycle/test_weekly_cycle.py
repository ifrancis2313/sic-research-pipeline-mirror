from datetime import date

import pandas as pd
import pytest

from qepm.contracts import (
    DecisionRecord,
    Direction,
    ExecutionPriceLimit,
    FactorScoreMatrix,
    Holdings,
    PhaseGateError,
    PortfolioFitResult,
    PortfolioPolicy,
    ProposedTrade,
    SizingRecommendation,
    Snapshot,
    TradeOrder,
)
from qepm.weekly_cycle import run_live_weekly_cycle, run_weekly_cycle


def test_friday_cycle_generates_separate_student_and_eboard_pulses():
    friday = date(2026, 7, 17)
    snapshot = Snapshot(friday, pd.DataFrame(index=pd.Index(["IWB"], name="figi")), pd.DataFrame())
    scores = FactorScoreMatrix(friday, pd.DataFrame({"quality": [30.0]}, index=["IWB"]), {"quality": 1.0})
    holdings = Holdings(friday, pd.DataFrame({"dollar_value": [100_000.0]}, index=["IWB"]))

    result = run_weekly_cycle(
        snapshot, scores, holdings, PortfolioPolicy(portfolio_nav=100_000.0), {"IWB": "core"}, {"RB-1": "open"}
    )
    student, board = result.student, result.eboard

    assert student.research_needs[0].factor == "quality"
    assert student.beta_status == "data-missing"
    assert student.sleeve_statuses["core"] == "overweight"
    assert board.holdings.loc["IWB", "dollar_value"] == 100_000.0


def test_weekly_cycle_rejects_a_non_friday_snapshot():
    saturday = date(2026, 7, 18)
    snapshot = Snapshot(saturday, pd.DataFrame(index=pd.Index(["IWB"], name="figi")), pd.DataFrame())
    scores = FactorScoreMatrix(saturday, pd.DataFrame({"quality": [30.0]}, index=["IWB"]), {"quality": 1.0})
    holdings = Holdings(saturday, pd.DataFrame({"dollar_value": [100_000.0]}, index=["IWB"]))

    with pytest.raises(ValueError, match="Friday"):
        run_weekly_cycle(snapshot, scores, holdings, PortfolioPolicy(portfolio_nav=100_000.0), {"IWB": "core"}, {})


def test_friday_cycle_carries_approved_pending_trades_into_the_eboard_pulse():
    friday = date(2026, 7, 17)
    snapshot = Snapshot(friday, pd.DataFrame(index=pd.Index(["IWB"], name="figi")), pd.DataFrame())
    scores = FactorScoreMatrix(friday, pd.DataFrame({"quality": [30.0]}, index=["IWB"]), {"quality": 1.0})
    holdings = Holdings(friday, pd.DataFrame({"dollar_value": [100_000.0]}, index=["IWB"]))
    order = TradeOrder("IWB", Direction.BUY, 3_000.0, "PITCH", "BRIEF", "TARGET")
    proposal = ProposedTrade(
        order, friday, True,
        PortfolioFitResult("PITCH", "BRIEF", "TARGET", friday, True, False, {}, {}, order=order),
        SizingRecommendation(0.8, 0.03, 0.03, False, False), 100_000.0,
        DecisionRecord("PITCH", True, friday, ("Board Chair", "PM"), "chair-plus-pm-or-lead-v1"),
        ExecutionPriceLimit(95.0, 100.0, "DCF-supported purchase ceiling.", material_move_fraction=0.10),
    )

    result = run_weekly_cycle(
        snapshot, scores, holdings, PortfolioPolicy(portfolio_nav=100_000.0), {"IWB": "core"}, {}, (proposal,)
    )

    assert result.eboard.proposed_trades == (proposal,)


def test_live_cycle_rejects_lightweight_fixture_snapshot_before_running():
    friday = date(2026, 7, 17)
    snapshot = Snapshot(friday, pd.DataFrame(index=pd.Index(["IWB"], name="figi")), pd.DataFrame())
    scores = FactorScoreMatrix(friday, pd.DataFrame({"quality": [30.0]}, index=["IWB"]), {"quality": 1.0})
    holdings = Holdings(friday, pd.DataFrame({"dollar_value": [100_000.0]}, index=["IWB"]))

    with pytest.raises(PhaseGateError, match="V1 live snapshot is missing required fields"):
        run_live_weekly_cycle(
            snapshot, scores, holdings, PortfolioPolicy(portfolio_nav=100_000.0), {"IWB": "core"}, {}
        )
