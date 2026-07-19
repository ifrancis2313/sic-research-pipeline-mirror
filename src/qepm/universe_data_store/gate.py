"""Phase 1's own gate: validates an adapter's output before it enters the DataStore.

Three checks, per ADR 0002:
1. Schema conformance - panel/macro actually match the canonical shapes.
2. Leakage check - any derived/summarized field only reflects information
   available as of its own row's date. Convention: a derived column
   `<field>` that was computed from a window of history must carry a
   companion `<field>_asof` column recording the date it was actually
   computed through; the gate rejects `<field>_asof` > the row's own date.
3. Point-in-time Russell 1000 membership - every per-security row's FIGI
   must have actually been a constituent as of that row's date.
"""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from qepm.contracts import PhaseGateError
from qepm.universe_data_store.adapters.base import AdapterOutput
from qepm.universe_data_store.membership import PointInTimeMembership
from qepm.universe_data_store.schema import is_macro_shaped, is_panel_shaped


def _is_date_like(value: object) -> bool:
    return isinstance(value, (date, datetime, pd.Timestamp))


def validate_schema(output: AdapterOutput) -> None:
    if output.panel is None and output.macro is None:
        raise PhaseGateError("AdapterOutput has neither a panel nor a macro frame - nothing to ingest")

    if output.panel is not None:
        if not is_panel_shaped(output.panel):
            raise PhaseGateError(
                f"panel must be indexed by {('figi', 'date')}, got {output.panel.index.names}"
            )
        if output.panel.empty:
            raise PhaseGateError("panel is present but has no rows")
        if output.panel.index.duplicated().any():
            duplicates = output.panel.index[output.panel.index.duplicated()].tolist()
            raise PhaseGateError(f"panel has duplicate FIGI/date rows: {duplicates[:5]}")
        dates = output.panel.index.get_level_values("date")
        if not all(_is_date_like(d) for d in dates):
            raise PhaseGateError("panel's 'date' index level contains non-date values")

    if output.macro is not None:
        if not is_macro_shaped(output.macro):
            raise PhaseGateError(f"macro must be indexed by 'date' (single index), got {output.macro.index.names}")
        if output.macro.empty:
            raise PhaseGateError("macro is present but has no rows")
        if output.macro.index.duplicated().any():
            duplicates = output.macro.index[output.macro.index.duplicated()].tolist()
            raise PhaseGateError(f"macro has duplicate macro dates: {duplicates[:5]}")
        if not all(_is_date_like(d) for d in output.macro.index):
            raise PhaseGateError("macro's date index contains non-date values")


def check_no_leakage(panel: pd.DataFrame) -> None:
    row_dates = pd.to_datetime(panel.index.get_level_values("date"))
    for column in panel.columns:
        if not column.endswith("_asof"):
            continue
        computed_asof = pd.to_datetime(panel[column])
        violations = panel.index[computed_asof.to_numpy() > row_dates.to_numpy()]
        if len(violations) > 0:
            raise PhaseGateError(
                f"leakage: '{column}' reflects data computed after its own row's date "
                f"for {list(violations[:5])}"
            )


def check_point_in_time_membership(panel: pd.DataFrame, membership: PointInTimeMembership) -> None:
    violations = [
        (figi, as_of)
        for figi, as_of in panel.index
        if not membership.is_member(figi, as_of)
    ]
    if violations:
        raise PhaseGateError(
            f"{len(violations)} panel row(s) reference a FIGI not in the point-in-time Russell 1000 "
            f"membership as of that row's date: {violations[:5]}"
        )


def validate_adapter_output(
    output: AdapterOutput, membership: PointInTimeMembership | None = None
) -> None:
    validate_schema(output)
    if output.panel is not None:
        check_no_leakage(output.panel)
        if membership is not None:
            check_point_in_time_membership(output.panel, membership)
