"""The growing historical store: a bulk backfill path plus an incremental append path.

Every write - backfill or append - goes through an Adapter and Phase 1's
gate first (validate_adapter_output), so nothing enters the store without
conforming to the canonical shape, per ADR 0002.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from qepm.contracts import PhaseGateError, Snapshot
from qepm.universe_data_store.adapters.base import Adapter, AdapterOutput
from qepm.universe_data_store.gate import validate_adapter_output
from qepm.universe_data_store.membership import PointInTimeMembership
from qepm.universe_data_store.schema import empty_macro, empty_panel


class DataStore:
    """Phase 1's canonical per-security panel + macro series, accumulated over time."""

    def __init__(self) -> None:
        self.panel: pd.DataFrame = empty_panel()
        self.macro: pd.DataFrame = empty_macro()

    def backfill(
        self, adapter: Adapter, source: Any, membership: PointInTimeMembership | None = None
    ) -> AdapterOutput:
        """Seed an empty store from one adapter's full historical pull.

        Backfill is intentionally one-time.  Later data must use ``append``
        so the conflict gate can prevent historical revisions from silently
        replacing the canonical record.
        """
        if not self.panel.empty or not self.macro.empty:
            raise PhaseGateError("DataStore already contains history; use append rather than backfill")
        output = adapter.load(source)
        validate_adapter_output(output, membership)
        if output.panel is not None:
            self.panel = output.panel.sort_index()
        if output.macro is not None:
            self.macro = output.macro.sort_index()
        return output

    def append(
        self, adapter: Adapter, source: Any, membership: PointInTimeMembership | None = None
    ) -> AdapterOutput:
        """Add new rows to existing history without reprocessing what's already stored."""
        output = adapter.load(source)
        validate_adapter_output(output, membership)
        if output.panel is not None:
            self.panel = _merge_new_rows(self.panel, output.panel)
        if output.macro is not None:
            self.macro = _merge_new_rows(self.macro, output.macro)
        return output

    def snapshot(self, as_of: date, *, fundamental_fields: tuple[str, ...]) -> Snapshot:
        """Materialize one point-in-time snapshot from stored history.

        Market and reference fields come only from the requested trading date.
        Each named fundamental may carry forward its latest valid observation,
        but only when that observation records the date it became available.
        This keeps stale fundamentals usable between filings without allowing
        a later filing to enter an earlier snapshot.
        """
        as_of_timestamp = pd.Timestamp(as_of)
        panel_dates = pd.to_datetime(self.panel.index.get_level_values("date"))
        current = self.panel.loc[panel_dates == as_of_timestamp].copy()
        securities = current.droplevel("date")

        historical = self.panel.loc[panel_dates <= as_of_timestamp]
        for field in fundamental_fields:
            field_asof = f"{field}_asof"
            if field not in self.panel.columns:
                raise ValueError(f"fundamental field '{field}' is absent from the DataStore panel")
            if field_asof not in self.panel.columns:
                raise ValueError(
                    f"fundamental field '{field}' requires a '{field_asof}' availability-date column"
                )

            observations = historical[[field, field_asof]].dropna(subset=[field, field_asof]).copy()
            available = pd.to_datetime(observations[field_asof]) <= as_of_timestamp
            observations = observations.loc[available]
            latest = observations.groupby(level="figi").tail(1)
            # Carry fundamentals only onto securities present in the requested
            # day's market panel. A delisted or missing FIGI must not turn a
            # valid historical observation into an opaque pandas KeyError.
            latest = latest.loc[latest.index.get_level_values("figi").isin(securities.index)]

            securities.loc[latest.index.get_level_values("figi"), field] = latest[field].to_numpy()
            securities.loc[latest.index.get_level_values("figi"), field_asof] = latest[field_asof].to_numpy()

        macro_dates = pd.to_datetime(self.macro.index)
        macro = self.macro.loc[macro_dates == as_of_timestamp].copy()
        return Snapshot(as_of=as_of, securities=securities, macro=macro)


def _merge_new_rows(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    """Merge source slices without silently revising populated history.

    A later source may complete a missing field on an already stored row.
    It may not replace a populated historical value: that is a vendor-data
    disagreement that must be reconciled before it enters the canonical store.
    """
    overlapping_rows = existing.index.intersection(incoming.index)
    common_columns = existing.columns.intersection(incoming.columns)
    conflicts: list[tuple[object, str, object, object]] = []
    for row_index in overlapping_rows:
        for column in common_columns:
            stored = existing.loc[row_index, column]
            proposed = incoming.loc[row_index, column]
            if pd.notna(stored) and pd.notna(proposed) and stored != proposed:
                conflicts.append((row_index, column, stored, proposed))

    if conflicts:
        preview = conflicts[:5]
        raise PhaseGateError(
            "cannot append conflicting populated values for existing historical rows: "
            f"{preview}"
        )

    # Existing populated values win; incoming data fills only missing fields
    # and contributes genuinely new rows/columns.
    return existing.combine_first(incoming).sort_index()
