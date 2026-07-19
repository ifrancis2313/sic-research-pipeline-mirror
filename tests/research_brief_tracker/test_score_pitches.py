from datetime import date

import pytest

from qepm.contracts import CompetingPitch, PhaseGateError
from qepm.exposure_optimizer import generate_exposure_targets
from qepm.research_brief_tracker import assign_pod, create_brief, score_pitches, submit_pitch


def _energy_momentum_target(snapshot, scores, holdings):
    targets = generate_exposure_targets(snapshot, scores, holdings)
    return next(t for t in targets if t.dimension.sector == "Energy" and t.dimension.factor == "momentum")


def test_multiple_pods_can_submit_against_the_same_brief(snapshot, scores, holdings):
    target = _energy_momentum_target(snapshot, scores, holdings)
    brief = create_brief(target)
    brief.pod_capacity = 2
    assign_pod(brief, "Pod A", claimed_on=date(2026, 7, 17))
    assign_pod(brief, "Pod B", claimed_on=date(2026, 7, 17))

    pitch_a = CompetingPitch(id="CP-A", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-007", thesis="Energy momentum pick")
    pitch_b = CompetingPitch(id="CP-B", brief_id=brief.id, pod="Pod B", figi="BBG-FIXTURE-009", thesis="Consumer staples alternative")
    submit_pitch(brief, pitch_a, submitted_on=snapshot.as_of)
    submit_pitch(brief, pitch_b, submitted_on=snapshot.as_of)

    assert {p.id for p in brief.pitches} == {"CP-A", "CP-B"}


def test_pitch_cannot_be_submitted_to_a_different_brief_than_it_names(snapshot, scores, holdings):
    target = _energy_momentum_target(snapshot, scores, holdings)
    brief = create_brief(target)
    wrong_brief_pitch = CompetingPitch(
        id="CP-WRONG", brief_id="RB-SOMETHING-ELSE", pod="Pod A", figi="BBG-FIXTURE-007", thesis="t"
    )

    with pytest.raises(PhaseGateError, match="does not belong"):
        submit_pitch(brief, wrong_brief_pitch, submitted_on=snapshot.as_of)


def test_pitch_readiness_requires_the_fundamental_artifacts(snapshot, scores, holdings):
    target = _energy_momentum_target(snapshot, scores, holdings)
    brief = create_brief(target)
    submit_pitch(brief, CompetingPitch(id="CP-A", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-007", thesis="t"), submitted_on=snapshot.as_of)
    submit_pitch(brief, CompetingPitch(id="CP-B", brief_id=brief.id, pod="Pod B", figi="BBG-FIXTURE-009", thesis="t"), submitted_on=snapshot.as_of)

    readiness = score_pitches(brief)

    assert readiness.ready == ()
    assert "DCF with sensitivities" in readiness.revise["CP-A"]
    assert "Portfolio Fit Check card" in readiness.revise["CP-B"]


def test_complete_pitch_is_ready_without_a_model_rank(snapshot, scores, holdings):
    target = _energy_momentum_target(snapshot, scores, holdings)
    brief = create_brief(target)
    complete_pitch = CompetingPitch(
        id="CP-A", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-007", thesis="t",
        variant_view="v", dcf_sensitivity="d", cca_peers="c", catalysts_timeline="c",
        risks_disconfirming_evidence="r", fit_card_attached=True,
    )
    submit_pitch(brief, complete_pitch, submitted_on=snapshot.as_of)
    submit_pitch(brief, CompetingPitch(id="CP-B", brief_id=brief.id, pod="Pod B", figi="BBG-FIXTURE-009", thesis="t"), submitted_on=snapshot.as_of)

    first = score_pitches(brief)
    second = score_pitches(brief)

    assert first.ready == (complete_pitch,)
    assert second == first


def test_readiness_does_not_select_a_winner_between_complete_pitches(snapshot, scores, holdings):
    target = _energy_momentum_target(snapshot, scores, holdings)
    brief = create_brief(target)
    fields = dict(variant_view="v", dcf_sensitivity="d", cca_peers="c", catalysts_timeline="c", risks_disconfirming_evidence="r", fit_card_attached=True)
    energy_pitch = CompetingPitch(id="CP-ENERGY", brief_id=brief.id, pod="Pod A", figi="BBG-FIXTURE-007", thesis="on-sector", **fields)
    offsector_pitch = CompetingPitch(id="CP-OFFSECTOR", brief_id=brief.id, pod="Pod B", figi="BBG-FIXTURE-005", thesis="off-sector", **fields)
    submit_pitch(brief, energy_pitch, submitted_on=snapshot.as_of)
    submit_pitch(brief, offsector_pitch, submitted_on=snapshot.as_of)

    readiness = score_pitches(brief)

    assert readiness.ready == (energy_pitch, offsector_pitch)
    assert readiness.revise == {}
