from datetime import date
from pathlib import Path

import pytest
from hypothesis import settings

from qepm.factor_registry import FactorRegistry, score_universe
from qepm.factor_registry.stub_factors import STUB_MOMENTUM
from qepm.universe_data_store import get_universe_snapshot
from qepm.universe_data_store.fixtures import fixture_holdings

# Hypothesis's default 200ms per-example deadline is a CI-stability trap for
# pandas-backed property tests: a slow CI runner or a GC pause mid-example
# fails the test on timing, not logic. None of these property tests make a
# performance claim, so timing isn't a property worth checking here.
settings.register_profile("qepm", deadline=None)
settings.load_profile("qepm")

DATA_DIR = Path(__file__).resolve().parent.parent / "Data"


@pytest.fixture
def data_dir():
    if not DATA_DIR.is_dir():
        pytest.skip("source-backed adapter fixtures are not included in the public repository")
    return DATA_DIR


@pytest.fixture
def as_of():
    return date(2026, 7, 4)


@pytest.fixture
def snapshot(as_of):
    return get_universe_snapshot(as_of)


@pytest.fixture
def holdings(as_of):
    return fixture_holdings(as_of)


@pytest.fixture
def registry():
    reg = FactorRegistry()
    reg.register(STUB_MOMENTUM)
    return reg


@pytest.fixture
def scores(snapshot, registry):
    return score_universe(snapshot, registry)
