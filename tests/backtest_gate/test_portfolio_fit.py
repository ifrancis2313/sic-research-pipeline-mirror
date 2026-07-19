import pandas as pd
import pytest

from qepm.backtest_gate import evaluate_portfolio_fit
from qepm.contracts import (
    CompetingPitch,
    DimensionSpec,
    Direction,
    ExposureTarget,
    FactorScoreMatrix,
    Holdings,
    PhaseGateError,
    PortfolioPolicy,
)
from qepm.research_brief_tracker import create_brief


def test_fit_check_rejects_buy_that_would_breach_single_name_cap(as_of, snapshot, scores):
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6],
        median_daily_dollar_volume=[10_000_000.0] * 5,
        is_russell_1000=[True] * 5,
    )
    policy = PortfolioPolicy(portfolio_nav=100_000.0)
    holdings = Holdings(
        as_of=as_of,
        positions=pd.DataFrame({"dollar_value": [9_000.0]}, index=pd.Index(["BBG-FIXTURE-001"], name="figi")),
    )
    target = ExposureTarget(
        id="ET-BUY-MOMENTUM",
        direction=Direction.BUY,
        dollar_amount=2_000.0,
        dimension=DimensionSpec(factor="momentum"),
        rationale="Add momentum exposure.",
    )
    brief = create_brief(target)
    pitch = CompetingPitch(id="CP-CAP", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-001", thesis="t")

    result = evaluate_portfolio_fit(
        pitch,
        target,
        brief,
        holdings,
        scores,
        snapshot.__class__(as_of=snapshot.as_of, securities=securities, macro=snapshot.macro),
        as_of,
        policy,
    )

    assert result.passed is False
    assert result.requires_exception is True
    assert result.hard_limit_violations == ("single-name-cap",)


def test_portfolio_fit_requires_one_exact_snapshot_date(as_of, snapshot, scores):
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6],
        median_daily_dollar_volume=[10_000_000.0] * 5,
    ).drop(columns=["is_russell_1000"])
    target = ExposureTarget("ET", Direction.BUY, 2_000.0, DimensionSpec(factor="momentum"), "test")
    brief = create_brief(target)
    pitch = CompetingPitch("CP", brief.id, "Pod A", "BBG-FIXTURE-001", "t")
    stale_holdings = Holdings(
        as_of.replace(day=as_of.day - 1),
        pd.DataFrame({"dollar_value": []}, index=pd.Index([], name="figi")),
    )

    with pytest.raises(PhaseGateError, match="same as_of"):
        evaluate_portfolio_fit(
            pitch,
            target,
            brief,
            stale_holdings,
            scores,
            snapshot.__class__(as_of=snapshot.as_of, securities=securities, macro=snapshot.macro),
            as_of,
            PortfolioPolicy(portfolio_nav=100_000.0),
        )


def test_fit_check_rejects_a_sell_larger_than_the_existing_long_position(as_of, snapshot, scores):
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6],
        median_daily_dollar_volume=[10_000_000.0] * 5,
    )
    target = ExposureTarget(
        "ET-SELL", Direction.SELL, 2_000.0, DimensionSpec(factor="momentum"), "test", ("BBG-FIXTURE-001",)
    )
    brief = create_brief(target)
    pitch = CompetingPitch("CP-SELL", brief.id, "Pod A", "BBG-FIXTURE-001", "t")
    holdings = Holdings(
        as_of,
        pd.DataFrame({"dollar_value": [1_000.0]}, index=pd.Index([pitch.figi], name="figi")),
    )

    result = evaluate_portfolio_fit(
        pitch,
        target,
        brief,
        holdings,
        scores,
        snapshot.__class__(as_of=snapshot.as_of, securities=securities, macro=snapshot.macro),
        as_of,
        PortfolioPolicy(portfolio_nav=100_000.0),
    )

    assert result.passed is False
    assert "sell-exceeds-held-position" in result.hard_limit_violations


