"""Phase 1's canonical internal shapes (ADR 0002): per-security panel + macro series.

Every adapter's output gets coerced into one (or both) of these before it's
allowed into the DataStore - see gate.py for the checks that enforce it.
"""

from __future__ import annotations

import pandas as pd

PANEL_INDEX_NAMES = ("figi", "date")
MACRO_INDEX_NAME = "date"


def empty_panel() -> pd.DataFrame:
    index = pd.MultiIndex.from_arrays([[], []], names=PANEL_INDEX_NAMES)
    return pd.DataFrame(index=index)


def empty_macro() -> pd.DataFrame:
    return pd.DataFrame(index=pd.DatetimeIndex([], name=MACRO_INDEX_NAME))


def is_panel_shaped(frame: pd.DataFrame) -> bool:
    return isinstance(frame.index, pd.MultiIndex) and tuple(frame.index.names) == PANEL_INDEX_NAMES


def is_macro_shaped(frame: pd.DataFrame) -> bool:
    return not isinstance(frame.index, pd.MultiIndex) and frame.index.name == MACRO_INDEX_NAME
