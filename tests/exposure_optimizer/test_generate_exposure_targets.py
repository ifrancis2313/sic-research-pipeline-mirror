import math

import pytest

from qepm.contracts import Direction, Snapshot
from qepm.exposure_optimizer import generate_exposure_targets
from qepm.factor_registry import FactorRegistry, score_universe
from qepm.factor_registry.stub_factors import STUB_MACRO_ADJUSTED_MOMENTUM, STUB_MOMENTUM
from qepm.factor_registry.v1 import v1_factor_registry


def _find(targets, **dimension_fields):
    return next(
        t
        for t in targets
        if all(getattr(t.dimension, field) == value for field, value in dimension_fields.items())
    )


def test_returns_targets_in_both_directions_from_one_run(snapshot, scores, holdings):
    targets = generate_exposure_targets(snapshot, scores, holdings)

    assert any(t.direction is Direction.BUY for t in targets)
    assert any(t.direction is Direction.SELL for t in targets)


def test_sector_and_factor_combined_dimension(snapshot, scores, holdings):
    targets = generate_exposure_targets(snapshot, scores, holdings)

    target = _find(targets, sector="Energy", factor="momentum")
    assert target.direction is Direction.BUY
    assert target.dollar_amount == pytest.approx(21_882.35, abs=0.01)
    assert target.dimension.screen is None
    assert target.source_bucket == ()


def test_sector_alone_is_a_single_dimension_target(snapshot, scores, holdings):
    targets = generate_exposure_targets(snapshot, scores, holdings)

    # with a single adopted factor, the "combined" blend equals that factor,
    # so the sector-alone target should size identically to the sector+factor one
    target = _find(targets, sector="Energy", factor=None, screen=None)
    assert target.direction is Direction.BUY
    assert target.dollar_amount == pytest.approx(21_882.35, abs=0.01)


def test_sector_and_screen_is_a_combined_dimension_target(snapshot, scores, holdings):
    targets = generate_exposure_targets(snapshot, scores, holdings)

    screen_targets = [t for t in targets if t.dimension.screen is not None]
    assert screen_targets  # at least one screen-scoped target was generated
    energy_screen = _find(targets, sector="Energy", screen=screen_targets[0].dimension.screen)
    assert energy_screen.direction is Direction.BUY
    assert "fcf_yield" in energy_screen.dimension.screen
    # Pins the actual computed target_weight/gap math (n_passing / total_passing,
    # target_weight - current_weight), not just that a target of some size exists.
    assert energy_screen.dollar_amount == pytest.approx(41_000.0, abs=0.01)
    consumer_staples_screen = _find(targets, sector="Consumer Staples", screen=screen_targets[0].dimension.screen)
    assert consumer_staples_screen.dollar_amount == pytest.approx(38_000.0, abs=0.01)


def test_screen_with_nothing_passing_produces_no_targets_at_all(snapshot, scores, holdings):
    """total_passing == 0 is an early-return special case, not just a
    smaller result -- dividing n_passing/total_passing without it would be
    a literal 0/0 producing NaN target weights across every sector."""
    securities = snapshot.securities.assign(fcf_yield=[float("-inf")] * len(snapshot.securities))
    all_fail_snapshot = snapshot.__class__(as_of=snapshot.as_of, securities=securities, macro=snapshot.macro)

    targets = generate_exposure_targets(all_fail_snapshot, scores, holdings)

    assert not any(math.isnan(t.dollar_amount) for t in targets)
    assert not any(t.dimension.screen is not None for t in targets)


def test_screen_target_carries_a_structured_predicate_not_just_display_text(snapshot, scores, holdings):
    targets = generate_exposure_targets(snapshot, scores, holdings)

    screen_target = next(t for t in targets if t.dimension.screen_predicate is not None)

    predicate = screen_target.dimension.screen_predicate
    assert predicate.field == "fcf_yield"
    assert predicate.op == ">"
    assert predicate.threshold == pytest.approx(0.0320, abs=1e-4)


