from datetime import timedelta

import pandas as pd
import pytest

from qepm.contracts import PhaseGateError, Snapshot
from qepm.factor_registry import FactorRegistry, score_universe
from qepm.factor_registry.stub_factors import STUB_MACRO_ADJUSTED_MOMENTUM


def test_rejects_snapshot_missing_a_field_a_registered_factor_needs(snapshot, registry):
    securities = snapshot.securities.drop(columns=["momentum_raw"])
    bad_snapshot = Snapshot(as_of=snapshot.as_of, securities=securities, macro=snapshot.macro)

    with pytest.raises(PhaseGateError, match="momentum_raw"):
        score_universe(bad_snapshot, registry)


def test_rejects_snapshot_with_duplicate_figis(snapshot, registry):
    securities = pd.concat([snapshot.securities.iloc[[0]], snapshot.securities])
    bad_snapshot = Snapshot(as_of=snapshot.as_of, securities=securities, macro=snapshot.macro)

    with pytest.raises(PhaseGateError, match="duplicate"):
        score_universe(bad_snapshot, registry)


def test_rejects_snapshot_not_indexed_by_figi(snapshot, registry):
    securities = snapshot.securities.reset_index(drop=True)
    bad_snapshot = Snapshot(as_of=snapshot.as_of, securities=securities, macro=snapshot.macro)

    with pytest.raises(PhaseGateError, match="figi"):
        score_universe(bad_snapshot, registry)


def test_rejects_snapshot_missing_a_macro_field_a_registered_factor_needs(snapshot):
    macro_registry = FactorRegistry()
    macro_registry.register(STUB_MACRO_ADJUSTED_MOMENTUM)
    macro = snapshot.macro.drop(columns=["risk_free_rate"])
    bad_snapshot = Snapshot(as_of=snapshot.as_of, securities=snapshot.securities, macro=macro)

    with pytest.raises(PhaseGateError, match="risk_free_rate"):
        score_universe(bad_snapshot, macro_registry)


def test_rejects_snapshot_whose_macro_series_has_no_row_for_as_of(snapshot):
    macro_registry = FactorRegistry()
    macro_registry.register(STUB_MACRO_ADJUSTED_MOMENTUM)
    macro = snapshot.macro.copy()
    macro.index = [snapshot.as_of - timedelta(days=1)]
    macro.index.name = "date"
    bad_snapshot = Snapshot(as_of=snapshot.as_of, securities=snapshot.securities, macro=macro)

    with pytest.raises(PhaseGateError, match="no row for"):
        score_universe(bad_snapshot, macro_registry)


def test_leakage_check_rejects_a_future_dated_asof_column(snapshot, registry):
    securities = snapshot.securities.copy()
    securities["rolling_score_asof"] = snapshot.as_of
    securities.loc[securities.index[0], "rolling_score_asof"] = snapshot.as_of + timedelta(days=7)
    bad_snapshot = Snapshot(as_of=snapshot.as_of, securities=securities, macro=snapshot.macro)

    with pytest.raises(PhaseGateError, match="leakage"):
        score_universe(bad_snapshot, registry)
