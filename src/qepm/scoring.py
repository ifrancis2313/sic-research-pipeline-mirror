"""Small scoring utilities shared across modules that combine or rank factor scores.

Kept here rather than duplicated in exposure_optimizer / backtest_gate /
research_brief_tracker.rubric, since all three need the same "blend
every adopted factor into one score" and "rank a security within the
universe" operations.
"""

from __future__ import annotations

import operator as _operator
from math import isfinite

import pandas as pd

from qepm.contracts import FactorScoreMatrix, ScreenPredicate

_OPERATORS = {
    ">": _operator.gt,
    "<": _operator.lt,
    ">=": _operator.ge,
    "<=": _operator.le,
    "==": _operator.eq,
}


def percentile_rank_score(figi: str, series: pd.Series) -> float:
    """A security's percentile rank within series, scaled 0-10 (10 = best in the universe)."""
    return float(series.rank(pct=True).loc[figi]) * 10.0


def combined_factor_score(scores: FactorScoreMatrix) -> pd.Series:
    """The equal-or-weighted blend of every adopted factor, per FactorDefinition.weight.

    A factor missing from scores.weights defaults to weight 1.0 (equal
    weighting) - this keeps hand-built FactorScoreMatrix objects (e.g. in
    tests) working without requiring an explicit weights dict, while
    score_universe's real output uses each registered factor's actual
    weight.
    """
    columns = scores.scores.columns
    weights = {name: scores.weights.get(name, 1.0) for name in columns}
    invalid_weights = [name for name, weight in weights.items() if not isfinite(weight) or weight < 0]
    if invalid_weights:
        raise ValueError(f"combined_factor_score: weights must be finite and non-negative: {invalid_weights}")
    total_weight = sum(weights.values())
    if total_weight == 0:
        raise ValueError("combined_factor_score: all factor weights are zero - nothing to blend")

    # A monitor with zero allocation must not turn an otherwise valid blend
    # into NaN through IEEE's undefined 0 * NaN operation.
    weighted_sum = sum(
        (scores.scores[name] * weight for name, weight in weights.items() if weight > 0),
        start=pd.Series(0.0, index=scores.scores.index),
    )
    return weighted_sum / total_weight


def evaluate_screen_predicate(predicate: ScreenPredicate, value: float) -> bool:
    """Whether value passes predicate, without depending on any display-string formatting."""
    op_func = _OPERATORS.get(predicate.op)
    if op_func is None:
        raise ValueError(f"unsupported screen operator: {predicate.op!r}")
    return bool(op_func(value, predicate.threshold))
