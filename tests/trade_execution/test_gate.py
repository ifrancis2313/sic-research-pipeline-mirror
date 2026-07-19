import pytest

from qepm.contracts import BacktestResult, Direction, PhaseGateError, TradeOrder
from qepm.trade_execution import execute_walking_skeleton_demo

ORDER = TradeOrder(
    figi="BBG-FIXTURE-007",
    direction=Direction.BUY,
    dollar_amount=21_882.35,
    pitch_id="CP-1",
    brief_id="RB-ET-BUY-ENERGY",
    target_id="ET-BUY-ENERGY",
)


def test_rejects_execution_of_a_failed_backtest():
    failed = BacktestResult(
        pitch_id="CP-1",
        brief_id="RB-ET-BUY-ENERGY",
        target_id="ET-BUY-ENERGY",
        passed=False,
        factor_fit={"momentum": -0.04},
        estimated_impact={"dollar_impact": 21_882.35},
        notes="factor mismatch",
    )

    with pytest.raises(PhaseGateError, match="did not pass"):
        execute_walking_skeleton_demo(ORDER, failed)


def test_rejects_backtest_result_for_a_different_pitch():
    mismatched = BacktestResult(
        pitch_id="CP-999",
        brief_id="RB-ET-BUY-ENERGY",
        target_id="ET-BUY-ENERGY",
        passed=True,
        factor_fit={"momentum": 0.11},
        estimated_impact={"dollar_impact": 21_882.35},
    )

    with pytest.raises(PhaseGateError, match="not the order's pitch"):
        execute_walking_skeleton_demo(ORDER, mismatched)
