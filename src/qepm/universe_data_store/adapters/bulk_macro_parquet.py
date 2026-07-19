"""Adapter for a bulk, date-keyed (no security column) parquet file, e.g. Data/ff5.parquet.

Fama-French factor returns are a Macro series (CONTEXT.md): market-wide,
not crosswalkable to any single security, so this never touches FIGI.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from qepm.universe_data_store.adapters.base import Adapter, AdapterOutput


class BulkMacroParquetAdapter(Adapter):
    """Generic enough to register once per source (e.g. "ff5_fama_french",
    "cboe_vix") without writing a new class - give each instance its own
    `name` so the registry can tell separately-registered sources apart.
    """

    def __init__(self, name: str = "bulk_macro_parquet", date_column: str = "date") -> None:
        self.name = name
        self.date_column = date_column

    def load(self, source: Any) -> AdapterOutput:
        raw = pd.read_parquet(source)
        macro = raw.copy()
        macro["date"] = pd.to_datetime(macro[self.date_column]).dt.date
        if self.date_column != "date":
            macro = macro.drop(columns=[self.date_column])
        macro = macro.set_index("date").sort_index()

        return AdapterOutput(macro=macro)
