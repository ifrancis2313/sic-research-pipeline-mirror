"""Universe & Data Store (Phase 1).

Produces a FIGI-keyed Snapshot (per-security panel + macro series) for a
given as_of date. get_universe_snapshot still serves the hand-built
fixture from the walking skeleton - the real contract,
adapter framework, and gate built to support it (DataStore,
Adapter, gate.py) are usable now but not yet wired into
get_universe_snapshot itself; that wiring is follow-up work once enough
real adapters exist to seed a real snapshot.
"""

from __future__ import annotations

from datetime import date

from qepm.contracts import Snapshot
from qepm.universe_data_store.fixtures import fixture_snapshot
from qepm.universe_data_store.store import DataStore


def get_universe_snapshot(as_of: date) -> Snapshot:
    return fixture_snapshot(as_of)


__all__ = ["get_universe_snapshot", "Snapshot", "DataStore"]
