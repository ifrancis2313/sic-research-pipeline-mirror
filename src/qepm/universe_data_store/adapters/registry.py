"""Adapter registration: adding a source is additive, never a Phase 2+ change."""

from __future__ import annotations

from qepm.universe_data_store.adapters.base import Adapter

_ADAPTERS: dict[str, Adapter] = {}


def register_adapter(adapter: Adapter) -> None:
    if adapter.name in _ADAPTERS:
        raise ValueError(
            f"an adapter named {adapter.name!r} is already registered -- "
            "give the new source a distinct name rather than silently overwriting the old one"
        )
    _ADAPTERS[adapter.name] = adapter


def get_adapter(name: str) -> Adapter:
    return _ADAPTERS[name]


def registered_adapters() -> dict[str, Adapter]:
    return dict(_ADAPTERS)