def test_sell_target_includes_the_specific_overexposed_holdings_bucket(snapshot, scores, holdings):
    targets = generate_exposure_targets(snapshot, scores, holdings)

    target = _find(targets, sector="Industrials", factor="momentum")
    assert target.direction is Direction.SELL
    assert target.dollar_amount == pytest.approx(6_176.47, abs=0.01)
    assert target.source_bucket == ("BBG-FIXTURE-005",)


def test_empty_dict_constraints_is_valid_and_matches_the_default(snapshot, scores, holdings):
    default_targets = generate_exposure_targets(snapshot, scores, holdings, constraints=None)
    explicit_empty_targets = generate_exposure_targets(snapshot, scores, holdings, constraints={})

    assert len(default_targets) == len(explicit_empty_targets) > 0
    assert {t.id for t in default_targets} == {t.id for t in explicit_empty_targets}


def test_portfolio_nav_is_overridable_via_constraints(snapshot, scores, holdings):
    default_targets = generate_exposure_targets(snapshot, scores, holdings)
    scaled_targets = generate_exposure_targets(
        snapshot, scores, holdings, constraints={"portfolio_nav": 200_000.0}
    )

    default_buy = _find(default_targets, sector="Energy", factor="momentum")
    scaled_buy = _find(scaled_targets, sector="Energy", factor="momentum")
    # doubling nav shrinks Energy's current weight (fixed dollar holding / bigger nav),
    # widening the gap - so the buy target grows, though not linearly since holdings don't scale with nav
    assert scaled_buy.dollar_amount > default_buy.dollar_amount


def test_min_dollar_size_constraint_prunes_small_gaps(snapshot, scores, holdings):
    default_targets = generate_exposure_targets(snapshot, scores, holdings)
    strict_targets = generate_exposure_targets(
        snapshot, scores, holdings, constraints={"min_dollar_size": 50_000.0}
    )

    assert len(strict_targets) < len(default_targets)


def test_sector_with_entirely_missing_scores_produces_no_nan_target(snapshot, scores, holdings):
    # A sector where every security's factor score is missing (e.g. a vendor
    # coverage gap) must not produce a garbage target. Previously this NaN'd
    # out dollar_amount, and NaN comparisons are always False - so it slipped
    # past both the `abs(gap) < min_dollar_size` skip and
    # validate_target_for_brief's `dollar_amount <= 0` gate, reaching a brief
    # as "trim a holding worth $nan."
    sectors = snapshot.securities["sector"]
    scores.scores.loc[sectors[sectors == "Energy"].index, "momentum"] = float("nan")

    targets = generate_exposure_targets(snapshot, scores, holdings)

    assert not any(math.isnan(t.dollar_amount) for t in targets)
    assert not any(t.dimension.sector == "Energy" and t.dimension.factor == "momentum" for t in targets)
    # Energy sorts second of five sectors alphabetically (the order
    # by_sector.iterrows() actually visits them in) -- skipping it must not
    # silently stop the loop from reaching the sectors that come after it.
    later_sectors = {"Industrials", "Materials", "Technology"}
    assert later_sectors <= {
        t.dimension.sector for t in targets if t.dimension.factor == "momentum" and t.dimension.screen is None
    }


def test_adding_a_second_factor_widens_breadth_without_touching_the_first(snapshot, holdings):
    registry = FactorRegistry()
    registry.register(STUB_MOMENTUM)
    registry.register(STUB_MACRO_ADJUSTED_MOMENTUM)
    scores = score_universe(snapshot, registry)

    targets = generate_exposure_targets(snapshot, scores, holdings)

    factors_represented = {t.dimension.factor for t in targets}
    assert {"momentum", "macro_adjusted_momentum"} <= factors_represented
    # the original momentum-only sector+factor target is unchanged by the second factor's presence
    momentum_energy = _find(targets, sector="Energy", factor="momentum")
    assert momentum_energy.dollar_amount == pytest.approx(21_882.35, abs=0.01)


