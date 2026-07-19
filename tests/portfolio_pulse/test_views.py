from datetime import date

import pandas as pd

from qepm.contracts import Direction, Holdings, ResearchNeed
from qepm.portfolio_pulse import eboard_pulse, student_pulse


def test_student_pulse_excludes_position_level_holdings_but_eboard_pulse_includes_them():
    needs = (ResearchNeed("quality", Direction.BUY, 30, 55, "priority", "need quality"),)
    holdings = Holdings(date(2026, 7, 17), pd.DataFrame({"dollar_value": [10_000]}, index=["FIGI"]))

    student = student_pulse(needs, "green", {"RB-1": "open"}, {"core": 0.6})
    board = eboard_pulse(holdings, needs, "green", (), {"RB-1": "open"}, {"core": 0.6})

    assert student.sleeves == {"core": 0.6}
    assert board.brief_statuses == {"RB-1": "open"}
    assert board.holdings.loc["FIGI", "dollar_value"] == 10_000
