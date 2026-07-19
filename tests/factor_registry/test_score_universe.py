import numpy as np

from qepm.contracts import Snapshot
from qepm.factor_registry import score_universe


def test_scores_match_raw_momentum_field(snapshot, registry):
    result = score_universe(snapshot, registry)

    assert list(result.scores.columns) == ["momentum"]
    assert result.scores["momentum"].equals(snapshot.securities["momentum_raw"].astype(float))
    assert result.as_of == snapshot.as_of


def test_score_matrix_carries_each_factors_registered_weight(snapshot, registry):
    result = score_universe(snapshot, registry)

    assert result.weights == {"momentum": registry.get("momentum").weight}


def test_security_missing_underlying_field_scores_as_nan(snapshot, registry):
    securities = snapshot.securities.copy()
    securities.loc[securities.index[0], "momentum_raw"] = np.nan
    snapshot_with_gap = Snapshot(as_of=snapshot.as_of, securities=securities, macro=snapshot.macro)

    result = score_universe(snapshot_with_gap, registry)

    assert np.isnan(result.scores["momentum"].iloc[0])
    assert not result.scores["momentum"].iloc[1:].isna().any()
