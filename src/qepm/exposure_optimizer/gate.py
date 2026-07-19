"""Factor -> Optimizer phase gate: validates a FactorScoreMatrix before optimization."""

from __future__ import annotations

import numpy as np
import pandas as pd

from qepm.contracts import FactorScoreMatrix, Holdings, PhaseGateError, Snapshot
from qepm.portfolio_state import validate_long_only_holdings, validate_snapshot_identities


def validate_scores_for_optimization(scores: FactorScoreMatrix) -> None:
    if scores.scores.index.name != "figi":
        raise PhaseGateError("FactorScoreMatrix.scores must be indexed by 'figi'")

    if scores.scores.shape[1] == 0:
        raise PhaseGateError("FactorScoreMatrix.scores has no factor columns")

    if scores.scores.index.duplicated().any():
        dupes = scores.scores.index[scores.scores.index.duplicated()].tolist()
        raise PhaseGateError(f"FactorScoreMatrix.scores has duplicate FIGIs: {dupes}")

    if scores.scores.isna().all(axis=None):
        raise PhaseGateError("FactorScoreMatrix.scores is entirely missing - nothing to optimize on")

    numeric = scores.scores.apply(pd.to_numeric, errors="coerce")
    non_numeric = scores.scores.notna() & numeric.isna()
    if non_numeric.any(axis=None):
        raise PhaseGateError("FactorScoreMatrix.scores must be numeric or N/A")
    non_finite = numeric.notna() & ~np.isfinite(numeric)
    if non_finite.any(axis=None):
        raise PhaseGateError("FactorScoreMatrix.scores contains non-finite values")


def validate_inputs_for_optimization(snapshot: Snapshot, scores: FactorScoreMatrix, holdings: Holdings) -> None:
    """Ensure every optimization input describes one point-in-time portfolio state."""
    validate_scores_for_optimization(scores)
    validate_snapshot_identities(snapshot)
    validate_long_only_holdings(holdings)
    if snapshot.as_of != scores.as_of or holdings.as_of != scores.as_of:
        raise PhaseGateError("optimizer requires snapshot, scores, and holdings from the same as_of date")
    missing_figis = holdings.positions.index.difference(snapshot.securities.index)
    if not missing_figis.empty:
        raise PhaseGateError(f"optimizer holdings are absent from the snapshot: {missing_figis.tolist()}")
