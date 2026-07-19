"""Adapter for a single-ticker Excel export shaped like Data/PriceHistory.xlsx.

Ticker identity lives in a title cell (row 1, e.g. "Price History: SPX"),
not a per-row column; the header is row 3, data starts row 4. Some
columns (e.g. Total Return, Cumulative Return %) may be entirely empty
in a given export and must not be required.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from qepm.universe_data_store.adapters.base import Adapter, AdapterOutput

TITLE_PATTERN = re.compile(r"Price History:\s*(?P<ticker>\S+)", re.IGNORECASE)

# source column name -> canonical panel field name. Columns absent from a
# given export (e.g. always-empty sparse fields) are simply skipped, not required.
COLUMN_MAP = {
    "Price": "price",
    "CVol": "volume",
    "Change": "change",
    "% Change": "pct_change",
    "Total Return (Gross, Unhedged)": "total_return",
    "Cumulative Return % (Gross, Unhedged)": "cumulative_return_pct",
    "Open": "open",
    "High": "high",
    "Low": "low",
}


class SingleTickerExcelAdapter(Adapter):
    name = "single_ticker_excel"

    def __init__(self, ticker_to_figi: dict[str, str]) -> None:
        self.ticker_to_figi = ticker_to_figi

    def load(self, source: Any) -> AdapterOutput:
        title_cell = pd.read_excel(source, header=None, nrows=1).iloc[0, 0]
        match = TITLE_PATTERN.search(str(title_cell))
        if not match:
            raise ValueError(f"could not find a ticker in the title cell: {title_cell!r}")

        ticker = match.group("ticker")
        if ticker not in self.ticker_to_figi:
            raise ValueError(f"no FIGI crosswalk entry for ticker {ticker!r}")
        figi = self.ticker_to_figi[ticker]

        raw = pd.read_excel(source, header=2)
        raw = raw.dropna(subset=["Date"])
        raw["date"] = pd.to_datetime(raw["Date"]).dt.date

        present_columns = [c for c in COLUMN_MAP if c in raw.columns]
        panel = raw[["date"] + present_columns].rename(columns=COLUMN_MAP)
        panel["figi"] = figi
        panel = panel.set_index(["figi", "date"]).sort_index()

        return AdapterOutput(panel=panel)
