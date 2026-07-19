"""Legacy Backtest Gate plus the V1 Portfolio Fit Check implementation.

``evaluate_pitch`` is retained for historical compatibility. V1 callers use
``qepm.portfolio_fit.evaluate_portfolio_fit``: a same-snapshot fit check, not
a historical backtest. The underlying implementation remains here while the
older issue-oriented module is kept stable.

The legacy path checks a winning pitch's own factor loadings against its Exposure
Target's rationale, plus estimated portfolio-level impact (sector,
factor, dollar). Catches the "DCF-cheap but factor-mismatched" case: a
stock can be a good value pick and still be a bad fit for the exposure
it's meant to fill.

Note: the PRD's stated interface is evaluate_pitch(pitch, target,
portfolio); this implementation also takes the brief (so a failing
result can return it to open status - see below), the Snapshot and
FactorScoreMatrix (needed for factor/sector lookups), an explicit
evaluation_date (so the leakage check has something concrete to check
every input's as_of stamp against), and an optional constraints dict
(portfolio_nav, factor_fit_pass_threshold) - the same
constraints-dict pattern the Exposure Optimizer already uses, so a
custom portfolio_nav passed to generate_exposure_targets can be passed
here too instead of silently reverting to the default.

Brief status: evaluate_pitch moves the brief through
open -> backtesting -> approved (pass) | open (fail) - a failing result
never leaves the brief stuck or terminates the pipeline; a different
pitch can still be scored and evaluated against the same brief.
"""

from __future__ import annotations

from datetime import date
from typing import cast

import pandas as pd

from qepm.backtest_gate.gate import validate_pitch_for_backtest, validate_pitch_for_portfolio_fit
from qepm.contracts import (
    BacktestResult,
    CompetingPitch,
    Direction,
    ExposureTarget,
    FactorScoreMatrix,
    Holdings,
    PortfolioFitResult,
    PortfolioPolicy,
    ResearchBrief,
    Snapshot,
    TradeOrder,
)
from qepm.exposure_optimizer import DEFAULT_PORTFOLIO_NAV
from qepm.portfolio_state import validate_portfolio_policy
from qepm.scoring import combined_factor_score, percentile_rank_score

__all__ = ["evaluate_pitch", "evaluate_portfolio_fit", "FACTOR_FIT_PASS_THRESHOLD"]

FACTOR_FIT_PASS_THRESHOLD = 5.0  # 0-10 percentile scale: at/above the universe median; overridable


def evaluate_pitch(
    pitch: CompetingPitch,
    target: ExposureTarget,
    brief: ResearchBrief,
    portfolio: Holdings,
    scores: FactorScoreMatrix,
    snapshot: Snapshot,
    evaluation_date: date,
    constraints: dict | None = None,
) -> BacktestResult:
    validate_pitch_for_backtest(pitch, target, brief, scores, snapshot, portfolio, evaluation_date)
    constraints = constraints or {}
    portfolio_nav = constraints.get("portfolio_nav", DEFAULT_PORTFOLIO_NAV)
    factor_fit_pass_threshold = constraints.get("factor_fit_pass_threshold", FACTOR_FIT_PASS_THRESHOLD)

    brief.status = "backtesting"

    factor_fit, factor_fit_passed, notes = _evaluate_factor_fit(pitch, target, scores, factor_fit_pass_threshold)
    estimated_impact = _estimate_portfolio_impact(pitch, target, portfolio, snapshot, scores, portfolio_nav)

    result = BacktestResult(
        pitch_id=pitch.id,
        brief_id=brief.id,
        target_id=target.id,
        passed=factor_fit_passed,
        factor_fit=factor_fit,
        estimated_impact=estimated_impact,
        notes="; ".join(notes) if notes else "OK",
    )

    brief.status = "approved" if factor_fit_passed else "open"
    return result


def evaluate_portfolio_fit(
    pitch: CompetingPitch,
    target: ExposureTarget,
    brief: ResearchBrief,
    portfolio: Holdings,
    scores: FactorScoreMatrix,
    snapshot: Snapshot,
    evaluation_date: date,
    policy: PortfolioPolicy,
) -> PortfolioFitResult:
    """Evaluate a proposed trade against factor fit and V1's binding limits."""
    validate_portfolio_policy(policy)
    validate_pitch_for_portfolio_fit(pitch, target, brief, scores, snapshot, portfolio, evaluation_date)
    brief.status = "backtesting"

    factor_fit, factor_fit_passed, notes = _evaluate_factor_fit_for_portfolio_fit(
        pitch, target, scores, FACTOR_FIT_PASS_THRESHOLD
    )
    estimated_impact = _estimate_portfolio_impact(
        pitch, target, portfolio, snapshot, scores, policy.portfolio_nav
    )
    violations, warnings, policy_impact = _evaluate_policy_limits(pitch, target, portfolio, snapshot, policy)
    estimated_impact.update(policy_impact)

    if any(value is None for value in factor_fit.values()):
        warnings.append("factor-data-unavailable")
    elif not factor_fit_passed:
        warnings.append("factor-fit-warning")
    passed = not violations
    brief.status = "approved" if passed else "open"
    notes.extend(violations)
    notes.extend(warnings)
    return PortfolioFitResult(
        pitch_id=pitch.id,
        brief_id=brief.id,
        target_id=target.id,
        as_of=evaluation_date,
        passed=passed,
        requires_exception=bool(violations),
        factor_fit=factor_fit,
        estimated_impact=estimated_impact,
        hard_limit_violations=tuple(violations),
        warnings=tuple(warnings),
        notes="; ".join(notes) if notes else "OK",
        order=TradeOrder(
            figi=pitch.figi,
            direction=target.direction,
            dollar_amount=target.dollar_amount,
            pitch_id=pitch.id,
            brief_id=brief.id,
            target_id=target.id,
        ),
    )


