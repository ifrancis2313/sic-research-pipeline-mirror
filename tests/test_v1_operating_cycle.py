from datetime import date, timedelta

import pandas as pd

from qepm.advisor_queue import admit_proposed_trade, execution_status
from qepm.contracts import (
    CompetingPitch,
    DecisionRecord,
    DimensionSpec,
    Direction,
    ExecutionPriceLimit,
    ExposureTarget,
    FactorScoreMatrix,
    Holdings,
    PortfolioFitResult,
    PortfolioPolicy,
    ProposedTrade,
    QueuePublication,
    Snapshot,
    TradeOrder,
)
from qepm.governance import DEFAULT_ORDINARY_RULE_ID
from qepm.portfolio_fit import evaluate_portfolio_fit
from qepm.position_sizing import recommend_position_size
from qepm.queue_publication import validate_queue_publication
from qepm.research_brief_tracker import create_brief, score_pitches, submit_pitch
from qepm.weekly_cycle import run_weekly_cycle


def test_recorded_v1_cycle_reaches_a_retestable_advisor_proposal():
    as_of = date(2026, 7, 17)
    snapshot = Snapshot(as_of, pd.DataFrame({
        "market_beta_90d": [0.7, 0.7], "median_daily_dollar_volume": [10_000_000.0, 10_000_000.0],
        "has_price_history": [True, True], "is_russell_1000": [True, True],
    }, index=["LEGACY", "FIGI"]), pd.DataFrame())
    scores = FactorScoreMatrix(as_of, pd.DataFrame({"quality": [30.0, 80.0]}, index=["LEGACY", "FIGI"]), {"quality": 1.0})
    holdings = Holdings(as_of, pd.DataFrame({"dollar_value": [100_000.0]}, index=pd.Index(["LEGACY"], name="figi")))
    weekly = run_weekly_cycle(
        snapshot, scores, holdings, PortfolioPolicy(portfolio_nav=100_000.0), {"LEGACY": "active"}, {"RB-OPEN": "open"}
    )
    publication = QueuePublication(
        tuple(need.factor for need in weekly.student.research_needs), ("quality",), "Publish quality need."
    )
    validate_queue_publication(publication)
    assert weekly.student.research_needs[0].factor == "quality"
    target = ExposureTarget("QUALITY", Direction.BUY, 3_000.0, DimensionSpec(factor="quality"), "build quality")
    brief = create_brief(target)
    pitch = CompetingPitch(
        "PITCH", brief.id, "Pod A", "FIGI", "thesis", "variant", "DCF", "CCA", "catalysts", "risks", True
    )
    submit_pitch(brief, pitch, submitted_on=as_of)
    readiness = score_pitches(brief)
    fit = evaluate_portfolio_fit(pitch, target, brief, holdings, scores, snapshot, as_of, PortfolioPolicy(portfolio_nav=100_000.0))
    sizing = recommend_position_size(confidence=0.8)
    decision = DecisionRecord(pitch.id, True, as_of, ("Board Chair", "PM"), DEFAULT_ORDINARY_RULE_ID)
    order = TradeOrder(pitch.figi, Direction.BUY, 3_000.0, pitch.id, brief.id, target.id)
    proposal = ProposedTrade(
        order, as_of, pitch in readiness.ready,
        PortfolioFitResult(
            fit.pitch_id, fit.brief_id, fit.target_id, fit.as_of, fit.passed, fit.requires_exception,
            fit.factor_fit, fit.estimated_impact, fit.hard_limit_violations, fit.warnings, fit.notes, order,
        ),
        sizing, 100_000.0, decision,
        ExecutionPriceLimit(95.0, 100.0, "DCF-supported purchase ceiling.", material_move_fraction=0.10),
    )

    admit_proposed_trade(proposal)
    assert execution_status(proposal, as_of + timedelta(days=30)).requires_retest is True