def test_fit_check_blocks_trade_without_liquidity_data(as_of, snapshot, scores):
    securities = snapshot.securities.assign(market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6])
    policy = PortfolioPolicy(portfolio_nav=100_000.0)
    holdings = Holdings(as_of=as_of, positions=pd.DataFrame({"dollar_value": []}, index=pd.Index([], name="figi")))
    target = ExposureTarget(
        id="ET-BUY-MOMENTUM",
        direction=Direction.BUY,
        dollar_amount=2_000.0,
        dimension=DimensionSpec(factor="momentum"),
        rationale="Add momentum exposure.",
    )
    brief = create_brief(target)
    pitch = CompetingPitch(id="CP-LIQ", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-001", thesis="t")

    result = evaluate_portfolio_fit(
        pitch,
        target,
        brief,
        holdings,
        scores,
        snapshot.__class__(as_of=snapshot.as_of, securities=securities, macro=snapshot.macro),
        as_of,
        policy,
    )

    assert result.passed is False
    assert result.hard_limit_violations == ("missing-liquidity-data",)


def test_fit_check_treats_nan_liquidity_as_missing_binding_data(as_of, snapshot, scores):
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6], median_daily_dollar_volume=[float("nan")] * 5
    )
    target = ExposureTarget("NAN-LIQ", Direction.BUY, 2_000.0, DimensionSpec(factor="momentum"), "test")
    brief = create_brief(target)
    pitch = CompetingPitch("CP-NAN", brief.id, "Pod", "BBG-FIXTURE-001", "t")
    result = evaluate_portfolio_fit(
        pitch, target, brief,
        Holdings(as_of, pd.DataFrame({"dollar_value": []}, index=pd.Index([], name="figi"))), scores,
        snapshot.__class__(as_of, securities, snapshot.macro), as_of, PortfolioPolicy(portfolio_nav=100_000.0),
    )

    assert "missing-liquidity-data" in result.hard_limit_violations


def test_fit_check_blocks_trade_without_price_history(as_of, snapshot, scores):
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6], median_daily_dollar_volume=[10_000_000.0] * 5,
        has_price_history=[False] * 5,
    )
    target = ExposureTarget("PRICE", Direction.BUY, 2_000.0, DimensionSpec(factor="momentum"), "test")
    brief = create_brief(target)
    pitch = CompetingPitch("CP-PRICE", brief.id, "Pod", "BBG-FIXTURE-001", "t")
    result = evaluate_portfolio_fit(
        pitch, target, brief,
        Holdings(as_of, pd.DataFrame({"dollar_value": []}, index=pd.Index([], name="figi"))), scores,
        snapshot.__class__(as_of, securities, snapshot.macro), as_of, PortfolioPolicy(portfolio_nav=100_000.0),
    )

    assert "missing-price-history" in result.hard_limit_violations


def test_fit_check_blocks_a_trade_with_nan_price_history_not_just_none_or_false(as_of, snapshot, scores):
    """`has_price_history` can arrive as a NaN float (a source column that
    failed to parse cleanly), not just Python `None` or `False` -- distinct
    from the `is None`/`not bool(...)` cases, since `bool(nan)` is `True` in
    Python. Mutation testing found this specific case is otherwise the only
    thing standing between `is None or pd.isna(...) or not bool(...)` and a
    weakened `(is None and pd.isna(...)) or not bool(...)` that would let a
    NaN-price-history security silently pass."""
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6], median_daily_dollar_volume=[10_000_000.0] * 5,
        has_price_history=[float("nan"), True, True, True, True],
    )
    target = ExposureTarget("PRICE-NAN", Direction.BUY, 2_000.0, DimensionSpec(factor="momentum"), "test")
    brief = create_brief(target)
    pitch = CompetingPitch("CP-PRICE-NAN", brief.id, "Pod", "BBG-FIXTURE-001", "t")
    result = evaluate_portfolio_fit(
        pitch, target, brief,
        Holdings(as_of, pd.DataFrame({"dollar_value": []}, index=pd.Index([], name="figi"))), scores,
        snapshot.__class__(as_of, securities, snapshot.macro), as_of, PortfolioPolicy(portfolio_nav=100_000.0),
    )

    assert "missing-price-history" in result.hard_limit_violations


