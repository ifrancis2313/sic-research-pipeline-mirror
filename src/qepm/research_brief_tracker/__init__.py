"""Research Brief & Pitch Tracker (Phase 3b).

Converts each ExposureTarget into a ResearchBrief automatically. Pod
assignment is a manual PM decision recorded here, not automated. Accepts
CompetingPitch submissions from one or more pods and qualifies them as
ready or revise. The Eboard chooses between ready pitches using the
students' fundamental work; the system does not select a winner.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from qepm.contracts import (
    CompetingPitch,
    ExposureTarget,
    PitchReadiness,
    ResearchBrief,
)
from qepm.research_brief_tracker.gate import (
    validate_brief_has_pitches,
    validate_brief_open_for_pitch,
    validate_pitch_for_brief,
    validate_target_for_brief,
)

__all__ = ["create_brief", "assign_pod", "submit_pitch", "score_pitches"]


def create_brief(target: ExposureTarget, *, sleeve: str | None = None) -> ResearchBrief:
    """Package a target while allowing the PM to explicitly assign its sleeve.

    Optimizer-generated targets default to ``active``. A PM may publish a
    core transition or experimental-research brief by supplying that sleeve;
    the immutable target retained by the brief then drives the later fit gate.
    """
    validate_target_for_brief(target)
    if sleeve is not None:
        if sleeve not in {"core", "active", "experimental"}:
            raise ValueError(f"unsupported SIC sleeve: {sleeve!r}")
        target = replace(target, sleeve=sleeve)

    verb = "Find a buy candidate" if target.direction.value == "buy" else "Pick a holding to trim"
    dims = [
        f"{label}={value}"
        for label, value in (
            ("sector", target.dimension.sector),
            ("factor", target.dimension.factor),
            ("screen", target.dimension.screen),
        )
        if value
    ]

    prompt = (
        f"{verb} worth ${target.dollar_amount:,.0f} scoped to {', '.join(dims)}. "
        f"Rationale: {target.rationale}"
    )
    if target.direction.value == "sell":
        prompt += f" Candidate holdings to consider trimming: {', '.join(target.source_bucket)}."

    return ResearchBrief(id=f"RB-{target.id}", target=target, prompt=prompt)


def assign_pod(brief: ResearchBrief, pod: str, *, claimed_on: date) -> None:
    """Record a PM pod assignment and start the brief's explicit lifecycle clock."""
    if pod not in brief.assigned_pods and len(brief.assigned_pods) >= brief.pod_capacity:
        raise ValueError(f"ResearchBrief {brief.id} has reached its pod capacity ({brief.pod_capacity})")
    if pod not in brief.assigned_pods:
        brief.assigned_pods.append(pod)
        if brief.claimed_on is None:
            brief.claimed_on = claimed_on


def submit_pitch(brief: ResearchBrief, pitch: CompetingPitch, *, submitted_on: date) -> CompetingPitch:
    """Record a pitch and its explicit meaningful-update date."""
    validate_brief_open_for_pitch(brief)
    validate_pitch_for_brief(brief, pitch)
    brief.pitches.append(pitch)
    brief.last_meaningful_update = submitted_on
    return pitch


def score_pitches(brief: ResearchBrief) -> PitchReadiness:
    """Classify artifact completeness without judging thesis substance or selecting a winner.

    V1 deliberately checks that required fields are present, not whether their
    narrative or valuation work is persuasive. That investment judgment stays
    with the E-board's human review.
    """
    validate_brief_has_pitches(brief)
    required_fields = {
        "thesis": "thesis / variant view",
        "variant_view": "variant view",
        "dcf_sensitivity": "DCF with sensitivities",
        "cca_peers": "CCA and defensible peers",
        "catalysts_timeline": "catalysts and timeline",
        "risks_disconfirming_evidence": "risks and disconfirming evidence",
    }
    ready: list[CompetingPitch] = []
    revise: dict[str, tuple[str, ...]] = {}
    for pitch in brief.pitches:
        missing = [label for field, label in required_fields.items() if not getattr(pitch, field).strip()]
        if not pitch.fit_card_attached:
            missing.append("Portfolio Fit Check card")
        if missing:
            revise[pitch.id] = tuple(missing)
        else:
            ready.append(pitch)
    return PitchReadiness(brief_id=brief.id, ready=tuple(ready), revise=revise)
