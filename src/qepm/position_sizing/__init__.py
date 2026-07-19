"""Confidence-aware, advisory SIC position-size recommendations."""

from __future__ import annotations

from math import isfinite

from qepm.contracts import SizingRecommendation

__all__ = ["recommend_position_size"]


def recommend_position_size(
    *,
    confidence: float,
    requested_weight: float = 0.03,
    engine_recommended: bool = False,
    student_reassessment: bool = False,
    fresh_fit_check: bool = False,
    pm_approved: bool = False,
) -> SizingRecommendation:
    """Apply V1 confidence bands while leaving the Eboard free to decline a pitch."""
    if not isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    if not isfinite(requested_weight) or requested_weight <= 0:
        raise ValueError("requested_weight must be finite and positive")

    requires_discussion = confidence < 0.45
    confidence_cap = 0.05 if confidence >= 0.70 else 0.03 if confidence >= 0.45 else 0.01
    # AGENTS.md's above-5% gate: "an engine recommendation, a new student
    # pitch/reassessment, a fresh binding risk check, and PM approval."
    has_above_five_path = all((engine_recommended, student_reassessment, fresh_fit_check, pm_approved))
    requested_above_five = requested_weight > 0.05
    maximum_weight = requested_weight if requested_above_five and has_above_five_path else confidence_cap
    recommended_weight = min(requested_weight, maximum_weight)
    return SizingRecommendation(
        confidence=confidence,
        recommended_weight=recommended_weight,
        maximum_weight=maximum_weight,
        requires_board_discussion=requires_discussion,
        requires_above_five_percent_path=requested_above_five and not has_above_five_path,
    )
