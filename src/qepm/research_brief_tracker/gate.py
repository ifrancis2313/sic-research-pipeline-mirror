"""Optimizer -> Brief phase gate: validates an ExposureTarget before it's packaged."""

from __future__ import annotations

from qepm.contracts import CompetingPitch, Direction, ExposureTarget, PhaseGateError, ResearchBrief
from qepm.portfolio_state import validate_exposure_target


def validate_target_for_brief(target: ExposureTarget) -> None:
    validate_exposure_target(target)

    if not any([target.dimension.sector, target.dimension.factor, target.dimension.screen]):
        raise PhaseGateError(
            f"ExposureTarget {target.id} has an empty dimension - no sector/factor/screen to scope a brief to"
        )

    if target.direction is Direction.SELL and not target.source_bucket:
        raise PhaseGateError(
            f"Sell-side ExposureTarget {target.id} is missing its source_bucket of current holdings"
        )


def validate_brief_open_for_pitch(brief: ResearchBrief) -> None:
    if brief.status not in {"open", "in-progress"}:
        raise PhaseGateError(f"ResearchBrief {brief.id} is not open for pitches (status={brief.status})")


def validate_pitch_for_brief(brief: ResearchBrief, pitch: CompetingPitch) -> None:
    if pitch.brief_id != brief.id:
        raise PhaseGateError(f"CompetingPitch {pitch.id} does not belong to ResearchBrief {brief.id}")


def validate_brief_has_pitches(brief: ResearchBrief) -> None:
    if not brief.pitches:
        raise PhaseGateError(f"ResearchBrief {brief.id} has no submitted pitches to score")