def test_fit_check_flags_high_cash_without_forcing_a_trade(as_of, snapshot, scores):
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6], median_daily_dollar_volume=[10_000_000.0] * 5
    )
    target = ExposureTarget("CASH", Direction.BUY, 2_000.0, DimensionSpec(factor="momentum"), "test")
    brief = create_brief(target)
    pitch = CompetingPitch("CP-CASH", brief.id, "Pod", "BBG-FIXTURE-001", "t")
    result = evaluate_portfolio_fit(
        pitch, target, brief,
        Holdings(as_of, pd.DataFrame({"dollar_value": []}, index=pd.Index([], name="figi"))), scores,
        snapshot.__class__(as_of, securities, snapshot.macro), as_of, PortfolioPolicy(portfolio_nav=100_000.0),
    )

    assert result.passed is True
    assert "cash-above-normal-operating-band" in result.warnings


def test_active_brief_requires_russell_1000_eligibility_data(as_of, snapshot, scores):
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6],
        median_daily_dollar_volume=[10_000_000.0] * 5,
    ).drop(columns=["is_russell_1000"])
    target = ExposureTarget("ACTIVE", Direction.BUY, 2_000.0, DimensionSpec(factor="momentum"), "test", sleeve="active")
    brief = create_brief(target)
    pitch = CompetingPitch("CP-ACTIVE", brief.id, "Pod", "BBG-FIXTURE-001", "t")
    result = evaluate_portfolio_fit(
        pitch, target, brief,
        Holdings(as_of, pd.DataFrame({"dollar_value": []}, index=pd.Index([], name="figi"))),
        scores, snapshot.__class__(as_of, securities, snapshot.macro), as_of, PortfolioPolicy(portfolio_nav=100_000.0),
    )

    assert "missing-universe-eligibility" in result.hard_limit_violations


def test_undeclared_sleeve_defaults_to_active_and_rejects_out_of_universe_candidate(as_of, snapshot, scores):
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6],
        median_daily_dollar_volume=[10_000_000.0] * 5,
        is_russell_1000=[False] * 5,
    )
    target = ExposureTarget("DEFAULT-SLEEVE", Direction.BUY, 2_000.0, DimensionSpec(factor="momentum"), "test")
    brief = create_brief(target)
    pitch = CompetingPitch("CP-DEFAULT-SLEEVE", brief.id, "Pod", "BBG-FIXTURE-001", "t")

    result = evaluate_portfolio_fit(
        pitch,
        target,
        brief,
        Holdings(as_of, pd.DataFrame({"dollar_value": []}, index=pd.Index([], name="figi"))),
        scores,
        snapshot.__class__(as_of, securities, snapshot.macro),
        as_of,
        PortfolioPolicy(portfolio_nav=100_000.0),
    )

    assert "active-sleeve-universe-eligibility" in result.hard_limit_violations


def test_active_brief_treats_nan_russell_eligibility_as_missing_data(as_of, snapshot, scores):
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6],
        median_daily_dollar_volume=[10_000_000.0] * 5,
        is_russell_1000=[float("nan")] * 5,
    )
    target = ExposureTarget("ACTIVE-NAN", Direction.BUY, 2_000.0, DimensionSpec(factor="momentum"), "test", sleeve="active")
    brief = create_brief(target)
    pitch = CompetingPitch("CP-ACTIVE-NAN", brief.id, "Pod", "BBG-FIXTURE-001", "t")

    result = evaluate_portfolio_fit(
        pitch, target, brief,
        Holdings(as_of, pd.DataFrame({"dollar_value": []}, index=pd.Index([], name="figi"))), scores,
        snapshot.__class__(as_of, securities, snapshot.macro), as_of, PortfolioPolicy(portfolio_nav=100_000.0),
    )

    assert "missing-universe-eligibility" in result.hard_limit_violations


