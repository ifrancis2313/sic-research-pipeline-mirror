"""The Adapter interface: a source/format-specific mapping into Phase 1's contract.

Adding a new source is always a new Adapter subclass + registration
(registry.py) - never a change to anything downstream of Phase 1.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class AdapterOutput:
    """What an adapter produces: a per-security panel slice, a macro slice, or both."""

    panel: pd.DataFrame | None = None  # MultiIndex (figi, date) if present
    macro: pd.DataFrame | None = None  # Index "date" if present


class Adapter(ABC):
    name: str

    @abstractmethod
    def load(self, source: Any) -> AdapterOutput: ...
