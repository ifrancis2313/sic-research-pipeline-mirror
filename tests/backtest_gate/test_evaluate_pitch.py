import numpy as np
import pytest

from qepm.backtest_gate import evaluate_pitch
from qepm.contracts import CompetingPitch, DimensionSpec, Direction, ExposureTarget, FactorScoreMatrix
from qepm.research_brief_tracker import create_brief

BUY_TARGET = ExposureTarget(
    id="ET-BUY-ENERGY",
    direction=Direction.BUY,
    dollar_amount=21_882.35,
    dimension=DimensionSpec(sector="Energy", factor="momentum"),
    rationale="Energy is underexposed on momentum.",
)

SELL_TARGET = ExposureTarget(
    id="ET-SELL-INDUSTRIALS",
    direction=Direction.SELL,
    dollar_amount=6_176.47,
    dimension=DimensionSpec(sector="Industrials", factor="momentum"),
    rationale="Industrials is overexposed on momentum.",
    source_bucket=("BBG-FIXTURE-005",),
)


def test_buy_pitch_matching_the_targets_rationale_passes(as_of, snapshot, holdings, scores):
    brief = create_brief(BUY_TARGET)
    pitch = CompetingPitch(id="CP-1", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-007", thesis="Energy momentum play")

    result = evaluate_pitch(pitch, BUY_TARGET, brief, holdings, scores, snapshot, as_of)

    assert result.passed is True
    assert result.factor_fit["momentum"] == pytest.approx(0.11)
    assert result.estimated_impact["dollar_impact"] == pytest.approx(21_882.35)
    assert brief.status == "approved"


def test_buy_pitch_that_is_dcf_cheap_but_factor_mismatched_fails(as_of, snapshot, holdings, scores):
    # Industrials-sector FIGI has negative momentum - a value pick that doesn't carry the tilt the target wants.
    brief = create_brief(BUY_TARGET)
    pitch = CompetingPitch(id="CP-2", brief_id=brief.id, pod="Pod B", figi="BBG-FIXTURE-005", thesis="Cheap on DCF")

    result = evaluate_pitch(pitch, BUY_TARGET, brief, holdings, scores, snapshot, as_of)

    assert result.passed is False
    assert "ranks" in result.notes
    # a failing result returns the brief to open status rather than terminating the flow
    assert brief.status == "open"


def test_sell_pitch_naming_a_holding_in_the_source_bucket_passes(as_of, snapshot, holdings, scores):
    brief = create_brief(SELL_TARGET)
    pitch = CompetingPitch(id="CP-3", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-005", thesis="Trim this one")

    result = evaluate_pitch(pitch, SELL_TARGET, brief, holdings, scores, snapshot, as_of)

    assert result.passed is True
    assert result.estimated_impact["dollar_impact"] == pytest.approx(-6_176.47)
    assert brief.status == "approved"


@pytest.mark.parametrize("target,figi", [(BUY_TARGET, "BBG-FIXTURE-007"), (SELL_TARGET, "BBG-FIXTURE-005")])
def test_missing_pitched_factor_score_is_na_not_a_failed_measurement(as_of, snapshot, holdings, scores, target, figi):
    brief = create_brief(target)
    pitch = CompetingPitch(id="CP-NO-FACTOR", brief_id=brief.id, pod="Pod A", figi=figi, thesis="t")
    missing = scores.scores.copy()
    missing.loc[figi, "momentum"] = np.nan

    result = evaluate_pitch(
        pitch, target, brief, holdings,
        FactorScoreMatrix(as_of=scores.as_of, scores=missing, weights=scores.weights), snapshot, as_of,
    )

    assert result.passed is True
    assert result.factor_fit == {"momentum": None}
    assert "unavailable" in result.notes


def test_sell_pitch_naming_a_holding_outside_the_source_bucket_fails(as_of, snapshot, holdings, scores):
    brief = create_brief(SELL_TARGET)
    pitch = CompetingPitch(id="CP-4", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-009", thesis="Trim this instead")

    result = evaluate_pitch(pitch, SELL_TARGET, brief, holdings, scores, snapshot, as_of)

    assert result.passed is False
    assert "not part of the overexposed bucket" in result.notes
    assert brief.status == "open"


def test_portfolio_impact_shows_before_and_after_sector_and_factor_exposure(as_of, snapshot, holdings, scores):
    brief = create_brief(BUY_TARGET)
    pitch = CompetingPitch(id="CP-5", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-007", thesis="t")

    result = evaluate_pitch(pitch, BUY_TARGET, brief, holdings, scores, snapshot, as_of)

    assert result.estimated_impact["sector_weight_after"] > result.estimated_impact["sector_weight_before"]
    assert result.estimated_impact["factor_exposure_after"] > result.estimated_impact["factor_exposure_before"]
    # Exact values, not just direction -- a "before > after" comparison alone
    # can't distinguish a sign/operator error (e.g. `/` mutated to `*`) from
    # correct math if the error happens to preserve the ordering by luck.
    assert result.estimated_impact["sector_weight_before"] == pytest.approx(0.09)
    assert result.estimated_impact["sector_weight_after"] == pytest.approx(0.3088235)
    assert result.estimated_impact["factor_exposure_before"] == pytest.approx(0.0567)
    assert result.estimated_impact["factor_exposure_after"] == pytest.approx(0.080770585)


def test_portfolio_nav_is_overridable_via_constraints_and_changes_the_impact_math(as_of, snapshot, holdings, scores):
    brief = create_brief(BUY_TARGET)
    pitch = CompetingPitch(id="CP-6", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-007", thesis="t")

    default_result = evaluate_pitch(pitch, BUY_TARGET, brief, holdings, scores, snapshot, as_of)
    scaled_result = evaluate_pitch(
        pitch, BUY_TARGET, brief, holdings, scores, snapshot, as_of, constraints={"portfolio_nav": 200_000.0}
    )

    # same holdings, bigger NAV denominator -> smaller sector weight before the trade
    assert scaled_result.estimated_impact["sector_weight_before"] < default_result.estimated_impact["sector_weight_before"]


def test_factor_fit_pass_threshold_is_overridable(as_of, snapshot, holdings, scores):
    brief = create_brief(BUY_TARGET)
    # BBG-FIXTURE-005 fails the default 5.0/10 threshold (see test above) - lowering the bar should flip it to pass
    pitch = CompetingPitch(id="CP-7", brief_id=brief.id, pod="Pod B", figi="BBG-FIXTURE-005", thesis="Cheap on DCF")

    lenient_result = evaluate_pitch(
        pitch, BUY_TARGET, brief, holdings, scores, snapshot, as_of, constraints={"factor_fit_pass_threshold": 0.0}
    )

    assert lenient_result.passed is True
    assert brief.status == "approved"