def _evaluate_factor_fit_for_portfolio_fit(
    pitch: CompetingPitch, target: ExposureTarget, scores: FactorScoreMatrix, factor_fit_pass_threshold: float
) -> tuple[dict[str, float | None], bool, list[str]]:
    """Return advisory factor evidence; missing/non-comparable scores remain visible as N/A."""
    factor_name = target.dimension.factor
    label = factor_name or "combined"
    if pitch.figi not in scores.scores.index:
        return {label: None}, True, [f"{label} score is unavailable for {pitch.figi}."]

    factor_fit, passed, notes = _evaluate_factor_fit(pitch, target, scores, factor_fit_pass_threshold)
    return cast(dict[str, float | None], factor_fit), passed, notes


def _evaluate_policy_limits(
    pitch: CompetingPitch,
    target: ExposureTarget,
    portfolio: Holdings,
    snapshot: Snapshot,
    policy: PortfolioPolicy,
) -> tuple[list[str], list[str], dict[str, float]]:
    violations: list[str] = []
    warnings: list[str] = []
    impact: dict[str, float] = {}
    security = snapshot.securities.loc[pitch.figi]

    liquidity = security.get(policy.liquidity_column)
    beta = security.get(policy.beta_column)
    price_history = security.get(policy.price_history_column)
    _evaluate_sleeve_eligibility(target, security, policy, violations)
    if price_history is None or pd.isna(price_history) or not bool(price_history):
        violations.append("missing-price-history")
    if liquidity is None or pd.isna(liquidity):
        violations.append("missing-liquidity-data")
    elif float(liquidity) < policy.min_median_daily_dollar_volume:
        violations.append("minimum-liquidity")
    elif target.dollar_amount > float(liquidity) * policy.max_trade_volume_fraction:
        violations.append("trade-participation-cap")

    positions = portfolio.positions["dollar_value"]
    current_position = float(positions.get(pitch.figi, 0.0))
    signed_amount = target.dollar_amount if target.direction is Direction.BUY else -target.dollar_amount
    position_after = current_position + signed_amount
    name_weight_before = current_position / policy.portfolio_nav
    impact["name_weight_after"] = position_after / policy.portfolio_nav
    if target.direction is Direction.SELL and position_after < 0:
        violations.append("sell-exceeds-held-position")
    cash_after = policy.portfolio_nav - float(positions.sum()) - signed_amount
    impact["cash_weight_after"] = cash_after / policy.portfolio_nav
    if impact["cash_weight_after"] > policy.normal_cash_maximum:
        warnings.append("cash-above-normal-operating-band")
    if impact["name_weight_after"] > policy.max_single_name_weight:
        if name_weight_before <= policy.max_single_name_weight or position_after > current_position:
            violations.append("single-name-cap")
        else:
            warnings.append("inherited-single-name-cap")

    if beta is None or pd.isna(beta):
        violations.append("missing-beta-data")
        return violations, warnings, impact

    beta_series = snapshot.securities.get(policy.beta_column, None)
    if beta_series is None or not positions.index.isin(beta_series.index).all() or beta_series.reindex(positions.index).isna().any():
        violations.append("missing-beta-data")
        return violations, warnings, impact

    portfolio_beta_before = float((positions / policy.portfolio_nav * beta_series.reindex(positions.index)).sum())
    portfolio_beta_after = portfolio_beta_before + signed_amount / policy.portfolio_nav * float(beta)
    impact["portfolio_beta_before"] = portfolio_beta_before
    impact["portfolio_beta_after"] = portfolio_beta_after
    if portfolio_beta_after > policy.beta_ceiling and (
        portfolio_beta_before <= policy.beta_ceiling or portfolio_beta_after > portfolio_beta_before
    ):
        violations.append("portfolio-beta-ceiling")
    elif portfolio_beta_after >= policy.beta_warning:
        warnings.append("portfolio-beta-warning")
    return violations, warnings, impact


