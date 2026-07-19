from datetime import date

import pandas as pd

from qepm.campaigns import evaluate_approved_subset
from qepm.contracts import (
    CampaignLeg,
    CompetingPitch,
    DimensionSpec,
    Direction,
    ExposureTarget,
    FactorScoreMatrix,
    Holdings,
    PortfolioPolicy,
    Snapshot,
)
from qepm.research_brief_tracker import create_brief


def test_campaign_subset_is_checked_cumulatively_not_as_independent_legs():
    as_of = date(2026, 7, 17)
    snapshot = Snapshot(
        as_of,
        pd.DataFrame(
                {
                    "median_daily_dollar_volume": [10_000_000.0],
                    "market_beta_90d": [0.5],
                    "has_price_history": [True],
                    "is_russell_1000": [True],
                },
            index=pd.Index(["FIGI"], name="figi"),
        ),
        pd.DataFrame(index=pd.Index([], name="date")),
    )
    scores = FactorScoreMatrix(as_of, pd.DataFrame({"quality": [70.0]}, index=["FIGI"]), {"quality": 1.0})
    holdings = Holdings(as_of, pd.DataFrame({"dollar_value": []}, index=pd.Index([], name="figi")))
    target = ExposureTarget("T", Direction.BUY, 6_000.0, DimensionSpec(factor="quality"), "test")
    first = create_brief(target)
    second = create_brief(target)
    legs = (
        CampaignLeg(CompetingPitch("P1", first.id, "A", "FIGI", "t"), first),
        CampaignLeg(CompetingPitch("P2", second.id, "B", "FIGI", "t"), second),
    )

    result = evaluate_approved_subset(legs, holdings, scores, snapshot, as_of, PortfolioPolicy(portfolio_nav=100_000.0))

    assert result.leg_results[0].passed is True
    assert result.leg_results[1].passed is False
    assert "single-name-cap" in result.leg_results[1].hard_limit_violations
