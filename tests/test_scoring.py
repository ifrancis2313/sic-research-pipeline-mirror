from datetime import date

import pandas as pd
import pytest

from qepm.contracts import FactorScoreMatrix, ScreenPredicate
from qepm.scoring import combined_factor_score, evaluate_screen_predicate, percentile_rank_score


def _matrix(scores_dict: dict, weights: dict[str, float] | None = None) -> FactorScoreMatrix:
    scores = pd.DataFrame(scores_dict, index=["F1", "F2", "F3"])
    scores.index.name = "figi"
    return FactorScoreMatrix(as_of=date(2026, 1, 1), scores=scores, weights=weights or {})


def test_combined_factor_score_defaults_to_equal_weight_when_weights_missing():
    matrix = _matrix({"a": [1.0, 2.0, 3.0], "b": [3.0, 2.0, 1.0]})

    combined = combined_factor_score(matrix)

    assert combined.loc["F1"] == pytest.approx(2.0)
    assert combined.loc["F2"] == pytest.approx(2.0)
    assert combined.loc["F3"] == pytest.approx(2.0)


def test_combined_factor_score_respects_registry_weights():
    matrix = _matrix({"a": [1.0, 2.0, 3.0], "b": [3.0, 2.0, 1.0]}, weights={"a": 3.0, "b": 1.0})

    combined = combined_factor_score(matrix)

    # weighted average: (a*3 + b*1) / 4
    assert combined.loc["F1"] == pytest.approx((1.0 * 3 + 3.0 * 1) / 4)
    assert combined.loc["F3"] == pytest.approx((3.0 * 3 + 1.0 * 1) / 4)


def test_combined_factor_score_raises_when_all_weights_zero():
    matrix = _matrix({"a": [1.0, 2.0, 3.0]}, weights={"a": 0.0})

    with pytest.raises(ValueError, match="all factor weights are zero"):
        combined_factor_score(matrix)


def test_zero_weight_missing_monitor_does_not_poison_combined_score():
    matrix = _matrix({"value": [1.0, 2.0, 3.0], "size": [float("nan")] * 3}, weights={"value": 1.0, "size": 0.0})

    combined = combined_factor_score(matrix)

    assert combined.tolist() == [1.0, 2.0, 3.0]


@pytest.mark.parametrize("weight", [-1.0, float("nan"), float("inf")])
def test_combined_factor_score_rejects_invalid_weights(weight):
    matrix = _matrix({"a": [1.0, 2.0, 3.0]}, weights={"a": weight})

    with pytest.raises(ValueError, match="finite and non-negative"):
        combined_factor_score(matrix)


def test_percentile_rank_score_ranks_highest_value_as_ten():
    series = pd.Series([1.0, 2.0, 3.0], index=["F1", "F2", "F3"])

    assert percentile_rank_score("F3", series) == pytest.approx(10.0)
    assert percentile_rank_score("F1", series) == pytest.approx(10.0 / 3)


def test_evaluate_screen_predicate_supports_standard_operators():
    assert evaluate_screen_predicate(ScreenPredicate(field="x", op=">", threshold=5.0), 6.0) is True
    assert evaluate_screen_predicate(ScreenPredicate(field="x", op=">", threshold=5.0), 4.0) is False
    assert evaluate_screen_predicate(ScreenPredicate(field="x", op="<=", threshold=5.0), 5.0) is True
    assert evaluate_screen_predicate(ScreenPredicate(field="x", op="==", threshold=5.0), 5.0) is True


def test_evaluate_screen_predicate_raises_on_unsupported_operator():
    with pytest.raises(ValueError, match="unsupported screen operator"):
        evaluate_screen_predicate(ScreenPredicate(field="x", op="~=", threshold=5.0), 5.0)
