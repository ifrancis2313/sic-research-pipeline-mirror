import numpy as np
import pytest

from qepm.contracts import FactorScoreMatrix, Holdings, PhaseGateError
from qepm.exposure_optimizer import generate_exposure_targets


def test_rejects_scores_not_indexed_by_figi(snapshot, scores, holdings):
    bad_scores = FactorScoreMatrix(
        as_of=scores.as_of, scores=scores.scores.reset_index(drop=True)
    )

    with pytest.raises(PhaseGateError, match="figi"):
        generate_exposure_targets(snapshot, bad_scores, holdings)


def test_rejects_scores_with_no_factor_columns(snapshot, scores, holdings):
    bad_scores = FactorScoreMatrix(as_of=scores.as_of, scores=scores.scores.drop(columns=["momentum"]))

    with pytest.raises(PhaseGateError, match="no factor columns"):
        generate_exposure_targets(snapshot, bad_scores, holdings)


def test_rejects_scores_that_are_entirely_missing(snapshot, scores, holdings):
    all_nan = scores.scores.copy()
    all_nan["momentum"] = np.nan
    bad_scores = FactorScoreMatrix(as_of=scores.as_of, scores=all_nan)

    with pytest.raises(PhaseGateError, match="entirely missing"):
        generate_exposure_targets(snapshot, bad_scores, holdings)


@pytest.mark.parametrize("bad_value", [np.inf, -np.inf])
def test_rejects_infinite_scores_but_allows_nan_as_documented_na(snapshot, scores, holdings, bad_value):
    infinite = scores.scores.copy()
    infinite.iloc[0, 0] = bad_value
    with pytest.raises(PhaseGateError, match="non-finite"):
        generate_exposure_targets(snapshot, FactorScoreMatrix(as_of=scores.as_of, scores=infinite), holdings)

    missing = scores.scores.copy()
    missing.iloc[0, 0] = np.nan
    generate_exposure_targets(snapshot, FactorScoreMatrix(as_of=scores.as_of, scores=missing), holdings)


def test_rejects_mixed_snapshot_dates(snapshot, scores, holdings):
    later_holdings = Holdings(
        as_of=scores.as_of.replace(day=scores.as_of.day + 1), positions=holdings.positions
    )

    with pytest.raises(PhaseGateError, match="same as_of"):
        generate_exposure_targets(snapshot, scores, later_holdings)


@pytest.mark.parametrize(
    ("constraints", "message"),
    [
        ({"portfolio_nav": 0.0}, "portfolio_nav"),
        ({"portfolio_nav": float("inf")}, "portfolio_nav"),
        ({"min_dollar_size": 0.0}, "min_dollar_size"),
        ({"min_dollar_size": float("nan")}, "min_dollar_size"),
        ({"screen_field": ""}, "screen_field"),
    ],
)
def test_rejects_malformed_optimizer_constraints(constraints, message, snapshot, scores, holdings):
    with pytest.raises(PhaseGateError, match=message):
        generate_exposure_targets(snapshot, scores, holdings, constraints)
