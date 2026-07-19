"""Factor Registry (Phase 2).

Holds adopted factor definitions as data (name, scoring formula, weight),
so a Lead Analyst pitch is a registry write, not a code change. Scores
the universe against every adopted factor via score_universe().
"""

from __future__ import annotations

import pandas as pd

from qepm.contracts import FactorScoreMatrix, Snapshot
from qepm.factor_registry.gate import validate_snapshot_for_scoring
from qepm.factor_registry.registry import FactorRegistry

__all__ = ["FactorRegistry", "score_universe"]


def score_universe(snapshot: Snapshot, registry: FactorRegistry) -> FactorScoreMatrix:
    validate_snapshot_for_scoring(snapshot, registry)

    columns = {name: factor.formula(snapshot) for name, factor in registry.factors.items()}
    scores = pd.DataFrame(columns, index=snapshot.securities.index)
    weights = {name: factor.weight for name, factor in registry.factors.items()}
    return FactorScoreMatrix(as_of=snapshot.as_of, scores=scores, weights=weights)
