from datetime import date

import pandas as pd

from qepm.contracts import Holdings, PortfolioPolicy
from qepm.sleeves import (
    STARTING_SLEEVE_BY_FIGI,
    STARTING_SLEEVE_BY_TICKER,
    cash_posture,
    sleeve_status,
    sleeve_weights,
)


def test_starting_sleeve_map_preserves_the_transition_book():
    holdings = Holdings(
        date(2026, 7, 17),
        pd.DataFrame({"dollar_value": [75.0, 31.0, 10.0]}, index=["SAMPLE-CORE-1", "SAMPLE-ACTIVE-1", "SAMPLE-EXPERIMENTAL-1"]),
    )

    weights = sleeve_weights(
        holdings,
        PortfolioPolicy(portfolio_nav=116.0),
        {"SAMPLE-CORE-1": "core", "SAMPLE-ACTIVE-1": "active", "SAMPLE-EXPERIMENTAL-1": "experimental"},
    )

    assert weights == {"core": 75 / 116, "active": 31 / 116, "experimental": 10 / 116, "unassigned": 0.0}
    assert STARTING_SLEEVE_BY_TICKER["SAMPLE-CORE-1"] == "core"
    assert STARTING_SLEEVE_BY_FIGI["BBG-FIXTURE-013"] == "core"


def test_excess_cash_is_flagged_without_creating_an_order():
    holdings = Holdings(date(2026, 7, 17), pd.DataFrame({"dollar_value": [90.0]}, index=["SAMPLE-CORE-1"]))

    posture = cash_posture(holdings, PortfolioPolicy(portfolio_nav=100.0))

    assert posture == {"cash_weight": 0.10, "flagged": True}


def test_sleeve_status_flags_the_transition_without_forcing_trades():
    status = sleeve_status({"core": 0.59, "active": 0.31, "experimental": 0.10}, PortfolioPolicy(portfolio_nav=1.0))

    assert status == {"core": "overweight", "experimental": "underweight", "active": "transition-build"}
