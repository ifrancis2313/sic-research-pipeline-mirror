"""Exposure Optimizer (Phase 3a).

Consumes the factor score matrix, current holdings, and (currently open,
per PRD Out of Scope) risk constraints, and emits ExposureTargets - a
dollar amount against a sector/factor/screen dimension, buy or sell.

Note: the PRD's stated interface is generate_exposure_targets(scores,
holdings, constraints); this implementation also takes the Snapshot
directly, since sector attribution (needed for both a target's
dimension and the sell-side source bucket) lives on the per-security
panel, not the score matrix. Revisit if a real constraint model
wants this passed differently.

Three independent rules produce the full breadth of targets in one run:
- per-factor sector gaps (dimension: sector + factor) - one pass per
  adopted factor in the score matrix, so adding a factor to the
  registry automatically widens this without code changes.
- a combined blend across every adopted factor, weighted by each
  factor's FactorRegistry weight (dimension: sector alone) - a real
  signal (a multifactor optimizer's blended sector view), not just a
  demo of DimensionSpec's shape.
- a screen-based rule (dimension: sector + screen) - how much of a
  sector's current holding actually passes a named screen predicate,
  vs. how much of the universe in that sector does.

Real risk/exposure constraints (position caps, sector bands, tracking
error) remain out of scope per the PRD; `constraints` stays a plain,
optional dict so passing {} or None is always valid.
"""

from __future__ import annotations

from datetime import date
from math import isfinite
from numbers import Real

import pandas as pd

from qepm.contracts import (
    DimensionSpec,
    Direction,
    ExposureTarget,
    FactorScoreMatrix,
    Holdings,
    PhaseGateError,
    ScreenPredicate,
    Snapshot,
)
from qepm.exposure_optimizer.gate import validate_inputs_for_optimization
from qepm.scoring import combined_factor_score

__all__ = [
    "generate_exposure_targets",
    "DEFAULT_PORTFOLIO_NAV",
    "DEFAULT_MIN_DOLLAR_SIZE",
    "DEFAULT_SCREEN_FIELD",
]

DEFAULT_PORTFOLIO_NAV = 100_000.0  # SIC's fund size (CONTEXT.md); overridable via constraints
DEFAULT_MIN_DOLLAR_SIZE = 500.0  # gaps smaller than this aren't worth a brief; overridable
DEFAULT_SCREEN_FIELD = "fcf_yield"  # illustrative screen (CONTEXT.md's own example); overridable


def generate_exposure_targets(
    snapshot: Snapshot,
    scores: FactorScoreMatrix,
    holdings: Holdings,
    constraints: dict | None = None,
) -> list[ExposureTarget]:
    validate_inputs_for_optimization(snapshot, scores, holdings)
    constraints = constraints or {}
    portfolio_nav = float(constraints.get("portfolio_nav", DEFAULT_PORTFOLIO_NAV))
    min_dollar_size = float(constraints.get("min_dollar_size", DEFAULT_MIN_DOLLAR_SIZE))
    screen_field = constraints.get("screen_field", DEFAULT_SCREEN_FIELD)
    if not isinstance(portfolio_nav, Real) or isinstance(portfolio_nav, bool) or not isfinite(portfolio_nav) or portfolio_nav <= 0:
        raise PhaseGateError("optimizer portfolio_nav must be finite and positive")
    if (
        not isinstance(min_dollar_size, Real)
        or isinstance(min_dollar_size, bool)
        or not isfinite(min_dollar_size)
        or min_dollar_size <= 0
    ):
        raise PhaseGateError("optimizer min_dollar_size must be finite and positive")
    if not isinstance(screen_field, str) or not screen_field.strip():
        raise PhaseGateError("optimizer screen_field must be a non-empty string")

    panel = pd.DataFrame({"sector": snapshot.securities["sector"]})
    panel["dollar_value"] = holdings.positions["dollar_value"].reindex(panel.index).fillna(0.0)

    targets: list[ExposureTarget] = []

    for factor_name in scores.scores.columns:
        if scores.weights.get(factor_name, 1.0) <= 0:
            continue  # monitor-only factors (e.g. V1 Size) do not create directional research briefs
        targets += _sector_score_targets(
            panel,
            scores.scores[factor_name],
            factor_label=factor_name,
            portfolio_nav=portfolio_nav,
            min_dollar_size=min_dollar_size,
            as_of=snapshot.as_of,
        )

    combined_score = combined_factor_score(scores)
    targets += _sector_score_targets(
        panel,
        combined_score,
        factor_label=None,
        portfolio_nav=portfolio_nav,
        min_dollar_size=min_dollar_size,
        as_of=snapshot.as_of,
    )

    if screen_field in snapshot.securities.columns:
        targets += _sector_screen_targets(
            panel,
            snapshot.securities[screen_field],
            screen_field=screen_field,
            portfolio_nav=portfolio_nav,
            min_dollar_size=min_dollar_size,
            as_of=snapshot.as_of,
        )

    return targets


