"""Select context windows by positive-duration half-open flag intersection."""

from __future__ import annotations

from typing import Mapping, Sequence

from scripts.core.errors import ContractError
from scripts.core.records import Interval

from .fusion import FusedFlag


def select_flagged_windows(
    windows: Sequence[Mapping], flags: Sequence[FusedFlag]
) -> list[dict]:
    selected: list[dict] = []
    seen: set[str] = set()
    for window in windows:
        window_id = window["window_id"]
        if window_id in seen:
            raise ContractError(f"duplicate window ID: {window_id}")
        seen.add(window_id)
        interval = Interval(window["start_seconds"], window["end_seconds"])
        matching = [
            flag.flag_id
            for flag in flags
            if interval.overlaps(Interval(flag.start_seconds, flag.end_seconds))
        ]
        if matching:
            copied = dict(window)
            copied["flag_ids"] = matching
            selected.append(copied)
    return selected
