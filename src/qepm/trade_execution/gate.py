"""Backtest -> Execution phase gate: a trade may only execute against a passed BacktestResult."""

from __future__ import annotations

from qepm.contracts import BacktestResult, PhaseGateError, TradeOrder


def validate_backtest_passed(order: TradeOrder, backtest_result: BacktestResult) -> None:
    if backtest_result.pitch_id != order.pitch_id:
        raise PhaseGateError(
            f"BacktestResult is for pitch {backtest_result.pitch_id!r}, "
            f"not the order's pitch {order.pitch_id!r}"
        )

    if not backtest_result.passed:
        raise PhaseGateError(
            f"BacktestResult for pitch {order.pitch_id} did not pass - cannot execute"
        )
