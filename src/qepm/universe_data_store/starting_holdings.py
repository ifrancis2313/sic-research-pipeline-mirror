"""Load a sanitized SIC brokerage-position CSV into FIGI-keyed holdings."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from qepm.contracts import Holdings


def load_starting_holdings(path: Path, as_of: date, identifier_to_figi: dict[str, str]) -> Holdings:
    """Resolve an ``isin`` column to FIGIs; refuse an incomplete crosswalk."""
    positions = pd.read_csv(path)
    identifier_column = "isin" if "isin" in positions.columns else "cusip"
    positions["figi"] = positions[identifier_column].map(identifier_to_figi)
    unresolved = positions.loc[positions["figi"].isna(), "ticker"].tolist()
    if unresolved:
        raise ValueError(f"missing FIGI crosswalk entries for {unresolved}")
    return Holdings(as_of=as_of, positions=positions.set_index("figi")[["dollar_value"]])
