"""Data -> Factor phase gate: validates a Snapshot before it's scored.

Per ADR 0002, the receiving phase checks its own upstream input. This is
the boundary between Universe & Data Store and Factor Registry.

check_no_leakage follows the same `<field>_asof` companion-column
convention as Phase 1's own leakage check
(universe_data_store/gate.py): a value derived from a window of history
must carry a column recording the date it was actually computed
through, and that date can never be later than the snapshot's own as_of.
"""

from __future__ import annotations

import pandas as pd

from qepm.contracts import PhaseGateError, Snapshot
from qepm.factor_registry.registry import FactorRegistry


def validate_snapshot_for_scoring(snapshot: Snapshot, registry: FactorRegistry) -> None:
    if snapshot.securities.index.name != "figi":
        raise PhaseGateError("Snapshot.securities must be indexed by 'figi'")

    if snapshot.securities.index.duplicated().any():
        dupes = snapshot.securities.index[snapshot.securities.index.duplicated()].tolist()
        raise PhaseGateError(f"Snapshot.securities has duplicate FIGIs: {dupes}")

    if snapshot.macro.index.name != "date":
        raise PhaseGateError("Snapshot.macro must be indexed by 'date'")

    missing_fields: set[str] = set()
    missing_macro_fields: set[str] = set()
    needs_macro_as_of = False
    for factor in registry.factors.values():
        missing_fields.update(set(factor.required_fields) - set(snapshot.securities.columns))
        missing_macro_fields.update(set(factor.required_macro_fields) - set(snapshot.macro.columns))
        needs_macro_as_of = needs_macro_as_of or bool(factor.required_macro_fields)

    if missing_fields:
        raise PhaseGateError(
            f"Snapshot is missing fields required by registered factors: {sorted(missing_fields)}"
        )
    if missing_macro_fields:
        raise PhaseGateError(
            f"Snapshot's macro series is missing fields required by registered factors: "
            f"{sorted(missing_macro_fields)}"
        )
    if needs_macro_as_of and snapshot.as_of not in snapshot.macro.index:
        raise PhaseGateError(
            f"a registered factor needs the macro series, but Snapshot.macro has no row for "
            f"as_of={snapshot.as_of}"
        )

    check_no_leakage(snapshot)
    _validate_v1_factor_inputs(snapshot, registry)


def check_no_leakage(snapshot: Snapshot) -> None:
    as_of = pd.to_datetime(snapshot.as_of)
    for column in snapshot.securities.columns:
        if not column.endswith("_asof"):
            continue
        computed_asof = pd.to_datetime(snapshot.securities[column])
        violations = snapshot.securities.index[computed_asof > as_of]
        if len(violations) > 0:
            raise PhaseGateError(
                f"leakage: '{column}' reflects data computed after snapshot.as_of={snapshot.as_of} "
                f"for {list(violations[:5])}"
            )


def _validate_v1_factor_inputs(snapshot: Snapshot, registry: FactorRegistry) -> None:
    """Apply V1's economic-domain checks before its formulas divide or log values.

    This remains V1-specific rather than imposing these assumptions on future
    registry entries: a different approved factor may legitimately use a
    different domain. Missing values remain representable as N/A; supplied
    numeric values must be finite and usable by the approved V1 formulas.
    """
    from qepm.factor_registry.v1 import V1_FACTOR_NAMES, validate_v1_numeric_inputs

    if V1_FACTOR_NAMES.issubset(registry.factors):
        validate_v1_numeric_inputs(snapshot)
