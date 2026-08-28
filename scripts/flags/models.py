"""Canonical records shared by the three independent flag sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from scripts.core.errors import ContractError
from scripts.core.records import Interval


class FlagSource(str, Enum):
    CLIP_URGENCY = "clip_urgency"
    VITALS_THRESHOLD = "vitals_threshold"
    TRANSCRIPT_KEYWORD = "transcript_keyword"


class FlagStatus(str, Enum):
    SUCCESS_NONEMPTY = "success_nonempty"
    SUCCESS_EMPTY = "success_empty"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass(frozen=True)
class FlagRecord:
    flag_id: str
    source: FlagSource
    start_seconds: float
    end_seconds: float
    evidence_ids: tuple[str, ...]
    policy_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        Interval(self.start_seconds, self.end_seconds)
        if not self.flag_id or not self.evidence_ids or not self.policy_id:
            raise ContractError("flag records require ID, evidence IDs, and policy ID")

    def to_dict(self) -> dict[str, Any]:
        return {
            "flag_id": self.flag_id,
            "source": self.source.value,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "evidence_ids": list(self.evidence_ids),
            "policy_id": self.policy_id,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class FlagArtifact:
    session_id: str
    source: FlagSource
    status: FlagStatus
    flags: tuple[FlagRecord, ...] = ()
    failure_reason: str | None = None
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if any(flag.source != self.source for flag in self.flags):
            raise ContractError("flag artifact contains a record from another source")
        if self.status == FlagStatus.SUCCESS_NONEMPTY and not self.flags:
            raise ContractError("success_nonempty flag artifact requires records")
        if self.status != FlagStatus.SUCCESS_NONEMPTY and self.flags:
            raise ContractError(f"{self.status.value} flag artifact cannot contain records")
        if self.status in {FlagStatus.UNAVAILABLE, FlagStatus.FAILED} and not self.failure_reason:
            raise ContractError(f"{self.status.value} flag artifact requires a reason")
        if self.status in {FlagStatus.SUCCESS_NONEMPTY, FlagStatus.SUCCESS_EMPTY} and self.failure_reason:
            raise ContractError("successful flag artifact cannot contain a failure reason")

    @classmethod
    def success(
        cls,
        *,
        session_id: str,
        source: FlagSource,
        flags: tuple[FlagRecord, ...] | list[FlagRecord],
        provenance: Mapping[str, Any],
    ) -> "FlagArtifact":
        materialized = tuple(flags)
        return cls(
            session_id=session_id,
            source=source,
            status=(FlagStatus.SUCCESS_NONEMPTY if materialized else FlagStatus.SUCCESS_EMPTY),
            flags=materialized,
            provenance=provenance,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "session_id": self.session_id,
            "source": self.source.value,
            "status": self.status.value,
            "failure_reason": self.failure_reason,
            "flags": [flag.to_dict() for flag in self.flags],
            "provenance": dict(self.provenance),
        }
