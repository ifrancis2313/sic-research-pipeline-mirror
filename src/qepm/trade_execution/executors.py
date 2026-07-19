"""Execution implementation details.

``Executor`` exists only to support the simulated walking-skeleton demo and
its test doubles.  It is not an extension point for live brokerage execution:
SIC policy requires every real order to be handed to the faculty advisor.
The advisor formatter is intentionally private, so the governed proposed-trade
entry point owns its use rather than exposing a convenient raw-order handoff.
Python privacy is a convention, not a security boundary; access controls and
advisor workflow remain operational controls.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from qepm.contracts import ExecutionResult, TradeOrder

__all__ = ["Executor"]


class Executor(ABC):
    @abstractmethod
    def execute(self, order: TradeOrder) -> ExecutionResult: ...


class _AdvisorPassthroughExecutor(Executor):
    """Formats the order for the policy-required SIC faculty-advisor handoff."""

    def execute(self, order: TradeOrder) -> ExecutionResult:
        note = (
            f"Hand off to faculty advisor: {order.direction.value.upper()} "
            f"${order.dollar_amount:,.0f} of {order.figi} "
            f"(pitch {order.pitch_id}, brief {order.brief_id}, target {order.target_id})."
        )
        return ExecutionResult(
            order=order,
            status="sent_to_advisor",
            backend="AdvisorPassthroughExecutor",
            confirmation_note=note,
        )
