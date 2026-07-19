from datetime import date

import pandas as pd
import pytest

from qepm.contracts import PhaseGateError
from qepm.universe_data_store.adapters.base import AdapterOutput
from qepm.universe_data_store.gate import validate_adapter_output
from qepm.universe_data_store.membership import MembershipWindow, PointInTimeMembership


def _panel(rows: dict) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    return df.set_index(["figi", "date"])


def test_rejects_a_panel_not_indexed_by_figi_and_date():
    bad_panel = pd.DataFrame({"figi": ["F1"], "date": [date(2026, 1, 2)], "price": [10.0]})

    with pytest.raises(PhaseGateError, match="figi"):
        validate_adapter_output(AdapterOutput(panel=bad_panel))


def test_rejects_a_lookahead_tainted_derived_field():
    panel = _panel(
        {
            "figi": ["F1", "F1"],
            "date": [date(2026, 1, 2), date(2026, 1, 3)],
            "rolling_mom": [0.05, 0.06],
            # second row's derived value claims to be computed using a future date
            "rolling_mom_asof": [date(2026, 1, 2), date(2026, 1, 10)],
        }
    )

    with pytest.raises(PhaseGateError, match="leakage"):
        validate_adapter_output(AdapterOutput(panel=panel))


def test_rejects_a_security_not_in_point_in_time_russell_membership():
    panel = _panel(
        {
            "figi": ["F1", "F2"],
            "date": [date(2026, 1, 2), date(2026, 1, 2)],
            "price": [10.0, 20.0],
        }
    )
    # F2 only joined the index later than this row's date
    membership = PointInTimeMembership(
        [
            MembershipWindow(figi="F1", start_date=date(2020, 1, 1)),
            MembershipWindow(figi="F2", start_date=date(2026, 6, 1)),
        ]
    )

    with pytest.raises(PhaseGateError, match="membership"):
        validate_adapter_output(AdapterOutput(panel=panel), membership=membership)


def test_accepts_a_security_that_is_a_point_in_time_member():
    panel = _panel(
        {
            "figi": ["F1"],
            "date": [date(2026, 1, 2)],
            "price": [10.0],
        }
    )
    membership = PointInTimeMembership([MembershipWindow(figi="F1", start_date=date(2020, 1, 1))])

    validate_adapter_output(AdapterOutput(panel=panel), membership=membership)  # raises on failure


def test_rejects_duplicate_security_date_rows_in_one_adapter_load():
    panel = _panel(
        {
            "figi": ["F1", "F1"],
            "date": [date(2026, 1, 2), date(2026, 1, 2)],
            "price": [10.0, 11.0],
        }
    )

    with pytest.raises(PhaseGateError, match="duplicate"):
        validate_adapter_output(AdapterOutput(panel=panel))


def test_rejects_duplicate_macro_dates_in_one_adapter_load():
    macro = pd.DataFrame(
        {"date": [date(2026, 1, 2), date(2026, 1, 2)], "risk_free_rate": [0.03, 0.04]}
    ).set_index("date")

    with pytest.raises(PhaseGateError, match="duplicate macro dates"):
        validate_adapter_output(AdapterOutput(macro=macro))
