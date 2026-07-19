#!/usr/bin/env python3
"""One-off refresh of `crosswalk_cache.json`: batch-resolves the specific
tickers/ISINs the repo's known adapters (registrations.py) currently need
via the real OpenFIGI API, and writes the result to a committed cache file
so the pipeline never makes a live symbology call on its hot path.

Run whenever a new security is added to Data/ and needs a crosswalk entry:

    .venv/bin/python scripts/refresh_figi_crosswalk.py

Pass an OpenFIGI API key (raises the per-request batch cap and rate limit)
via the OPENFIGI_API_KEY env var if resolving a larger universe later.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from qepm.universe_data_store.openfigi import resolve_index_tickers_to_figi, resolve_isins_to_figi

CACHE_PATH = Path(__file__).resolve().parent.parent / "src" / "qepm" / "universe_data_store" / "crosswalk_cache.json"

# The securities Data/'s known adapters currently reference (registrations.py).
# Add to these lists, rerun this script, and commit the updated cache file
# as new securities are added -- don't hand-edit crosswalk_cache.json.
INDEX_TICKERS = ["SPX"]  # Data/PriceHistory.xlsx ("Price History: SPX" title cell -- the S&P 500 Index)
ISINS = [
    "US0000000101",  # example equity A
    "US0000000102",  # example equity B
]


def main() -> None:
    api_key = os.environ.get("OPENFIGI_API_KEY")

    ticker_to_figi = resolve_index_tickers_to_figi(INDEX_TICKERS, api_key=api_key)
    isin_to_figi = resolve_isins_to_figi(ISINS, api_key=api_key)

    unresolved_tickers = set(INDEX_TICKERS) - set(ticker_to_figi)
    unresolved_isins = set(ISINS) - set(isin_to_figi)
    if unresolved_tickers or unresolved_isins:
        print(f"WARNING: unresolved tickers={unresolved_tickers} isins={unresolved_isins} "
              f"-- see the openfigi logger warnings above for why")

    cache = {"ticker_to_figi": ticker_to_figi, "isin_to_figi": isin_to_figi}
    CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
    print(f"wrote {CACHE_PATH} -- {len(ticker_to_figi)} ticker(s), {len(isin_to_figi)} ISIN(s)")


if __name__ == "__main__":
    main()
