import pytest

from qepm.position_sizing import recommend_position_size


@pytest.mark.parametrize(
    ("confidence", "expected_cap"),
    [(0.70, 0.05), (0.45, 0.03), (0.44, 0.01)],
)
def test_confidence_sets_an_advisory_recommendation_cap_not_a_pitch_veto(confidence, expected_cap):
    recommendation = recommend_position_size(confidence=confidence)

    assert recommendation.maximum_weight == expected_cap
    assert recommendation.recommended_weight == min(0.03, expected_cap)
    assert recommendation.requires_board_discussion is (confidence < 0.45)
    assert recommendation.pitch_remains_eligible is True


def test_above_five_percent_requires_the_documented_reassessment_path():
    recommendation = recommend_position_size(
        confidence=0.90,
        requested_weight=0.07,
        engine_recommended=True,
        student_reassessment=True,
        fresh_fit_check=True,
        pm_approved=True,
    )

    assert recommendation.recommended_weight == 0.07
    assert recommendation.requires_above_five_percent_path is False


@pytest.mark.parametrize("requested_weight", (float("nan"), float("inf"), float("-inf")))
def test_position_sizing_rejects_non_finite_requested_weight(requested_weight):
    with pytest.raises(ValueError, match="finite"):
        recommend_position_size(confidence=0.7, requested_weight=requested_weight)


@pytest.mark.parametrize(
    ("engine_recommended", "student_reassessment", "fresh_fit_check", "pm_approved"),
    [
        (False, False, False, False),
        (True, False, False, False),
        (False, True, False, False),
        (False, False, True, False),
        (False, False, False, True),
        (True, True, True, False),
    ],
)
def test_above_five_percent_path_requires_all_four_flags_not_any_one(
    engine_recommended, student_reassessment, fresh_fit_check, pm_approved
):
    recommendation = recommend_position_size(
        confidence=0.90,
        requested_weight=0.07,
        engine_recommended=engine_recommended,
        student_reassessment=student_reassessment,
        fresh_fit_check=fresh_fit_check,
        pm_approved=pm_approved,
    )

    assert recommendation.maximum_weight == 0.05
    assert recommendation.recommended_weight == 0.05
    assert recommendation.requires_above_five_percent_path is True
