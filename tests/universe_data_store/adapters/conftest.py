import pytest

from qepm.universe_data_store.adapters import registry


@pytest.fixture(autouse=True)
def _clean_registry():
    """The adapter registry is a module-level dict -- isolate every test in
    this directory from whatever register_known_sources() or another test
    already registered, regardless of collection/execution order. Shared
    here (rather than duplicated per test file) so a new test file in this
    directory gets the same isolation automatically."""
    saved = dict(registry._ADAPTERS)
    registry._ADAPTERS.clear()
    yield
    registry._ADAPTERS.clear()
    registry._ADAPTERS.update(saved)
