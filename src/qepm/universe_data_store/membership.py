"""Point-in-time Russell 1000 membership (CONTEXT.md: Universe).

No real Russell 1000 historical membership feed exists in this repo yet -
PointInTimeMembership is a real, usable interface backed by explicit
windows; wire in a real vendor membership history (dates a FIGI entered/
left the index) once that source is sourced, with no change to the gate
or anything downstream.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class MembershipWindow:
    figi: str
    start_date: date
    end_date: date | None = None  # None = still a constituent


class PointInTimeMembership:
    def __init__(self, windows: list[MembershipWindow]) -> None:
        self._windows = windows

    def is_member(self, figi: str, as_of: date) -> bool:
        return any(
            w.figi == figi and w.start_date <= as_of and (w.end_date is None or as_of <= w.end_date)
            for w in self._windows
        )
