"""Fixed differential-CLIP urgency policy and adapter."""

from __future__ import annotations

from dataclasses import dataclass
from math import fsum, isfinite
from typing import Iterable, Mapping, Protocol, Sequence

from scripts.core.errors import ContractError
from scripts.core.records import Interval

from .models import FlagArtifact, FlagRecord, FlagSource


@dataclass(frozen=True)
class ClipUrgencyInterval:
    interval_id: str
    start_seconds: float
    end_seconds: float
    evidence_ids: tuple[str, ...]
    camera_ids: tuple[str, ...]
    score_record: Mapping

    def __post_init__(self) -> None:
        Interval(self.start_seconds, self.end_seconds)
        if not self.interval_id or not self.evidence_ids or not self.camera_ids:
            raise ContractError("CLIP urgency intervals require ID, evidence, and source cameras")


class ClipUrgencyPolicy(Protocol):
    """Versioned templates, scoring, thresholding, and camera merge policy."""

    policy_id: str

    def flag(self, frame_records: Sequence[Mapping]) -> Iterable[ClipUrgencyInterval]: ...


ROUTINE_TEMPLATES = (
    "medical staff calmly monitoring patient in hospital room",
    "nurses and doctors having routine clinical discussion",
    "healthcare workers doing regular patient assessment",
    "medical team performing standard patient care",
)
EMERGENCY_TEMPLATES = (
    "medical staff suddenly running towards patient in distress",
    "healthcare team actively performing CPR chest compressions",
    "doctors and nurses rushing with crash cart",
    "medical emergency with staff frantically working on patient",
    "team urgently gathering around deteriorating patient",
    "medical crisis with rapid coordinated response",
)
CLIP_POLICY_ID = "clip-urgency-v1.0.0"


class FixedClipUrgencyPolicy:
    """Score cameras independently and retain fixed-policy positive runs."""

    policy_id = CLIP_POLICY_ID
    minimum_consecutive_bins = 5
    within_camera_merge_gap_seconds = 10.0

    @staticmethod
    def _score(record: Mapping) -> tuple[str, int, str, float]:
        camera_id = record.get("camera_id")
        bin_index = record.get("bin_index")
        evidence_id = record.get("evidence_id")
        timestamp = record.get("aligned_timestamp_seconds")
        if camera_id not in {"cam1", "cam2", "cam3"}:
            raise ContractError("CLIP urgency frame requires cam1, cam2, or cam3")
        if not isinstance(bin_index, int) or bin_index < 0:
            raise ContractError("CLIP urgency frame requires a non-negative bin_index")
        if not isinstance(evidence_id, str) or not evidence_id:
            raise ContractError("CLIP urgency frame requires evidence_id")
        if timestamp is None or not isfinite(float(timestamp)) or not bin_index <= float(timestamp) < bin_index + 1:
            raise ContractError("CLIP urgency frame timestamp must fall in its half-open bin")
        routine, emergency = record.get("routine_logits"), record.get("emergency_logits")
        if (
            not isinstance(routine, Sequence) or isinstance(routine, (str, bytes)) or len(routine) != len(ROUTINE_TEMPLATES)
            or not isinstance(emergency, Sequence) or isinstance(emergency, (str, bytes)) or len(emergency) != len(EMERGENCY_TEMPLATES)
        ):
            raise ContractError("CLIP urgency requires four routine and six emergency logits")
        routine_values = tuple(float(value) for value in routine)
        emergency_values = tuple(float(value) for value in emergency)
        if not all(isfinite(value) for value in routine_values + emergency_values):
            raise ContractError("CLIP logits must be finite")
        return camera_id, bin_index, evidence_id, max(emergency_values) - max(routine_values)

    def flag(self, frame_records: Sequence[Mapping]) -> Iterable[ClipUrgencyInterval]:
        per_camera: dict[str, dict[int, tuple[str, float]]] = {
            "cam1": {}, "cam2": {}, "cam3": {}
        }
        for record in frame_records:
            camera_id, bin_index, evidence_id, score = self._score(record)
            if bin_index in per_camera[camera_id]:
                raise ContractError(f"duplicate CLIP urgency bin {camera_id}/{bin_index}")
            per_camera[camera_id][bin_index] = (evidence_id, score)

        output: list[ClipUrgencyInterval] = []
        for camera_id in ("cam1", "cam2", "cam3"):
            positive_runs: list[list[tuple[int, str, float]]] = []
            current: list[tuple[int, str, float]] = []
            for bin_index, (evidence_id, score) in sorted(per_camera[camera_id].items()):
                if score > 0.0 and (not current or bin_index == current[-1][0] + 1):
                    current.append((bin_index, evidence_id, score))
                else:
                    if len(current) >= self.minimum_consecutive_bins:
                        positive_runs.append(current)
                    current = [(bin_index, evidence_id, score)] if score > 0.0 else []
            if len(current) >= self.minimum_consecutive_bins:
                positive_runs.append(current)

            merged: list[list[tuple[int, str, float]]] = []
            for run in positive_runs:
                if (
                    merged
                    and run[0][0] - (merged[-1][-1][0] + 1)
                    <= self.within_camera_merge_gap_seconds
                ):
                    merged[-1].extend(run)
                else:
                    merged.append(list(run))
            for index, run in enumerate(merged):
                scores = [item[2] for item in run]
                output.append(ClipUrgencyInterval(
                    interval_id=f"{camera_id}-{index:04d}",
                    start_seconds=float(run[0][0]),
                    end_seconds=float(run[-1][0] + 1),
                    evidence_ids=tuple(item[1] for item in run),
                    camera_ids=(camera_id,),
                    score_record={
                        "maximum_urgency_score": max(scores),
                        "mean_urgency_score": fsum(scores) / len(scores),
                        "positive_bin_ids": [item[0] for item in run],
                        "threshold_comparison": "> 0.0",
                    },
                ))
        return output


class ClipUrgencyAdapter:
    def __init__(self, policy: ClipUrgencyPolicy | None = None, *, paper_mode: bool = True) -> None:
        policy = policy or FixedClipUrgencyPolicy()
        if paper_mode and type(policy) is not FixedClipUrgencyPolicy:
            raise ContractError("paper mode requires the fixed CLIP urgency policy")
        if not policy.policy_id:
            raise ContractError("CLIP urgency policy_id is required")
        self.policy = policy

    def run(self, session_id: str, frame_records: Sequence[Mapping]) -> FlagArtifact:
        flags = [
            FlagRecord(
                flag_id=f"clip-{interval.interval_id}",
                source=FlagSource.CLIP_URGENCY,
                start_seconds=interval.start_seconds,
                end_seconds=interval.end_seconds,
                evidence_ids=interval.evidence_ids,
                policy_id=self.policy.policy_id,
                payload={
                    "camera_ids": list(interval.camera_ids),
                    "score_record": dict(interval.score_record),
                },
            )
            for interval in self.policy.flag(frame_records)
        ]
        return FlagArtifact.success(
            session_id=session_id,
            source=FlagSource.CLIP_URGENCY,
            flags=flags,
            provenance={"policy_id": self.policy.policy_id},
        )