@pytest.mark.parametrize(
    ("sleeve", "extra_fields"),
    (
        ("core", {"is_core_market_etf": True}),
        ("experimental", {"is_us_listed": True, "instrument_type": "stock"}),
    ),
)
def test_pm_selected_non_active_sleeves_reach_the_portfolio_fit_eligibility_gate(
    as_of, snapshot, scores, sleeve, extra_fields
):
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6],
        median_daily_dollar_volume=[10_000_000.0] * 5,
        is_russell_1000=[False] * 5,
        **{field: [value] * 5 for field, value in extra_fields.items()},
    )
    target = ExposureTarget("SLEEVE", Direction.BUY, 2_000.0, DimensionSpec(factor="momentum"), "test")
    brief = create_brief(target, sleeve=sleeve)
    pitch = CompetingPitch("CP-SLEEVE", brief.id, "Pod", "BBG-FIXTURE-001", "t")

    result = evaluate_portfolio_fit(
        pitch, brief.target, brief, Holdings(as_of, pd.DataFrame({"dollar_value": []}, index=pd.Index([], name="figi"))),
        scores, snapshot.__class__(as_of, securities, snapshot.macro), as_of, PortfolioPolicy(portfolio_nav=100_000.0),
    )

    assert not any("eligibility" in violation for violation in result.hard_limit_violations)


@pytest.mark.parametrize(
    ("sleeve", "extra_fields", "expected_violation"),
    (
        ("core", {"is_core_market_etf": False}, "active-sleeve-universe-eligibility"),
        ("experimental", {"is_us_listed": True, "instrument_type": "bond"}, "experimental-sleeve-eligibility"),
        ("experimental", {"is_us_listed": False, "instrument_type": "stock"}, "experimental-sleeve-eligibility"),
    ),
)
def test_pm_selected_non_active_sleeves_reject_an_ineligible_candidate(
    as_of, snapshot, scores, sleeve, extra_fields, expected_violation
):
    """The pass-side of PM-selected core/experimental sleeves is covered
    above; this covers the reject side -- a security that is explicitly
    ineligible for its declared sleeve, not just missing data (see the
    `-missing-*-eligibility` cases covered elsewhere)."""
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6],
        median_daily_dollar_volume=[10_000_000.0] * 5,
        is_russell_1000=[False] * 5,
        **{field: [value] * 5 for field, value in extra_fields.items()},
    )
    target = ExposureTarget("SLEEVE-REJECT", Direction.BUY, 2_000.0, DimensionSpec(factor="momentum"), "test")
    brief = create_brief(target, sleeve=sleeve)
    pitch = CompetingPitch("CP-SLEEVE-REJECT", brief.id, "Pod", "BBG-FIXTURE-001", "t")

    result = evaluate_portfolio_fit(
        pitch, brief.target, brief, Holdings(as_of, pd.DataFrame({"dollar_value": []}, index=pd.Index([], name="figi"))),
        scores, snapshot.__class__(as_of, securities, snapshot.macro), as_of, PortfolioPolicy(portfolio_nav=100_000.0),
    )

    assert expected_violation in result.hard_limit_violations


def test_an_invalid_sleeve_string_is_rejected_rather_than_silently_defaulting(as_of, snapshot, scores):
    """`create_brief()` itself already validates sleeve against the allowed
    set, so this can only happen via a hand-constructed `ExposureTarget`
    bypassing that constructor -- but `_evaluate_sleeve_eligibility` must
    still fail closed on it rather than silently treating it as active."""
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6],
        median_daily_dollar_volume=[10_000_000.0] * 5,
        is_russell_1000=[True] * 5,
    )
    target = ExposureTarget(
        "SLEEVE-INVALID", Direction.BUY, 2_000.0, DimensionSpec(factor="momentum"), "test", sleeve="not-a-real-sleeve"
    )
    brief = create_brief(target)
    pitch = CompetingPitch("CP-SLEEVE-INVALID", brief.id, "Pod", "BBG-FIXTURE-001", "t")

    result = evaluate_portfolio_fit(
        pitch, target, brief, Holdings(as_of, pd.DataFrame({"dollar_value": []}, index=pd.Index([], name="figi"))),
        scores, snapshot.__class__(as_of, securities, snapshot.macro), as_of, PortfolioPolicy(portfolio_nav=100_000.0),
    )

    assert "invalid-sleeve" in result.hard_limit_violations


