from datetime import date

import pandas as pd
import pytest

from qepm.beta_monitoring import portfolio_beta_status
from qepm.contracts import Holdings, PortfolioPolicy, Snapshot


def test_beta_monitor_reports_operational_target_and_long_window_context():
    snapshot = Snapshot(
        date(2026, 7, 17),
        pd.DataFrame({"market_beta_90d": [0.78], "market_beta_252d": [0.74]}, index=["FIGI"]), pd.DataFrame(),
    )
    holdings = Holdings(date(2026, 7, 17), pd.DataFrame({"dollar_value": [100_000]}, index=["FIGI"]))

    status = portfolio_beta_status(holdings, snapshot, PortfolioPolicy(portfolio_nav=100_000))

    assert status.operational_beta == 0.78
    assert status.context_beta == 0.74
    assert status.status == "target"
    assert status.requires_exception_review is False


def test_beta_monitor_uses_distinct_above_target_warning_and_ceiling_bands():
    def status_for(beta: float) -> str:
        snapshot = Snapshot(date(2026, 7, 17), pd.DataFrame({"market_beta_90d": [beta]}, index=["FIGI"]), pd.DataFrame())
        holdings = Holdings(date(2026, 7, 17), pd.DataFrame({"dollar_value": [100_000]}, index=["FIGI"]))
        return portfolio_beta_status(holdings, snapshot, PortfolioPolicy(portfolio_nav=100_000)).status

    assert status_for(0.85) == "above-target"
    assert status_for(0.95) == "warning"
    assert status_for(1.00) == "ceiling-breach"


def test_beta_monitor_escalates_ceiling_or_confirmed_two_window_warning():
    holdings = Holdings(date(2026, 7, 17), pd.DataFrame({"dollar_value": [100_000]}, index=["FIGI"]))
    confirmed = Snapshot(date(2026, 7, 17), pd.DataFrame({"market_beta_90d": [0.95], "market_beta_252d": [0.92]}, index=["FIGI"]), pd.DataFrame())

    assert portfolio_beta_status(holdings, confirmed, PortfolioPolicy(portfolio_nav=100_000)).requires_exception_review is True


def test_beta_monitor_requires_holdings_and_snapshot_from_the_same_date():
    snapshot = Snapshot(
        date(2026, 7, 17), pd.DataFrame({"market_beta_90d": [0.78]}, index=["FIGI"]), pd.DataFrame()
    )
    stale_holdings = Holdings(
        date(2026, 7, 16), pd.DataFrame({"dollar_value": [100_000]}, index=["FIGI"])
    )

    with pytest.raises(ValueError, match="same as_of"):
        portfolio_beta_status(stale_holdings, snapshot, PortfolioPolicy(portfolio_nav=100_000))
