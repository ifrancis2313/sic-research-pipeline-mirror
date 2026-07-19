"""Property-based tests for scoring.py's pure blend/rank math.

Example-based tests (tests/test_scoring.py) pin specific numbers; these
pin the general invariants that must hold for *any* valid input, the
kind of thing a hand-picked example can miss.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from hypothesis import assume, given
from hypothesis import strategies as st

from qepm.contracts import FactorScoreMatrix
from qepm.scoring import combined_factor_score, percentile_rank_score

_FINITE_SCORE = st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False)
_FIGIS = ["FIGI-A", "FIGI-B", "FIGI-C"]


def _matrix(value_a: float, value_b: float, value_c: float, weight: float) -> FactorScoreMatrix:
    return FactorScoreMatrix(
        as_of=date(2026, 7, 4),
        scores=pd.DataFrame({"only_factor": [value_a, value_b, value_c]}, index=_FIGIS),
        weights={"only_factor": weight},
    )


@given(value_a=_FINITE_SCORE, value_b=_FINITE_SCORE, value_c=_FINITE_SCORE)
def test_single_factor_blend_is_the_identity(value_a, value_b, value_c):
    """With one factor at weight 1.0, the blend is exactly that factor's own scores."""
    result = combined_factor_score(_matrix(value_a, value_b, value_c, weight=1.0))

    assert result["FIGI-A"] == value_a
    assert result["FIGI-B"] == value_b
    assert result["FIGI-C"] == value_c


@given(
    value_a=_FINITE_SCORE,
    value_b=_FINITE_SCORE,
    value_c=_FINITE_SCORE,
    scale=st.floats(min_value=0.01, max_value=100.0, allow_nan=False, allow_infinity=False),
)
def test_blend_is_invariant_to_uniformly_rescaling_every_weight(value_a, value_b, value_c, scale):
    """combined_factor_score normalizes by total_weight, so scaling every
    factor's weight by the same positive constant must not change the result
    -- it's a *relative* blend, not an absolute one. This is the property
    that makes "equal weighting" and "all weights doubled" mean the same
    thing, which the codebase relies on implicitly (score_universe's real
    weights vs. a hand-built test matrix's default weight of 1.0)."""
    baseline = combined_factor_score(
        FactorScoreMatrix(
            as_of=date(2026, 7, 4),
            scores=pd.DataFrame({"a": [value_a, value_b, value_c]}, index=_FIGIS),
            weights={"a": 1.0},
        )
    )
    rescaled = combined_factor_score(
        FactorScoreMatrix(
            as_of=date(2026, 7, 4),
            scores=pd.DataFrame({"a": [value_a, value_b, value_c]}, index=_FIGIS),
            weights={"a": scale},
        )
    )

    pd.testing.assert_series_equal(baseline, rescaled, check_exact=False, atol=1e-9)


@given(
    real_value=_FINITE_SCORE,
    zero_weight_value=st.one_of(_FINITE_SCORE, st.just(float("nan"))),
)
def test_zero_weighted_factor_never_changes_the_result_even_when_nan(real_value, zero_weight_value):
    """A monitor-only (zero-weight) factor must have zero effect on the
    blend -- including when its own value is NaN. This pins down, as a
    property rather than one hand-picked example, the exact bug
    (`NaN * 0.0 == NaN` in IEEE 754) this function's own comment says it
    guards against."""
    with_real_factor_only = FactorScoreMatrix(
        as_of=date(2026, 7, 4),
        scores=pd.DataFrame({"real": [real_value]}, index=["FIGI-A"]),
        weights={"real": 1.0},
    )
    with_zero_weight_monitor_added = FactorScoreMatrix(
        as_of=date(2026, 7, 4),
        scores=pd.DataFrame({"real": [real_value], "monitor": [zero_weight_value]}, index=["FIGI-A"]),
        weights={"real": 1.0, "monitor": 0.0},
    )

    baseline = combined_factor_score(with_real_factor_only)
    with_monitor = combined_factor_score(with_zero_weight_monitor_added)

    assert baseline["FIGI-A"] == with_monitor["FIGI-A"]


@given(
    lo=st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    hi=st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    frac_a=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    frac_b=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    # Deliberately excludes weights below 1e-6: a real FactorDefinition.weight
    # is a human-configured registry value (V1's own weights are all 0.0 or
    # 1.0), never a denormalized float. Hypothesis found that a weight near
    # the bottom of the float64 range (e.g. 5e-324, the smallest positive
    # double) makes `weighted_sum / total_weight` lose enough precision to
    # land outside [lo, hi] by a wide margin -- a genuine float-precision
    # artifact at a magnitude no real weight will ever take, not a logic bug.
    # Same pattern as excluding near-zero T/vol in Black-Scholes property
    # tests: bound the input to the domain the function is actually used in,
    # and don't chase unkillable noise at the edge of float64 representation.
    weight_a=st.floats(min_value=0.0, max_value=100.0, allow_nan=False).filter(lambda w: w == 0.0 or w >= 1e-6),
    weight_b=st.floats(min_value=0.0, max_value=100.0, allow_nan=False).filter(lambda w: w == 0.0 or w >= 1e-6),
)
def test_blend_never_exceeds_the_range_of_its_inputs(lo, hi, frac_a, frac_b, weight_a, weight_b):
    """A weighted average is a convex combination: for one security, the
    blended score can never fall outside [min(factor scores), max(factor
    scores)] for that security. This would catch a sign error or a
    mis-normalized weight producing an out-of-range blended score."""
    assume(weight_a + weight_b > 0)
    lo, hi = (lo, hi) if lo <= hi else (hi, lo)
    value_a = lo + frac_a * (hi - lo)
    value_b = lo + frac_b * (hi - lo)

    result = combined_factor_score(
        FactorScoreMatrix(
            as_of=date(2026, 7, 4),
            scores=pd.DataFrame({"a": [value_a], "b": [value_b]}, index=["FIGI-A"]),
            weights={"a": weight_a, "b": weight_b},
        )
    )

    assert lo - 1e-6 <= result["FIGI-A"] <= hi + 1e-6


@given(values=st.lists(_FINITE_SCORE, min_size=2, max_size=8, unique=True))
def test_percentile_rank_is_always_between_zero_and_ten(values):
    figis = [f"FIGI-{i}" for i in range(len(values))]
    series = pd.Series(values, index=figis)

    for figi in figis:
        rank = percentile_rank_score(figi, series)
        assert 0.0 < rank <= 10.0


@given(values=st.lists(_FINITE_SCORE, min_size=2, max_size=8, unique=True))
def test_percentile_rank_gives_the_strict_maximum_a_perfect_ten(values):
    figis = [f"FIGI-{i}" for i in range(len(values))]
    series = pd.Series(values, index=figis)
    winner = series.idxmax()

    assert percentile_rank_score(winner, series) == 10.0


@given(values=st.lists(_FINITE_SCORE, min_size=3, max_size=8, unique=True))
def test_percentile_rank_is_monotonic_in_the_underlying_value(values):
    """A strictly higher raw value must never produce a strictly lower
    percentile rank -- this is the property that makes "percentile rank"
    a meaningful ordering rather than an arbitrary transformation."""
    figis = [f"FIGI-{i}" for i in range(len(values))]
    series = pd.Series(values, index=figis)
    ordered = series.sort_values()

    ranks = [percentile_rank_score(figi, series) for figi in ordered.index]

    assert ranks == sorted(ranks)