def test_fit_check_blocks_trade_below_liquidity_floor(as_of, snapshot, scores):
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6],
        median_daily_dollar_volume=[4_999_999.0, 10_000_000.0, 10_000_000.0, 10_000_000.0, 10_000_000.0],
    )
    policy = PortfolioPolicy(portfolio_nav=100_000.0)
    holdings = Holdings(as_of=as_of, positions=pd.DataFrame({"dollar_value": []}, index=pd.Index([], name="figi")))
    target = ExposureTarget(
        id="ET-BUY-MOMENTUM",
        direction=Direction.BUY,
        dollar_amount=2_000.0,
        dimension=DimensionSpec(factor="momentum"),
        rationale="Add momentum exposure.",
    )
    brief = create_brief(target)
    pitch = CompetingPitch(id="CP-FLOOR", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-001", thesis="t")

    result = evaluate_portfolio_fit(
        pitch,
        target,
        brief,
        holdings,
        scores,
        snapshot.__class__(as_of=snapshot.as_of, securities=securities, macro=snapshot.macro),
        as_of,
        policy,
    )

    assert result.hard_limit_violations == ("minimum-liquidity",)


def test_fit_check_blocks_trade_above_participation_cap(as_of, snapshot, scores):
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6],
        median_daily_dollar_volume=[10_000_000.0] * 5,
    )
    policy = PortfolioPolicy(portfolio_nav=10_000_000.0)
    holdings = Holdings(as_of=as_of, positions=pd.DataFrame({"dollar_value": []}, index=pd.Index([], name="figi")))
    target = ExposureTarget(
        id="ET-BUY-MOMENTUM",
        direction=Direction.BUY,
        dollar_amount=250_000.0,
        dimension=DimensionSpec(factor="momentum"),
        rationale="Add momentum exposure.",
    )
    brief = create_brief(target)
    pitch = CompetingPitch(id="CP-PARTICIPATION", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-001", thesis="t")

    result = evaluate_portfolio_fit(
        pitch,
        target,
        brief,
        holdings,
        scores,
        snapshot.__class__(as_of=snapshot.as_of, securities=securities, macro=snapshot.macro),
        as_of,
        policy,
    )

    assert result.hard_limit_violations == ("trade-participation-cap",)


def test_fit_check_allows_sell_that_reduces_an_inherited_beta_breach(as_of, snapshot, scores):
    securities = snapshot.securities.assign(
        market_beta_90d=[1.1, 0.7, 0.8, 1.0, 0.6],
        median_daily_dollar_volume=[10_000_000.0] * 5,
    )
    policy = PortfolioPolicy(portfolio_nav=100_000.0)
    holdings = Holdings(
        as_of=as_of,
        positions=pd.DataFrame({"dollar_value": [100_000.0]}, index=pd.Index(["BBG-FIXTURE-001"], name="figi")),
    )
    target = ExposureTarget(
        id="ET-SELL-BETA",
        direction=Direction.SELL,
        dollar_amount=10_000.0,
        dimension=DimensionSpec(factor="momentum"),
        rationale="Reduce beta.",
        source_bucket=("BBG-FIXTURE-001",),
    )
    brief = create_brief(target)
    pitch = CompetingPitch(id="CP-BETA", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-001", thesis="t")

    result = evaluate_portfolio_fit(
        pitch,
        target,
        brief,
        holdings,
        scores,
        snapshot.__class__(as_of=snapshot.as_of, securities=securities, macro=snapshot.macro),
        as_of,
        policy,
    )

    assert result.passed is True
    assert result.hard_limit_violations == ()
    assert result.estimated_impact["portfolio_beta_before"] == 1.1
    assert result.estimated_impact["portfolio_beta_after"] == pytest.approx(0.99)


def test_fit_check_reports_factor_mismatch_as_advisory_not_a_hard_rejection(as_of, snapshot, scores):
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6],
        median_daily_dollar_volume=[10_000_000.0] * 5,
    )
    policy = PortfolioPolicy(portfolio_nav=100_000.0)
    holdings = Holdings(as_of=as_of, positions=pd.DataFrame({"dollar_value": []}, index=pd.Index([], name="figi")))
    target = ExposureTarget(
        id="ET-BUY-MOMENTUM",
        direction=Direction.BUY,
        dollar_amount=2_000.0,
        dimension=DimensionSpec(factor="momentum"),
        rationale="Add momentum exposure.",
    )
    brief = create_brief(target)
    pitch = CompetingPitch(id="CP-MISMATCH", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-005", thesis="t")

    result = evaluate_portfolio_fit(
        pitch,
        target,
        brief,
        holdings,
        scores,
        snapshot.__class__(as_of=snapshot.as_of, securities=securities, macro=snapshot.macro),
        as_of,
        policy,
    )

    assert result.passed is True
    assert result.hard_limit_violations == ()
    assert "factor-fit-warning" in result.warnings


def test_fit_check_reports_missing_factor_score_without_fabricating_one(as_of, snapshot, scores):
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6],
        median_daily_dollar_volume=[10_000_000.0] * 5,
    )
    policy = PortfolioPolicy(portfolio_nav=100_000.0)
    holdings = Holdings(as_of=as_of, positions=pd.DataFrame({"dollar_value": []}, index=pd.Index([], name="figi")))
    target = ExposureTarget(
        id="ET-BUY-MOMENTUM",
        direction=Direction.BUY,
        dollar_amount=2_000.0,
        dimension=DimensionSpec(factor="momentum"),
        rationale="Add momentum exposure.",
    )
    brief = create_brief(target)
    pitch = CompetingPitch(id="CP-NO-SCORE", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-001", thesis="t")
    missing_score = FactorScoreMatrix(as_of=scores.as_of, scores=scores.scores.drop(index=pitch.figi), weights=scores.weights)

    result = evaluate_portfolio_fit(
        pitch,
        target,
        brief,
        holdings,
        missing_score,
        snapshot.__class__(as_of=snapshot.as_of, securities=securities, macro=snapshot.macro),
        as_of,
        policy,
    )

    assert result.passed is True
    assert result.factor_fit == {"momentum": None}
    assert "factor-data-unavailable" in result.warnings


def test_fit_check_allows_a_trade_at_exactly_the_liquidity_floor(as_of, snapshot, scores):
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6],
        median_daily_dollar_volume=[5_000_000.0, 10_000_000.0, 10_000_000.0, 10_000_000.0, 10_000_000.0],
    )
    policy = PortfolioPolicy(portfolio_nav=100_000.0)
    holdings = Holdings(as_of=as_of, positions=pd.DataFrame({"dollar_value": []}, index=pd.Index([], name="figi")))
    target = ExposureTarget(
        id="ET-BUY-MOMENTUM",
        direction=Direction.BUY,
        dollar_amount=2_000.0,
        dimension=DimensionSpec(factor="momentum"),
        rationale="Add momentum exposure.",
    )
    brief = create_brief(target)
    pitch = CompetingPitch(id="CP-FLOOR-EXACT", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-001", thesis="t")

    result = evaluate_portfolio_fit(
        pitch,
        target,
        brief,
        holdings,
        scores,
        snapshot.__class__(as_of=snapshot.as_of, securities=securities, macro=snapshot.macro),
        as_of,
        policy,
    )

    assert "minimum-liquidity" not in result.hard_limit_violations


def test_fit_check_allows_a_trade_at_exactly_the_participation_cap(as_of, snapshot, scores):
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6],
        median_daily_dollar_volume=[10_000_000.0] * 5,
    )
    policy = PortfolioPolicy(portfolio_nav=10_000_000.0)
    holdings = Holdings(as_of=as_of, positions=pd.DataFrame({"dollar_value": []}, index=pd.Index([], name="figi")))
    target = ExposureTarget(
        id="ET-BUY-MOMENTUM",
        direction=Direction.BUY,
        dollar_amount=200_000.0,
        dimension=DimensionSpec(factor="momentum"),
        rationale="Add momentum exposure.",
    )
    brief = create_brief(target)
    pitch = CompetingPitch(id="CP-PARTICIPATION-EXACT", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-001", thesis="t")

    result = evaluate_portfolio_fit(
        pitch,
        target,
        brief,
        holdings,
        scores,
        snapshot.__class__(as_of=snapshot.as_of, securities=securities, macro=snapshot.macro),
        as_of,
        policy,
    )

    assert "trade-participation-cap" not in result.hard_limit_violations


def test_fit_check_allows_a_buy_that_lands_at_exactly_the_single_name_cap(as_of, snapshot, scores):
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6],
        median_daily_dollar_volume=[10_000_000.0] * 5,
        is_russell_1000=[True] * 5,
    )
    policy = PortfolioPolicy(portfolio_nav=100_000.0)
    holdings = Holdings(
        as_of=as_of,
        positions=pd.DataFrame({"dollar_value": [8_000.0]}, index=pd.Index(["BBG-FIXTURE-001"], name="figi")),
    )
    target = ExposureTarget(
        id="ET-BUY-MOMENTUM",
        direction=Direction.BUY,
        dollar_amount=2_000.0,
        dimension=DimensionSpec(factor="momentum"),
        rationale="Add momentum exposure.",
    )
    brief = create_brief(target)
    pitch = CompetingPitch(id="CP-CAP-EXACT", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-001", thesis="t")

    result = evaluate_portfolio_fit(
        pitch,
        target,
        brief,
        holdings,
        scores,
        snapshot.__class__(as_of=snapshot.as_of, securities=securities, macro=snapshot.macro),
        as_of,
        policy,
    )

    assert result.estimated_impact["name_weight_after"] == pytest.approx(0.10)
    assert "single-name-cap" not in result.hard_limit_violations
    assert "inherited-single-name-cap" not in result.warnings


def test_fit_check_allows_a_buy_that_lands_at_exactly_the_beta_ceiling(as_of, snapshot, scores):
    securities = snapshot.securities.assign(
        market_beta_90d=[1.0, 0.7, 0.8, 1.0, 0.6],
        median_daily_dollar_volume=[10_000_000.0] * 5,
    )
    policy = PortfolioPolicy(portfolio_nav=100_000.0)
    holdings = Holdings(
        as_of=as_of,
        positions=pd.DataFrame({"dollar_value": [90_000.0]}, index=pd.Index(["BBG-FIXTURE-001"], name="figi")),
    )
    target = ExposureTarget(
        id="ET-BUY-MOMENTUM",
        direction=Direction.BUY,
        dollar_amount=10_000.0,
        dimension=DimensionSpec(factor="momentum"),
        rationale="Add momentum exposure.",
    )
    brief = create_brief(target)
    pitch = CompetingPitch(id="CP-BETA-EXACT", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-001", thesis="t")

    result = evaluate_portfolio_fit(
        pitch,
        target,
        brief,
        holdings,
        scores,
        snapshot.__class__(as_of=snapshot.as_of, securities=securities, macro=snapshot.macro),
        as_of,
        policy,
    )

    assert result.estimated_impact["portfolio_beta_after"] == pytest.approx(1.00)
    assert "portfolio-beta-ceiling" not in result.hard_limit_violations


def test_fit_check_rejects_a_buy_that_worsens_an_inherited_single_name_cap_breach(as_of, snapshot, scores):
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6],
        median_daily_dollar_volume=[10_000_000.0] * 5,
        is_russell_1000=[True] * 5,
    )
    policy = PortfolioPolicy(portfolio_nav=100_000.0)
    holdings = Holdings(
        as_of=as_of,
        positions=pd.DataFrame({"dollar_value": [11_000.0]}, index=pd.Index(["BBG-FIXTURE-001"], name="figi")),
    )
    target = ExposureTarget(
        id="ET-BUY-MOMENTUM",
        direction=Direction.BUY,
        dollar_amount=1_000.0,
        dimension=DimensionSpec(factor="momentum"),
        rationale="Add momentum exposure.",
    )
    brief = create_brief(target)
    pitch = CompetingPitch(id="CP-CAP-WORSEN", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-001", thesis="t")

    result = evaluate_portfolio_fit(
        pitch,
        target,
        brief,
        holdings,
        scores,
        snapshot.__class__(as_of=snapshot.as_of, securities=securities, macro=snapshot.macro),
        as_of,
        policy,
    )

    assert "single-name-cap" in result.hard_limit_violations
    assert "inherited-single-name-cap" not in result.warnings


def test_fit_check_rejects_a_buy_that_worsens_an_inherited_beta_ceiling_breach(as_of, snapshot, scores):
    securities = snapshot.securities.assign(
        market_beta_90d=[1.1, 0.7, 0.8, 1.0, 0.6],
        median_daily_dollar_volume=[10_000_000.0] * 5,
    )
    policy = PortfolioPolicy(portfolio_nav=100_000.0)
    holdings = Holdings(
        as_of=as_of,
        positions=pd.DataFrame({"dollar_value": [100_000.0]}, index=pd.Index(["BBG-FIXTURE-001"], name="figi")),
    )
    target = ExposureTarget(
        id="ET-BUY-BETA",
        direction=Direction.BUY,
        dollar_amount=20_000.0,
        dimension=DimensionSpec(factor="momentum"),
        rationale="Add momentum exposure.",
    )
    brief = create_brief(target)
    pitch = CompetingPitch(id="CP-BETA-WORSEN", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-001", thesis="t")

    result = evaluate_portfolio_fit(
        pitch,
        target,
        brief,
        holdings,
        scores,
        snapshot.__class__(as_of=snapshot.as_of, securities=securities, macro=snapshot.macro),
        as_of,
        policy,
    )

    assert result.estimated_impact["portfolio_beta_before"] == pytest.approx(1.1)
    assert result.estimated_impact["portfolio_beta_after"] == pytest.approx(1.32)
    assert "portfolio-beta-ceiling" in result.hard_limit_violations


def test_fit_result_order_is_wired_from_the_real_pitch_and_target_not_a_stand_in(as_of, snapshot, scores):
    """`PortfolioFitResult.order` is what `advisor_queue._validate_approval_attestations`
    binds admission to (`fit.order == proposal.order`) -- but every test of
    that binding hand-constructs its own already-correct `PortfolioFitResult`.
    Nothing else proves `evaluate_portfolio_fit()` itself actually populates
    `.order` from the real pitch/target it was given, rather than `None` or
    a stale/default value."""
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6], median_daily_dollar_volume=[10_000_000.0] * 5
    )
    target = ExposureTarget(
        id="ET-ORDER-WIRING",
        direction=Direction.BUY,
        dollar_amount=4_500.0,
        dimension=DimensionSpec(factor="momentum"),
        rationale="test",
    )
    brief = create_brief(target)
    pitch = CompetingPitch(id="CP-ORDER-WIRING", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-001", thesis="t")

    result = evaluate_portfolio_fit(
        pitch, target, brief,
        Holdings(as_of, pd.DataFrame({"dollar_value": []}, index=pd.Index([], name="figi"))), scores,
        snapshot.__class__(as_of, securities, snapshot.macro), as_of, PortfolioPolicy(portfolio_nav=100_000.0),
    )

    assert result.order is not None
    assert result.order.figi == "BBG-FIXTURE-001"
    assert result.order.direction is Direction.BUY
    assert result.order.dollar_amount == 4_500.0
    assert result.order.pitch_id == "CP-ORDER-WIRING"
    assert result.order.brief_id == brief.id
    assert result.order.target_id == "ET-ORDER-WIRING"
    assert result.passed is True
    assert brief.status == "approved"


def test_fit_check_brief_status_stays_open_on_a_failing_result(as_of, snapshot, scores):
    """Mirrors `test_evaluate_pitch.py`'s equivalent assertion for
    `evaluate_pitch` -- but `evaluate_portfolio_fit` writes `brief.status`
    itself too (a separate line), and nothing in this file checked it."""
    securities = snapshot.securities.assign(
        market_beta_90d=[0.9, 0.7, 0.8, 1.0, 0.6],
        median_daily_dollar_volume=[10_000_000.0] * 5,
        is_russell_1000=[True] * 5,
    )
    target = ExposureTarget(
        id="ET-STATUS-OPEN",
        direction=Direction.BUY,
        dollar_amount=2_000.0,
        dimension=DimensionSpec(factor="momentum"),
        rationale="test",
    )
    brief = create_brief(target)
    pitch = CompetingPitch(id="CP-STATUS-OPEN", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-001", thesis="t")

    result = evaluate_portfolio_fit(
        pitch, target, brief,
        Holdings(as_of, pd.DataFrame({"dollar_value": [95_000.0]}, index=pd.Index(["BBG-FIXTURE-001"], name="figi"))),
        scores, snapshot.__class__(as_of, securities, snapshot.macro), as_of, PortfolioPolicy(portfolio_nav=100_000.0),
    )

    assert result.passed is False
    assert "single-name-cap" in result.hard_limit_violations
    assert brief.status == "open"
