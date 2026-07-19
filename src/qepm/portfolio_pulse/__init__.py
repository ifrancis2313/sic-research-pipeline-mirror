"""Separate weekly portfolio-pulse views for students and the executive board."""

from __future__ import annotations

from qepm.contracts import EboardPulse, Holdings, ProposedTrade, ResearchNeed, StudentPulse

__all__ = ["student_pulse", "eboard_pulse"]


def student_pulse(
    needs: tuple[ResearchNeed, ...], beta_status: str, brief_statuses: dict[str, str], sleeves: dict[str, float] | None = None,
    sleeve_statuses: dict[str, str] | None = None,
) -> StudentPulse:
    """Return non-sensitive weekly work and guardrail context for student pods."""
    return StudentPulse(beta_status, needs, brief_statuses, sleeves or {}, sleeve_statuses or {})


def eboard_pulse(
    holdings: Holdings, needs: tuple[ResearchNeed, ...], beta_status: str, proposed_trades: tuple[ProposedTrade, ...],
    brief_statuses: dict[str, str], sleeves: dict[str, float] | None = None, sleeve_statuses: dict[str, str] | None = None,
) -> EboardPulse:
    """Return the board view, including positions and advisor-queue detail."""
    student = student_pulse(needs, beta_status, brief_statuses, sleeves, sleeve_statuses)
    return EboardPulse(
        student.beta_status, student.research_needs, student.brief_statuses, student.sleeves,
        student.sleeve_statuses, holdings.positions.copy(), proposed_trades,
    )