def _evaluate_sleeve_eligibility(
    target: ExposureTarget, security, policy: PortfolioPolicy, violations: list[str]
) -> None:
    """Apply sleeve eligibility, defaulting legacy/unset targets to active.

    Normal optimizer targets explicitly declare ``active``.  The default
    keeps direct API callers safe: an omitted sleeve still receives the
    Russell-1000 gate rather than bypassing sleeve eligibility.
    """
    sleeve = target.sleeve or "active"
    if sleeve not in {"core", "active", "experimental"}:
        violations.append("invalid-sleeve")
        return
    if sleeve in {"core", "active"}:
        eligible = security.get(policy.russell_membership_column)
        core_etf = security.get(policy.core_market_etf_column) if sleeve == "core" else False
        eligible_is_missing = eligible is None or pd.isna(eligible)
        core_etf_is_true = core_etf is not None and not pd.isna(core_etf) and bool(core_etf)
        if eligible_is_missing and not core_etf_is_true:
            violations.append("missing-universe-eligibility")
        elif not bool(eligible) and not core_etf_is_true:
            violations.append("active-sleeve-universe-eligibility")
    if sleeve == "experimental":
        listed = security.get(policy.us_listing_column)
        instrument = security.get(policy.instrument_type_column)
        if listed is None or pd.isna(listed) or instrument is None or pd.isna(instrument):
            violations.append("missing-experimental-eligibility")
        elif not bool(listed) or str(instrument).lower() not in {"stock", "etf"}:
            violations.append("experimental-sleeve-eligibility")


def _evaluate_factor_fit(
    pitch: CompetingPitch, target: ExposureTarget, scores: FactorScoreMatrix, factor_fit_pass_threshold: float
) -> tuple[dict[str, float | None], bool, list[str]]:
    notes: list[str] = []

    if target.direction is Direction.SELL:
        passed = pitch.figi in target.source_bucket
        if not passed:
            notes.append(
                f"{pitch.figi} is not part of the overexposed bucket {target.source_bucket} "
                f"this sell target was scoped to."
            )
        factor_fit: dict[str, float | None] = {}
        if target.dimension.factor and target.dimension.factor in scores.scores.columns:
            score = scores.scores.loc[pitch.figi, target.dimension.factor]
            if pd.isna(score):
                factor_fit[target.dimension.factor] = None
                notes.append(f"{target.dimension.factor} score is unavailable for {pitch.figi}.")
            else:
                factor_fit[target.dimension.factor] = float(score)
        return factor_fit, passed, notes

    factor_name = target.dimension.factor
    if factor_name and factor_name in scores.scores.columns:
        series = scores.scores[factor_name]
        label = factor_name
    else:
        series = combined_factor_score(scores)
        label = "combined"

    score = series.loc[pitch.figi]
    if pd.isna(score):
        return {label: None}, True, [f"{label} score is unavailable for {pitch.figi}."]

    rank_score = percentile_rank_score(pitch.figi, series)
    passed = rank_score >= factor_fit_pass_threshold
    if not passed:
        notes.append(
            f"{pitch.figi} ranks {rank_score:.1f}/10 on {label}, below the "
            f"{factor_fit_pass_threshold}/10 threshold this {target.direction.value}-side target needs."
        )
    return {label: float(score)}, passed, notes


def _estimate_portfolio_impact(
    pitch: CompetingPitch,
    target: ExposureTarget,
    portfolio: Holdings,
    snapshot: Snapshot,
    scores: FactorScoreMatrix,
    portfolio_nav: float,
) -> dict[str, float]:
    signed_amount = target.dollar_amount if target.direction is Direction.BUY else -target.dollar_amount

    positions = portfolio.positions["dollar_value"].reindex(snapshot.securities.index).fillna(0.0)
    impact: dict[str, float] = {"dollar_impact": signed_amount}

    if target.dimension.sector:
        sector_mask = snapshot.securities["sector"] == target.dimension.sector
        current_sector_dollar = float(positions[sector_mask].sum())
        pick_sector = snapshot.securities.loc[pitch.figi, "sector"]
        sector_delta = signed_amount if pick_sector == target.dimension.sector else 0.0
        impact["sector_weight_before"] = current_sector_dollar / portfolio_nav
        impact["sector_weight_after"] = (current_sector_dollar + sector_delta) / portfolio_nav

    factor_name = target.dimension.factor
    factor_series = (
        scores.scores[factor_name] if factor_name and factor_name in scores.scores.columns else combined_factor_score(scores)
    )
    if pitch.figi in factor_series.index:
        weights = positions / portfolio_nav
        current_factor_exposure = float((weights * factor_series.reindex(positions.index)).sum())
        pick_score = float(factor_series.loc[pitch.figi])
        signed_weight = signed_amount / portfolio_nav
        impact["factor_exposure_before"] = current_factor_exposure
        impact["factor_exposure_after"] = current_factor_exposure + signed_weight * pick_score

    return impact
