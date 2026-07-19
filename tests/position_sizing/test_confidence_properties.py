"""Property-based tests for recommend_position_size's confidence-band and
above-5%-gate logic.

Example-based tests in test_confidence.py pin specific band boundaries;
these pin the invariants a real-money sizing function must never violate
for *any* valid input, regardless of which confidence band it lands in.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from qepm.position_sizing import recommend_position_size

_CONFIDENCE = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
_POSITIVE_WEIGHT = st.floats(min_value=1e-6, max_value=1.0, allow_nan=False, allow_infinity=False)
_FOUR_FLAGS = st.tuples(st.booleans(), st.booleans(), st.booleans(), st.booleans())


@given(confidence=_CONFIDENCE, requested_weight=_POSITIVE_WEIGHT, flags=_FOUR_FLAGS)
def test_recommended_weight_never_exceeds_the_requested_weight(confidence, requested_weight, flags):
    """The engine must never recommend more than what was actually
    requested -- this is the property that makes "recommendation" mean
    something other than "the engine invents a bigger number.\""""
    engine_recommended, student_reassessment, fresh_fit_check, pm_approved = flags

    recommendation = recommend_position_size(
        confidence=confidence,
        requested_weight=requested_weight,
        engine_recommended=engine_recommended,
        student_reassessment=student_reassessment,
        fresh_fit_check=fresh_fit_check,
        pm_approved=pm_approved,
    )

    assert recommendation.recommended_weight <= requested_weight


@given(confidence=_CONFIDENCE, requested_weight=_POSITIVE_WEIGHT, flags=_FOUR_FLAGS)
def test_recommended_weight_never_exceeds_its_own_maximum(confidence, requested_weight, flags):
    engine_recommended, student_reassessment, fresh_fit_check, pm_approved = flags

    recommendation = recommend_position_size(
        confidence=confidence,
        requested_weight=requested_weight,
        engine_recommended=engine_recommended,
        student_reassessment=student_reassessment,
        fresh_fit_check=fresh_fit_check,
        pm_approved=pm_approved,
    )

    assert recommendation.recommended_weight <= recommendation.maximum_weight


@given(
    requested_weight=st.floats(min_value=0.0501, max_value=1.0, allow_nan=False, allow_infinity=False),
    confidence=_CONFIDENCE,
)
def test_above_five_percent_is_never_reachable_with_fewer_than_all_four_flags(requested_weight, confidence):
    """Whichever three flags are on, the fourth missing one must still
    block the above-5% path -- a stronger, exhaustive version of the
    four hand-picked "exactly one flag" examples in test_confidence.py."""
    for missing_index in range(4):
        flags = [True, True, True, True]
        flags[missing_index] = False

        recommendation = recommend_position_size(
            confidence=confidence,
            requested_weight=requested_weight,
            engine_recommended=flags[0],
            student_reassessment=flags[1],
            fresh_fit_check=flags[2],
            pm_approved=flags[3],
        )

        assert recommendation.requires_above_five_percent_path is True
        assert recommendation.maximum_weight <= 0.05


@given(requested_weight=st.floats(min_value=0.0501, max_value=1.0, allow_nan=False, allow_infinity=False))
def test_all_four_flags_together_unlock_exactly_the_requested_weight(requested_weight):
    recommendation = recommend_position_size(
        confidence=0.90,
        requested_weight=requested_weight,
        engine_recommended=True,
        student_reassessment=True,
        fresh_fit_check=True,
        pm_approved=True,
    )

    assert recommendation.requires_above_five_percent_path is False
    assert recommendation.recommended_weight == requested_weight


@given(confidence=_CONFIDENCE)
def test_low_confidence_never_auto_vetoes_a_pitch(confidence):
    """Confidence is an advisory sizing input, never a hard block -- the
    function must always return a usable (positive) recommendation, no
    matter how low confidence is, matching the documented "never a pitch
    veto" design."""
    recommendation = recommend_position_size(confidence=confidence)

    assert recommendation.maximum_weight > 0.0
    assert recommendation.recommended_weight > 0.0
