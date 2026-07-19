"""Property-based tests for the sector-relative and universe-relative
percentile helpers behind V1's Value/Quality (sector) and Momentum/Size
(universe) factors.

These are the two functions every V1 factor score ultimately passes
through, so a bug here silently distorts every research brief the
optimizer generates -- exactly the kind of pure-math correctness that
should be pinned by properties, not just the specific numeric examples
in tests/factor_registry/test_v1_factors.py.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from hypothesis import given
from hypothesis import strategies as st

from qepm.contracts import Snapshot
from qepm.factor_registry.v1 import _sector_percentile, _universe_percentile

_FINITE_VALUE = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)


def _snapshot_with_sectors(sectors: list[str]) -> Snapshot:
    figis = [f"FIGI-{i}" for i in range(len(sectors))]
    return Snapshot(
        as_of=date(2026, 7, 4),
        securities=pd.DataFrame({"sector": sectors}, index=pd.Index(figis, name="figi")),
        macro=pd.DataFrame(index=pd.DatetimeIndex([], name="date")),
    )


@given(values=st.lists(_FINITE_VALUE, min_size=3, max_size=10, unique=True))
def test_universe_percentile_is_always_between_zero_and_100(values):
    figis = [f"FIGI-{i}" for i in range(len(values))]
    series = pd.Series(values, index=figis)

    result = _universe_percentile(series)

    assert ((result > 0.0) & (result <= 100.0)).all()


@given(values=st.lists(_FINITE_VALUE, min_size=3, max_size=10, unique=True))
def test_universe_percentile_gives_the_strict_maximum_a_perfect_100(values):
    figis = [f"FIGI-{i}" for i in range(len(values))]
    series = pd.Series(values, index=figis)
    winner = series.idxmax()

    result = _universe_percentile(series)

    assert result[winner] == 100.0


@given(values=st.lists(_FINITE_VALUE, min_size=4, max_size=10, unique=True))
def test_universe_percentile_is_monotonic_in_the_underlying_value(values):
    figis = [f"FIGI-{i}" for i in range(len(values))]
    series = pd.Series(values, index=figis)
    ordered = series.sort_values()

    result = _universe_percentile(series)
    ranks_in_value_order = result.reindex(ordered.index).tolist()

    assert ranks_in_value_order == sorted(ranks_in_value_order)


@given(
    sector_a_values=st.lists(_FINITE_VALUE, min_size=2, max_size=6, unique=True),
    sector_b_values=st.lists(_FINITE_VALUE, min_size=2, max_size=6, unique=True),
)
def test_sector_percentile_never_compares_across_sectors(sector_a_values, sector_b_values):
    """A security's sector-relative rank must depend only on its own
    sector's peers -- moving a completely disjoint sector's values should
    never change another sector's already-computed percentiles. This is
    the property that makes "sector-relative" actually sector-relative,
    rather than an accidental full-universe rank that happens to look
    right on hand-picked examples."""
    sectors = ["Tech"] * len(sector_a_values) + ["Energy"] * len(sector_b_values)
    values = sector_a_values + sector_b_values
    figis = [f"FIGI-{i}" for i in range(len(values))]
    snapshot = _snapshot_with_sectors(sectors)
    series = pd.Series(values, index=figis)

    result_full = _sector_percentile(snapshot, series)

    tech_only_snapshot = _snapshot_with_sectors(["Tech"] * len(sector_a_values))
    tech_only_series = pd.Series(sector_a_values, index=[f"FIGI-{i}" for i in range(len(sector_a_values))])
    result_tech_only = _sector_percentile(tech_only_snapshot, tech_only_series)

    for i in range(len(sector_a_values)):
        assert result_full[f"FIGI-{i}"] == result_tech_only[f"FIGI-{i}"]


@given(value=_FINITE_VALUE)
def test_sector_percentile_is_na_for_a_lone_sector_member(value):
    """A sector with exactly one scored constituent has no real
    cross-sectional information -- it must come back N/A, never a
    mechanically-perfect 100. (Pins the round-1 regression this codebase
    was specifically fixed for, as a property covering every possible
    single value, not just one hand-picked example.)"""
    snapshot = _snapshot_with_sectors(["Solo"])
    series = pd.Series([value], index=["FIGI-0"])

    result = _sector_percentile(snapshot, series)

    assert pd.isna(result["FIGI-0"])
