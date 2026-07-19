"""Registers the adapters built for specific, named real sources in Data/.

This is the running list of registered sources: each entry is one source,
added without touching any other adapter, the registry, the gate, or
anything in Phase 2+. Call register_known_sources() to populate the
registry (tests and scripts do this explicitly - it's not automatic on
import, matching how Factor Registry entries are also explicit calls,
not import-time side effects).
"""

from __future__ import annotations

from qepm.universe_data_store.adapters.bulk_macro_parquet import BulkMacroParquetAdapter
from qepm.universe_data_store.adapters.msci_esg_parquet import MsciEsgAdapter
from qepm.universe_data_store.adapters.registry import register_adapter
from qepm.universe_data_store.adapters.single_ticker_excel import SingleTickerExcelAdapter
from qepm.universe_data_store.crosswalk import ISIN_TO_FIGI, TICKER_TO_FIGI


def register_known_sources() -> None:
    register_adapter(SingleTickerExcelAdapter(TICKER_TO_FIGI))  # Data/PriceHistory.xlsx
    register_adapter(BulkMacroParquetAdapter(name="ff5_fama_french"))  # Data/ff5.parquet
    register_adapter(BulkMacroParquetAdapter(name="ff3_fama_french"))  # Data/ff3.parquet
    register_adapter(BulkMacroParquetAdapter(name="cboe_vix", date_column="Date"))  # Data/cboeall1986.parquet
    register_adapter(MsciEsgAdapter(ISIN_TO_FIGI))  # Data/msci.parquet
