import pytest

from qepm.universe_data_store.adapters import registry


class _FakeAdapter:
    def __init__(self, name: str):
        self.name = name


def test_register_adapter_is_retrievable_by_name():
    registry.register_adapter(_FakeAdapter("alpha"))
    assert registry.get_adapter("alpha").name == "alpha"


def test_registering_a_duplicate_name_raises_instead_of_silently_overwriting():
    first = _FakeAdapter("alpha")
    registry.register_adapter(first)

    with pytest.raises(ValueError, match="alpha"):
        registry.register_adapter(_FakeAdapter("alpha"))

    # the original registration must survive the failed second attempt
    assert registry.get_adapter("alpha") is first
