"""Failure-isolated invocation and policy-gated cross-source flag fusion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from scripts.core.errors import ContractError

from .models import FlagArtifact, FlagRecord, FlagSource, FlagStatus


Producer = Callable[[], FlagArtifact]
FIXED_MERGE_GAP_SECONDS = 10.0
FIXED_MERGE_POLICY_ID = "flag-fusion-v1.0.0"


def run_independent_sources(
    session_id: str, producers: Mapping[FlagSource, Producer]
) -> dict[FlagSource, FlagArtifact]:
    """Invoke all three producers even when peers are empty or raise."""
    expected = set(FlagSource)
    if set(producers) != expected:
        raise ContractError("exactly the three paper flag producers are required")
    results: dict[FlagSource, FlagArtifact] = {}
    for source in FlagSource:
        try:
            artifact = producers[source]()
            if artifact.source != source or artifact.session_id != session_id:
                raise ContractError("flag producer returned the wrong source or session")
            results[source] = artifact
        except Exception as exc:  # isolation boundary: peer sources must still run
            results[source] = FlagArtifact(
                session_id=session_id,
                source=source,
                status=FlagStatus.FAILED,
                failure_reason=f"{type(exc).__name__}: {exc}",
                provenance={},
            )
    return results


@dataclass(frozen=True)
class FusedFlag:
    flag_id: str
    start_seconds: float
    end_seconds: float
    contributions: tuple[FlagRecord, ...]

    def to_dict(self) -> dict:
        return {
            "flag_id": self.flag_id,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "contribution_ids": [item.flag_id for item in self.contributions],
            "contributions": [item.to_dict() for item in self.contributions],
        }


@dataclass(frozen=True)
class FusedFlagArtifact:
    session_id: str
    status: FlagStatus
    flags: tuple[FusedFlag, ...]
    source_statuses: Mapping[FlagSource, FlagStatus]
    merge_policy_id: str

    def to_dict(self) -> dict:
        return {
            "schema_version": "1.0.0",
            "session_id": self.session_id,
            "source": "fused",
            "status": self.status.value,
            "failure_reason": None,
            "flags": [flag.to_dict() for flag in self.flags],
            "source_statuses": {
                source.value: status.value for source, status in self.source_statuses.items()
            },
            "provenance": {"merge_policy_id": self.merge_policy_id},
        }


def fuse_flags(
    artifacts: Mapping[FlagSource, FlagArtifact],
    *,
    merge_gap_seconds: float,
    merge_on_equal_gap: bool,
    merge_policy_id: str,
    paper_mode: bool = True,
) -> FusedFlagArtifact:
    if paper_mode and (
        merge_gap_seconds != FIXED_MERGE_GAP_SECONDS
        or merge_on_equal_gap is not True
        or merge_policy_id != FIXED_MERGE_POLICY_ID
    ):
        raise ContractError("paper mode requires fixed 10-second inclusive flag fusion")
    if set(artifacts) != set(FlagSource):
        raise ContractError("fusion requires an artifact/status from every source")
    if merge_gap_seconds < 0 or not merge_policy_id:
        raise ContractError("explicit non-negative merge gap and policy ID are required")
    session_ids = {artifact.session_id for artifact in artifacts.values()}
    if len(session_ids) != 1:
        raise ContractError("cannot fuse flags from different sessions")
    records = sorted(
        (record for artifact in artifacts.values() for record in artifact.flags),
        key=lambda item: (item.start_seconds, item.end_seconds, item.flag_id),
    )
    groups: list[list[FlagRecord]] = []
    for record in records:
        if not groups:
            groups.append([record])
            continue
        current_end = max(item.end_seconds for item in groups[-1])
        gap = record.start_seconds - current_end
        should_merge = gap < 0 or gap < merge_gap_seconds or (
            merge_on_equal_gap and gap == merge_gap_seconds
        )
        if should_merge:
            groups[-1].append(record)
        else:
            groups.append([record])
    fused = tuple(
        FusedFlag(
            flag_id=f"fused-{index:04d}",
            start_seconds=min(item.start_seconds for item in group),
            end_seconds=max(item.end_seconds for item in group),
            contributions=tuple(group),
        )
        for index, group in enumerate(groups)
    )
    return FusedFlagArtifact(
        session_id=session_ids.pop(),
        status=FlagStatus.SUCCESS_NONEMPTY if fused else FlagStatus.SUCCESS_EMPTY,
        flags=fused,
        source_statuses={source: artifact.status for source, artifact in artifacts.items()},
        merge_policy_id=merge_policy_id,
    )


def fuse_flags_fixed(
    artifacts: Mapping[FlagSource, FlagArtifact], *, paper_mode: bool = True
) -> FusedFlagArtifact:
    """Apply the one normative cross-source temporal merge policy."""
    return fuse_flags(
        artifacts,
        merge_gap_seconds=FIXED_MERGE_GAP_SECONDS,
        merge_on_equal_gap=True,
        merge_policy_id=FIXED_MERGE_POLICY_ID,
        paper_mode=paper_mode,
    )
