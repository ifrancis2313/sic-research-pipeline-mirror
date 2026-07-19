from datetime import date
from pathlib import Path

from qepm.universe_data_store.starting_holdings import load_starting_holdings


def test_statement_holdings_load_to_figi_indexed_contract(tmp_path: Path):
    source = tmp_path / "holdings.csv"
    source.write_text("ticker,cusip,dollar_value\nSAMPLE-CORE-1,US0000000001,55246.05\n")

    holdings = load_starting_holdings(source, date(2026, 6, 16), {"US0000000001": "BBG-FIXTURE-013"})

    assert holdings.positions.loc["BBG-FIXTURE-013", "dollar_value"] == 55246.05
