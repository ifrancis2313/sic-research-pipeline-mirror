"""Public SIC Portfolio Fit Check interface.

This is a same-snapshot, pre-trade control. The older ``backtest_gate``
module remains as a compatibility layer for the original walking skeleton;
it is not presented as a historical validation result in V1 workflows.
"""

from qepm.backtest_gate import evaluate_portfolio_fit

__all__ = ["evaluate_portfolio_fit"]
