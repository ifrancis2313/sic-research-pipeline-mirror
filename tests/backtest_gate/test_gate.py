from datetime import timedelta

import pytest

from qepm.backtest_gate import evaluate_pitch
from qepm.contracts import (
    CompetingPitch,
    DimensionSpec,
    Direction,
    ExposureTarget,
    FactorScoreMatrix,
    Holdings,
    PhaseGateError,
    Snapshot,
)
from qepm.research_brief_tracker import create_brief

TARGET = ExposureTarget(
    id="ET-BUY-ENERGY",
    direction=Direction.BUY,
    dollar_amount=21_882.35,
    dimension=DimensionSpec(sector="Energy", factor="momentum"),
    rationale="Energy is underexposed on momentum.",
)


def test_rejects_pitch_referencing_the_wrong_brief(as_of, snapshot, holdings, scores):
    brief = create_brief(TARGET)
    pitch = CompetingPitch(id="CP-1", brief_id="RB-SOME-OTHER-BRIEF", pod="Pod A", figi="BBG-FIXTURE-007", thesis="wrong brief")

    with pytest.raises(PhaseGateError, match="not the given brief"):
        evaluate_pitch(pitch, TARGET, brief, holdings, scores, snapshot, as_of)


def test_rejects_pitch_for_a_security_with_no_factor_score(as_of, snapshot, holdings, scores):
    brief = create_brief(TARGET)
    pitch = CompetingPitch(id="CP-2", brief_id=brief.id, pod="Pod A", figi="NOT-A-REAL-FIGI", thesis="unscored security")

    with pytest.raises(PhaseGateError, match="no factor score"):
        evaluate_pitch(pitch, TARGET, brief, holdings, scores, snapshot, as_of)


def test_rejects_a_backtest_whose_scores_are_dated_after_the_evaluation_date(as_of, snapshot, holdings, scores):
    brief = create_brief(TARGET)
    pitch = CompetingPitch(id="CP-3", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-007", thesis="t")
    future_scores = FactorScoreMatrix(as_of=as_of + timedelta(days=7), scores=scores.scores)

    with pytest.raises(PhaseGateError, match="leakage"):
        evaluate_pitch(pitch, TARGET, brief, holdings, future_scores, snapshot, as_of)


def test_rejects_a_backtest_whose_snapshot_is_dated_after_the_evaluation_date(as_of, snapshot, holdings, scores):
    brief = create_brief(TARGET)
    pitch = CompetingPitch(id="CP-4", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-007", thesis="t")
    future_snapshot = Snapshot(as_of=as_of + timedelta(days=7), securities=snapshot.securities, macro=snapshot.macro)

    with pytest.raises(PhaseGateError, match="leakage"):
        evaluate_pitch(pitch, TARGET, brief, holdings, scores, future_snapshot, as_of)


def test_rejects_a_backtest_whose_holdings_are_dated_after_the_evaluation_date(as_of, snapshot, holdings, scores):
    brief = create_brief(TARGET)
    pitch = CompetingPitch(id="CP-5", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-007", thesis="t")
    future_holdings = Holdings(as_of=as_of + timedelta(days=7), positions=holdings.positions)

    with pytest.raises(PhaseGateError, match="leakage"):
        evaluate_pitch(pitch, TARGET, brief, future_holdings, scores, snapshot, as_of)
