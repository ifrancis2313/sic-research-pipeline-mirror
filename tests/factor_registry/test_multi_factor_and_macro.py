import numpy as np
import pytest

from qepm.contracts import Snapshot
from qepm.factor_registry import FactorRegistry, score_universe
from qepm.factor_registry.stub_factors import STUB_MACRO_ADJUSTED_MOMENTUM, STUB_MOMENTUM


@pytest.fixture
def multi_factor_registry():
    reg = FactorRegistry()
    reg.register(STUB_MOMENTUM)
    reg.register(STUB_MACRO_ADJUSTED_MOMENTUM)
    return reg


def test_two_simultaneous_factors_produce_a_correctly_shaped_matrix(snapshot, multi_factor_registry):
    result = score_universe(snapshot, multi_factor_registry)

    assert set(result.scores.columns) == {"momentum", "macro_adjusted_momentum"}
    assert len(result.scores) == len(snapshot.securities)


def test_macro_referencing_factor_actually_reads_the_macro_series(snapshot, multi_factor_registry):
    result = score_universe(snapshot, multi_factor_registry)

    risk_free_rate = snapshot.macro.loc[snapshot.as_of, "risk_free_rate"]
    expected = snapshot.securities["momentum_raw"].astype(float) - risk_free_rate
    assert result.scores["macro_adjusted_momentum"].equals(expected)


def test_a_missing_field_only_nans_the_affected_security_not_other_securities_or_factors(
    snapshot, multi_factor_registry
):
    securities = snapshot.securities.copy()
    gap_figi = securities.index[0]
    other_figi = securities.index[1]
    securities.loc[gap_figi, "momentum_raw"] = np.nan
    gapped_snapshot = Snapshot(as_of=snapshot.as_of, securities=securities, macro=snapshot.macro)

    result = score_universe(gapped_snapshot, multi_factor_registry)

    # both factors depend on momentum_raw, so both are explicitly NaN for the gapped security...
    assert np.isnan(result.scores.loc[gap_figi, "momentum"])
    assert np.isnan(result.scores.loc[gap_figi, "macro_adjusted_momentum"])
    # ...but every other security's scores, for both factors, are untouched
    assert not np.isnan(result.scores.loc[other_figi, "momentum"])
    assert not np.isnan(result.scores.loc[other_figi, "macro_adjusted_momentum"])
