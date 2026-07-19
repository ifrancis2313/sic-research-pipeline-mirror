from dataclasses import replace

import pandas as pd
import pytest

from qepm.backtest_gate import evaluate_portfolio_fit
from qepm.contracts import (
    CompetingPitch,
    DimensionSpec,
    Direction,
    ExposureTarget,
    Holdings,
    PhaseGateError,
    PortfolioPolicy,
)
from qepm.exposure_optimizer import generate_exposure_targets
from qepm.portfolio_state import validate_portfolio_policy
from qepm.research_brief_tracker import create_brief


def _target(*, direction: object = Direction.BUY, dollar_amount: object = 2_000.0) -> ExposureTarget:
    return ExposureTarget(
        id="ET-STATE",
        direction=direction,  # type: ignore[arg-type]  # malformed boundary-input test
        dollar_amount=dollar_amount,  # type: ignore[arg-type]  # malformed boundary-input test
        dimension=DimensionSpec(factor="momentum"),
        rationale="test",
    )


@pytest.mark.parametrize("amount", [float("inf"), float("-inf"), float("nan"), 0.0, -1.0])
def test_brief_gate_rejects_nonfinite_or_nonpositive_target_amount(amount):
    with pytest.raises(PhaseGateError, match="dollar_amount"):
        create_brief(_target(dollar_amount=amount))


def test_brief_gate_rejects_string_direction():
    with pytest.raises(PhaseGateError, match="direction must be a Direction"):
        create_brief(_target(direction="buy"))


def test_portfolio_fit_rejects_duplicate_holdings_figi(as_of, snapshot, scores):
    target = _target()
    brief = create_brief(target)
    pitch = CompetingPitch("CP-STATE", brief.id, "pod", snapshot.securities.index[0], "thesis")
    duplicated = Holdings(
        as_of,
        pd.DataFrame({"dollar_value": [1_000.0, 2_000.0]}, index=[snapshot.securities.index[0]] * 2),
    )

    with pytest.raises(PhaseGateError, match="unique FIGI"):
        evaluate_portfolio_fit(
            pitch, target, brief, duplicated, scores, snapshot, as_of, PortfolioPolicy(portfolio_nav=100_000.0)
        )


@pytest.mark.parametrize("amount", [float("inf"), float("-inf"), float("nan"), -0.01])
def test_optimizer_rejects_nonfinite_or_negative_holdings(amount, snapshot, scores, as_of):
    holdings = Holdings(
        as_of,
        pd.DataFrame({"dollar_value": [amount]}, index=pd.Index([snapshot.securities.index[0]], name="figi")),
    )

    with pytest.raises(PhaseGateError, match="non-finite or negative"):
        generate_exposure_targets(snapshot, scores, holdings)


def test_optimizer_rejects_held_figi_absent_from_snapshot(snapshot, scores, as_of):
    holdings = Holdings(
        as_of,
        pd.DataFrame({"dollar_value": [1_000.0]}, index=pd.Index(["NOT-IN-SNAPSHOT"], name="figi")),
    )

    with pytest.raises(PhaseGateError, match="absent from the snapshot"):
        generate_exposure_targets(snapshot, scores, holdings)


def test_optimizer_rejects_duplicate_snapshot_figi(snapshot, scores, holdings):
    duplicated_snapshot = replace(snapshot, securities=pd.concat([snapshot.securities, snapshot.securities.iloc[[0]]]))

    with pytest.raises(PhaseGateError, match="unique FIGI"):
        generate_exposure_targets(duplicated_snapshot, scores, holdings)


def test_policy_accepts_exactly_coherent_boundaries_and_rejects_just_above_fraction():
    valid = PortfolioPolicy(
        portfolio_nav=100_000.0,
        max_single_name_weight=1.0,
        max_trade_volume_fraction=1.0,
        beta_target_minimum=1.0,
        beta_target_maximum=1.0,
        beta_warning=1.0,
        beta_ceiling=1.0,
        factor_priority_score=50.0,
        factor_watch_score=50.0,
        factor_target_score=50.0,
        core_sleeve_minimum=0.20,
        core_sleeve_maximum=0.20,
        experimental_sleeve_minimum=0.15,
        experimental_sleeve_maximum=0.15,
        normal_cash_maximum=1.0,
    )
    validate_portfolio_policy(valid)

    with pytest.raises(PhaseGateError, match="must not exceed 1"):
        validate_portfolio_policy(replace(valid, max_single_name_weight=1.000001))


@pytest.mark.parametrize(
    "replacement, message",
    [
        ({"portfolio_nav": 0.0}, "portfolio_nav"),
        ({"portfolio_nav": float("nan")}, "portfolio_nav"),
        ({"beta_target_maximum": 0.74}, "beta thresholds"),
        ({"factor_watch_score": 20.0}, "factor thresholds"),
        ({"core_sleeve_minimum": 0.26}, "core sleeve minimum"),
        ({"material_price_move_fraction": 0.0}, "material_price_move_fraction"),
        ({"material_price_move_fraction": float("nan")}, "material_price_move_fraction"),
    ],
)
def test_policy_rejects_incoherent_controls(replacement, message):
    with pytest.raises(PhaseGateError, match=message):
        validate_portfolio_policy(replace(PortfolioPolicy(portfolio_nav=100_000.0), **replacement))
