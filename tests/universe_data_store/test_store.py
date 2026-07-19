from datetime import date

import pandas as pd
import pytest

from qepm.contracts import PhaseGateError
from qepm.universe_data_store.adapters.base import Adapter, AdapterOutput
from qepm.universe_data_store.store import DataStore


class _FixedPanelAdapter(Adapter):
    name = "fixed_panel"

    def __init__(self, rows: dict) -> None:
        self.rows = rows

    def load(self, source) -> AdapterOutput:
        panel = pd.DataFrame(self.rows).set_index(["figi", "date"])
        return AdapterOutput(panel=panel)


def test_backfill_seeds_the_store():
    adapter = _FixedPanelAdapter(
        {"figi": ["F1", "F2"], "date": [date(2026, 1, 2), date(2026, 1, 2)], "price": [10.0, 20.0]}
    )
    store = DataStore()

    store.backfill(adapter, source=None)

    assert len(store.panel) == 2
    assert store.panel.loc[("F1", date(2026, 1, 2)), "price"] == 10.0


def test_backfill_refuses_to_reseed_a_nonempty_store():
    store = DataStore()
    store.backfill(
        _FixedPanelAdapter({"figi": ["F1"], "date": [date(2026, 1, 2)], "price": [10.0]}), source=None
    )

    with pytest.raises(PhaseGateError, match="already contains history"):
        store.backfill(
            _FixedPanelAdapter({"figi": ["F2"], "date": [date(2026, 1, 3)], "price": [20.0]}), source=None
        )


def test_append_adds_new_rows_without_touching_existing_history():
    store = DataStore()
    store.backfill(
        _FixedPanelAdapter({"figi": ["F1"], "date": [date(2026, 1, 2)], "price": [10.0]}),
        source=None,
    )

    store.append(
        _FixedPanelAdapter({"figi": ["F1"], "date": [date(2026, 1, 3)], "price": [11.0]}),
        source=None,
    )

    assert len(store.panel) == 2
    assert store.panel.loc[("F1", date(2026, 1, 2)), "price"] == 10.0
    assert store.panel.loc[("F1", date(2026, 1, 3)), "price"] == 11.0


def test_append_merges_nonconflicting_populated_fields_for_existing_security_date():
    store = DataStore()
    store.backfill(
        _FixedPanelAdapter(
            {"figi": ["F1"], "date": [date(2026, 1, 2)], "price": [10.0], "sector": [None]}
        ),
        source=None,
    )

    store.append(
        _FixedPanelAdapter(
            {
                "figi": ["F1"],
                "date": [date(2026, 1, 2)],
                "price": [None],
                "sector": ["Technology"],
                "vendor_identifier": ["abc-123"],
            }
        ),
        source=None,
    )

    assert len(store.panel) == 1
    assert store.panel.loc[("F1", date(2026, 1, 2)), "price"] == 10.0
    assert store.panel.loc[("F1", date(2026, 1, 2)), "sector"] == "Technology"
    assert store.panel.loc[("F1", date(2026, 1, 2)), "vendor_identifier"] == "abc-123"


def test_append_rejects_conflicting_populated_historical_values():
    store = DataStore()
    store.backfill(
        _FixedPanelAdapter({"figi": ["F1"], "date": [date(2026, 1, 2)], "price": [10.0]}),
        source=None,
    )

    with pytest.raises(PhaseGateError, match="conflicting populated values"):
        store.append(
            _FixedPanelAdapter({"figi": ["F1"], "date": [date(2026, 1, 2)], "price": [10.5]}),
            source=None,
        )


def test_snapshot_carries_forward_latest_valid_fundamental_but_uses_current_market_data():
    store = DataStore()
    store.backfill(
        _FixedPanelAdapter(
            {
                "figi": ["F1", "F1"],
                "date": [date(2026, 7, 10), date(2026, 7, 17)],
                "price": [100.0, 110.0],
                "free_cash_flow_ttm": [500.0, float("nan")],
                "free_cash_flow_ttm_asof": [date(2026, 7, 10), pd.NaT],
            }
        ),
        source=None,
    )

    snapshot = store.snapshot(date(2026, 7, 17), fundamental_fields=("free_cash_flow_ttm",))

    assert snapshot.as_of == date(2026, 7, 17)
    assert snapshot.securities.loc["F1", "price"] == 110.0
    assert snapshot.securities.loc["F1", "free_cash_flow_ttm"] == 500.0
    assert snapshot.securities.loc["F1", "free_cash_flow_ttm_asof"] == date(2026, 7, 10)


def test_snapshot_ignores_historical_fundamentals_for_figis_missing_from_requested_market_panel():
    store = DataStore()
    store.backfill(
        _FixedPanelAdapter(
            {
                "figi": ["F1", "F2", "F1"],
                "date": [date(2026, 7, 10), date(2026, 7, 10), date(2026, 7, 17)],
                "price": [100.0, 200.0, 110.0],
                "free_cash_flow_ttm": [500.0, 600.0, float("nan")],
                "free_cash_flow_ttm_asof": [date(2026, 7, 10), date(2026, 7, 10), pd.NaT],
            }
        ),
        source=None,
    )

    snapshot = store.snapshot(date(2026, 7, 17), fundamental_fields=("free_cash_flow_ttm",))

    assert list(snapshot.securities.index) == ["F1"]
    assert snapshot.securities.loc["F1", "free_cash_flow_ttm"] == 500.0


def test_snapshot_refuses_to_carry_a_fundamental_without_an_availability_date():
    store = DataStore()
    store.backfill(
        _FixedPanelAdapter(
            {
                "figi": ["F1"],
                "date": [date(2026, 7, 17)],
                "free_cash_flow_ttm": [500.0],
            }
        ),
        source=None,
    )

    with pytest.raises(ValueError, match="free_cash_flow_ttm_asof"):
        store.snapshot(date(2026, 7, 17), fundamental_fields=("free_cash_flow_ttm",))