def test_a_persistent_gap_across_two_weekly_runs_does_not_collide_on_id(snapshot, scores, holdings):
    """A sector/factor gap that's still open on a later Friday must mint a
    distinct ExposureTarget.id, not the same string as the earlier run's
    still-open brief -- otherwise persisting brief state (a future
    workbook/governance record keyed on brief.id) would silently merge two
    different weeks' research needs into one identity."""
    first_run = generate_exposure_targets(snapshot, scores, holdings)
    first_id = _find(first_run, sector="Energy", factor="momentum").id

    later_snapshot = Snapshot(as_of=snapshot.as_of.replace(day=snapshot.as_of.day + 7), securities=snapshot.securities, macro=snapshot.macro)
    later_scores = scores.__class__(as_of=later_snapshot.as_of, scores=scores.scores, weights=scores.weights)
    later_holdings = holdings.__class__(as_of=later_snapshot.as_of, positions=holdings.positions)

    second_run = generate_exposure_targets(later_snapshot, later_scores, later_holdings)
    second_id = _find(second_run, sector="Energy", factor="momentum").id

    assert first_id != second_id
    assert first_id.rsplit("-", 1)[0] == second_id.rsplit("-", 1)[0]  # same gap, only the date segment differs


def test_re_running_the_same_snapshot_is_idempotent_on_id(snapshot, scores, holdings):
    """The date-based uniqueness must not make re-running the identical
    Friday snapshot mint a *new* ID each time -- that would break
    `create_brief()`/`ResearchBrief.id`'s derivation from `target.id` for a
    brief that's already been published and claimed."""
    first_id = _find(generate_exposure_targets(snapshot, scores, holdings), sector="Energy", factor="momentum").id
    second_id = _find(generate_exposure_targets(snapshot, scores, holdings), sector="Energy", factor="momentum").id

    assert first_id == second_id


def test_zero_weight_size_monitor_does_not_generate_a_directional_v1_research_target(snapshot, holdings):
    v1_snapshot = Snapshot(
        snapshot.as_of,
        snapshot.securities.assign(
            market_cap=[100.0, 200.0, 300.0, 400.0, 500.0],
            free_cash_flow_ttm=[5.0, 10.0, 15.0, 20.0, 25.0],
            revenue_ttm=[100.0] * 5,
            cost_of_revenue_ttm=[40.0] * 5,
            total_assets=[50.0] * 5,
            momentum_12_1=[0.1, 0.2, 0.3, 0.4, 0.5],
        ),
        snapshot.macro,
    )
    scores = score_universe(v1_snapshot, v1_factor_registry())

    targets = generate_exposure_targets(v1_snapshot, scores, holdings)

    assert not any(target.dimension.factor == "size" for target in targets)


def test_a_zero_weight_monitor_column_does_not_stop_later_factor_columns_from_generating_targets(snapshot, holdings):
    """The zero-weight skip in `generate_exposure_targets`'s per-factor loop
    must not depend on the zero-weight factor being registered last.
    `v1_factor_registry()` happens to register `size` (weight 0.0) after
    every real factor, which would hide a `continue`-turned-`break` bug
    here -- so this builds a `FactorScoreMatrix` with the zero-weight
    column deliberately placed *first*."""
    registry = FactorRegistry()
    registry.register(STUB_MOMENTUM)
    scores = score_universe(snapshot, registry)
    reordered_scores = scores.__class__(
        as_of=scores.as_of,
        scores=scores.scores.assign(zero_weight_monitor=scores.scores["momentum"])[["zero_weight_monitor", "momentum"]],
        weights={"zero_weight_monitor": 0.0, "momentum": 1.0},
    )

    targets = generate_exposure_targets(snapshot, reordered_scores, holdings)

    assert not any(t.dimension.factor == "zero_weight_monitor" for t in targets)
    assert any(t.dimension.factor == "momentum" for t in targets)