def _slug(sector: str) -> str:
    return sector.upper().replace(" ", "_")


def _held_figis_in_sector(panel: pd.DataFrame, sector: str) -> tuple[str, ...]:
    mask = (panel["sector"] == sector) & (panel["dollar_value"] > 0)
    return tuple(panel.index[mask])


def _sector_score_targets(
    panel: pd.DataFrame,
    score: pd.Series,
    factor_label: str | None,
    portfolio_nav: float,
    min_dollar_size: float,
    as_of: date,
) -> list[ExposureTarget]:
    working = panel.copy()
    working["score"] = score.reindex(working.index)

    by_sector = working.groupby("sector").agg(score=("score", "mean"), dollar_value=("dollar_value", "sum"))
    by_sector["current_weight"] = by_sector["dollar_value"] / portfolio_nav

    shifted = by_sector["score"] - by_sector["score"].min() + 0.01
    by_sector["target_weight"] = shifted / shifted.sum()
    by_sector["gap"] = by_sector["target_weight"] - by_sector["current_weight"]

    label_suffix = factor_label.upper() if factor_label else "COMBINED"
    factor_desc = factor_label if factor_label else "combined multi-factor"

    targets: list[ExposureTarget] = []
    for sector, row in by_sector.iterrows():
        if pd.isna(row["score"]):
            # Every security in this sector is missing a score for this
            # factor (e.g. a coverage gap in the vendor feed) - by_sector's
            # groupby("score").mean() is NaN, and NaN propagates through
            # shifted/target_weight/gap. abs(NaN) < min_dollar_size is False
            # (NaN comparisons are never True), so without this check a NaN
            # dollar_amount would fall through into a target. Skip rather
            # than emit a target with no real gap to act on.
            continue

        dollar_amount = row["gap"] * portfolio_nav
        if abs(dollar_amount) < min_dollar_size:
            continue

        direction = Direction.BUY if dollar_amount > 0 else Direction.SELL
        verb = "underexposed" if direction is Direction.BUY else "overexposed"
        rationale = (
            f"{sector} is {verb} relative to its {factor_desc} score: "
            f"target weight {row['target_weight']:.1%} vs current weight {row['current_weight']:.1%}."
        )

        targets.append(
            ExposureTarget(
                id=f"ET-{direction.value.upper()}-{_slug(sector)}-{label_suffix}-{as_of.isoformat()}",
                direction=direction,
                dollar_amount=round(float(abs(dollar_amount)), 2),
                dimension=DimensionSpec(sector=sector, factor=factor_label),
                rationale=rationale,
                source_bucket=_held_figis_in_sector(working, sector) if direction is Direction.SELL else (),
                sleeve="active",
            )
        )
    return targets


def _sector_screen_targets(
    panel: pd.DataFrame,
    screen_values: pd.Series,
    screen_field: str,
    portfolio_nav: float,
    min_dollar_size: float,
    as_of: date,
) -> list[ExposureTarget]:
    working = panel.copy()
    working["screen_value"] = screen_values.reindex(working.index)
    threshold = working["screen_value"].median()
    working["passes"] = working["screen_value"] > threshold
    working["qualifying_dollar"] = working["dollar_value"].where(working["passes"], 0.0)

    by_sector = working.groupby("sector").agg(
        n_passing=("passes", "sum"), qualifying_dollar=("qualifying_dollar", "sum")
    )
    total_passing = by_sector["n_passing"].sum()
    if total_passing == 0:
        return []

    by_sector["target_weight"] = by_sector["n_passing"] / total_passing
    by_sector["current_weight"] = by_sector["qualifying_dollar"] / portfolio_nav
    by_sector["gap"] = by_sector["target_weight"] - by_sector["current_weight"]

    targets: list[ExposureTarget] = []
    for sector, row in by_sector.iterrows():
        if row["n_passing"] == 0:
            continue  # nothing in this sector passes the screen - not a buy candidate for it

        dollar_amount = row["gap"] * portfolio_nav
        if dollar_amount < min_dollar_size:
            continue  # screen rule is buy-side only: "add more of the qualifying names"

        rationale = (
            f"{sector} is underexposed among securities passing the {screen_field} screen "
            f"({screen_field} > {threshold:.4f}): target weight {row['target_weight']:.1%} vs "
            f"current qualifying weight {row['current_weight']:.1%}."
        )
        targets.append(
            ExposureTarget(
                id=f"ET-BUY-{_slug(sector)}-SCREEN-{as_of.isoformat()}",
                direction=Direction.BUY,
                dollar_amount=round(float(dollar_amount), 2),
                dimension=DimensionSpec(
                    sector=sector,
                    screen=f"{screen_field} > {threshold:.4f}",
                    screen_predicate=ScreenPredicate(field=screen_field, op=">", threshold=float(threshold)),
                ),
                rationale=rationale,
                sleeve="active",
            )
        )
    return targets
