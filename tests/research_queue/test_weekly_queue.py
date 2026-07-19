from datetime import date

import pandas as pd

from qepm.contracts import FactorScoreMatrix, Holdings, PortfolioPolicy
from qepm.research_queue import propose_weekly_research_queue


def test_weekly_queue_surfaces_only_the_largest_actionable_factor_gap():
    scores = FactorScoreMatrix(
        as_of=date(2026, 7, 17),
        scores=pd.DataFrame(
            {
                "quality": [30.0, 90.0],
                "value": [70.0, 30.0],
                "momentum": [80.0, 80.0],
                "size": [20.0, 90.0],
            },
            index=pd.Index(["LOW-QUALITY", "HIGH-QUALITY"], name="figi"),
        ),
        weights={"quality": 1.0, "value": 1.0, "momentum": 1.0, "size": 0.0},
    )
    holdings = Holdings(
        as_of=date(2026, 7, 17),
        positions=pd.DataFrame({"dollar_value": [100_000.0]}, index=pd.Index(["LOW-QUALITY"], name="figi")),
    )

    queue = propose_weekly_research_queue(
        scores,
        holdings,
        PortfolioPolicy(portfolio_nav=100_000.0),
    )

    assert [need.factor for need in queue] == ["quality"]
    assert queue[0].current_score == 30.0
    assert queue[0].target_score == 55.0
    assert queue[0].priority == "priority"
    assert queue[0].direction == "buy"
