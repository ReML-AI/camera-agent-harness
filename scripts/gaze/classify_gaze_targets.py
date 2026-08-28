#!/usr/bin/env python3
"""Classify three attention targets on each segment's selected camera.

The patient target is an author-annotated, normalized image box loaded by exact
``(session_id, camera_id)`` key.  There is no person-role lookup, inferred target,
monitor target, or fallback patient region in this path.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from enum import Enum
from math import atan2, degrees, isfinite
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.core.errors import ContractError
from scripts.gaze.calibration import (
    CALIBRATION_PATH,
    CalibrationStore,
    MissingCalibrationError,
    PatientZoneCalibration,
)


ATTENTION_LABELS = ("patient", "person", "other")
ATTENTION_THRESHOLD_DEGREES = 35.0
ROLLING_MODE_WINDOW = 5


class EligibilityStatus(str, Enum):
    ELIGIBLE = "eligible"
    MISSING_CALIBRATION = "ineligible_missing_calibration"
    MISSING_IDENTITY = "ineligible_missing_identity"


class SegmentEligibilityStatus(str, Enum):
    CLASSIFIED = "classified"
    INELIGIBLE = "ineligible"


class SegmentIneligibilityReason(str, Enum):
    MISSING_POSE_ARTIFACT = "missing_pose_artifact"
    MALFORMED_POSE_ARTIFACT = "malformed_pose_artifact"
    MISSING_SELECTED_TRACK_POSE = "missing_selected_track_pose"
    NO_USABLE_POSE_IN_SEGMENT = "no_usable_pose_in_segment"


class AttentionEligibilityError(ContractError):
    """Raised when attention preflight does not return ``eligible``."""

    code = "ATTENTION_INELIGIBLE"


class MissingIdentityError(AttentionEligibilityError):
    code = "ATTENTION_IDENTITY_MISSING"


@dataclass(frozen=True)
class EligibilityReport:
    session_id: str
    status: EligibilityStatus
    required_camera_ids: tuple[str, ...]
    missing_camera_ids: tuple[str, ...] = ()
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["status"] = self.status.value
        result["required_camera_ids"] = list(self.required_camera_ids)
        result["missing_camera_ids"] = list(self.missing_camera_ids)
        return result


@dataclass(frozen=True)
class SegmentEligibility:
    transcript_segment_id: str
    camera_id: str
    track_id: str
    status: SegmentEligibilityStatus
    reason: SegmentIneligibilityReason | None
    pose_samples_classified: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "transcript_segment_id": self.transcript_segment_id,
            "camera_id": self.camera_id,
            "track_id": self.track_id,
            "status": self.status.value,
            "reason": self.reason.value if self.reason is not None else None,
            "pose_samples_classified": self.pose_samples_classified,
        }


@dataclass(frozen=True)
class AttentionClassificationResult:
    records: tuple[dict[str, Any], ...]
    segment_eligibility: tuple[SegmentEligibility, ...]

    def capture_at_run(self) -> dict[str, Any]:
        classified = sum(
            item.status is SegmentEligibilityStatus.CLASSIFIED
            for item in self.segment_eligibility
        )
        reason_counts = Counter(
            item.reason.value
            for item in self.segment_eligibility
            if item.reason is not None
        )
        return {
            "segments_attempted": len(self.segment_eligibility),
            "segments_classified": classified,
            "segments_ineligible": len(self.segment_eligibility) - classified,
            "segments_ineligible_by_reason": {
                reason.value: reason_counts[reason.value]
                for reason in SegmentIneligibilityReason
            },
            "pose_samples_classified": len(self.records),
            # Why individual poses were discarded. "no usable pose" is true whether the
            # data is sparse or the producer changed shape; only this separates them.
            "pose_rejections_by_error": dict(_POSE_REJECTIONS),
        }


@dataclass(frozen=True)
class AttentionInput:
    evidence_id: str
    camera_id: str
    track_id: str
    aligned_timestamp_seconds: float
    yaw_degrees: float
    observer_record: object


@dataclass(frozen=True)
class Assignment:
    label: str
    angular_distance_degrees: float | None
    target_track_id: str | None = None


class TargetAssignmentProcedure(Protocol):
    procedure_id: str
    threshold_degrees: float

    def assign(
        self, sample: AttentionInput, calibration: PatientZoneCalibration
    ) -> Assignment: ...


class RollingModeProcedure(Protocol):
    procedure_id: str
    window_size: int

    def smooth(self, labels: Sequence[str]) -> Sequence[str]: ...


def _bbox(value: object, name: str) -> tuple[float, float, float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 4:
        raise ContractError(f"{name} must be normalized [x1, y1, x2, y2]")
    box = tuple(float(item) for item in value)
    if not all(isfinite(item) and 0 <= item <= 1 for item in box):
        raise ContractError(f"{name} values must be finite and in [0, 1]")
    if not box[0] < box[2] or not box[1] < box[3]:
        raise ContractError(f"{name} must have x1 < x2 and y1 < y2")
    return box


def _center(box: Sequence[float]) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def _angular_distance(left: float, right: float) -> float:
    return abs((left - right + 180.0) % 360.0 - 180.0)


def _image_bearing(origin: tuple[float, float], target: tuple[float, float]) -> float:
    """Bearing in the image plane: down=0, right=90, up=180, left=-90."""

    if origin == target:
        return 0.0
    return degrees(atan2(target[0] - origin[0], target[1] - origin[1]))


def _box_angular_distance(
    origin: tuple[float, float], yaw_degrees: float, box: Sequence[float]
) -> float:
    points = (
        _center(box),
        (box[0], box[1]),
        (box[2], box[1]),
        (box[2], box[3]),
        (box[0], box[3]),
    )
    return min(_angular_distance(yaw_degrees, _image_bearing(origin, point)) for point in points)


class FixedTargetAssignment:
    """Deterministic image-plane assignment to patient, another person, or other."""

    procedure_id = "image-box-attention-assignment-v2.0.0"
    threshold_degrees = ATTENTION_THRESHOLD_DEGREES

    def assign(
        self, sample: AttentionInput, calibration: PatientZoneCalibration
    ) -> Assignment:
        if sample.camera_id != calibration.camera_id:
            raise ContractError(
                f"sample camera {sample.camera_id!r} does not match calibration camera "
                f"{calibration.camera_id!r}"
            )
        observer = sample.observer_record
        if not isinstance(observer, Mapping):
            raise ContractError("attention assignment requires an observer record")
        origin = _center(_bbox(observer.get("bbox_normalized"), "observer bbox_normalized"))
        candidates: list[tuple[float, int, str, str | None]] = [
            (
                _box_angular_distance(
                    origin, sample.yaw_degrees, calibration.patient_bbox_normalized
                ),
                0,
                "patient",
                None,
            )
        ]
        people = observer.get("person_targets", ())
        if not isinstance(people, Sequence) or isinstance(people, (str, bytes)):
            raise ContractError("person_targets must be a sequence")
        for person in people:
            if not isinstance(person, Mapping):
                raise ContractError("person target records must be mappings")
            track_id = person.get("track_id")
            if not isinstance(track_id, str) or not track_id:
                raise ContractError("person target requires a non-empty track_id")
            if track_id == sample.track_id:
                continue
            candidates.append(
                (
                    _box_angular_distance(
                        origin,
                        sample.yaw_degrees,
                        _bbox(person.get("bbox_normalized"), "person bbox_normalized"),
                    ),
                    1,
                    "person",
                    track_id,
                )
            )
        distance, _, label, track_id = min(
            candidates, key=lambda item: (item[0], item[1], item[3] or "")
        )
        if distance > self.threshold_degrees:
            return Assignment("other", distance, None)
        return Assignment(label, distance, track_id)


class FixedCausalRollingMode:
    """Causal mode-of-five, reset at segment/camera/track boundaries."""

    procedure_id = "causal-rolling-mode-v1.0.0"
    window_size = ROLLING_MODE_WINDOW

    def smooth_samples(
        self, samples: Sequence[AttentionInput], labels: Sequence[str]
    ) -> Sequence[str]:
        if len(samples) != len(labels):
            raise ContractError("attention samples and labels must have equal length")
        output = list(labels)
        history_by_track: dict[tuple[str, str, str], list[tuple[int, str]]] = {}
        for index, (sample, label) in enumerate(zip(samples, labels)):
            observer = sample.observer_record
            if not isinstance(observer, Mapping):
                raise ContractError("attention smoothing requires an observer record")
            grid_index = observer.get("grid_index")
            segment_id = observer.get("transcript_segment_id")
            if not isinstance(grid_index, int) or not isinstance(segment_id, str):
                raise ContractError(
                    "attention smoothing requires integer grid_index and transcript_segment_id"
                )
            key = (sample.camera_id, sample.track_id, segment_id)
            history = history_by_track.setdefault(key, [])
            # A frame the exact-frame gate excludes must not decide a delivered label.
            # Smoothing once ran over every candidate, so a delivered frame's mode could
            # be carried by neighbours the method says do not propagate. Excluded frames
            # contribute nothing and leave a grid_index gap, which the contiguity check
            # below turns into a history reset -- the same boundary rule already applied
            # at segment and track edges.
            if observer.get("exact_frame_gate") != EXACT_GATE_PASSED:
                continue
            if history and grid_index != history[-1][0] + 1:
                history.clear()
            history.append((grid_index, label))
            del history[:-self.window_size]
            counts = Counter(item[1] for item in history)
            maximum = max(counts.values())
            tied = {candidate for candidate, count in counts.items() if count == maximum}
            output[index] = next(
                prior for _, prior in reversed(history) if prior in tied
            )
        return output

    def smooth(self, labels: Sequence[str]) -> Sequence[str]:
        history: list[str] = []
        output = []
        for label in labels:
            history.append(label)
            del history[:-self.window_size]
            counts = Counter(history)
            maximum = max(counts.values())
            tied = {candidate for candidate, count in counts.items() if count == maximum}
            output.append(next(item for item in reversed(history) if item in tied))
        return output


class ReferenceCalibratedAttention:
    """Validate, classify, smooth, and serialize one camera's samples."""

    def __init__(
        self,
        calibration: PatientZoneCalibration,
        assignment_procedure: TargetAssignmentProcedure | None = None,
        *,
        smoothing_procedure: RollingModeProcedure | None = None,
        paper_mode: bool = True,
    ) -> None:
        assignment_procedure = assignment_procedure or FixedTargetAssignment()
        smoothing_procedure = smoothing_procedure or FixedCausalRollingMode()
        if paper_mode and type(assignment_procedure) is not FixedTargetAssignment:
            raise ContractError("paper mode requires the fixed target-assignment policy")
        if paper_mode and type(smoothing_procedure) is not FixedCausalRollingMode:
            raise ContractError("paper mode requires the fixed causal rolling-mode policy")
        if assignment_procedure.threshold_degrees != ATTENTION_THRESHOLD_DEGREES:
            raise ContractError("attention assignment threshold must be exactly 35 degrees")
        if smoothing_procedure.window_size != ROLLING_MODE_WINDOW:
            raise ContractError("attention rolling mode window must be exactly 5")
        if not assignment_procedure.procedure_id or not smoothing_procedure.procedure_id:
            raise ContractError("attention procedures require non-empty procedure IDs")
        self.calibration = calibration
        self.assignment_procedure = assignment_procedure
        self.smoothing_procedure = smoothing_procedure

    def classify(self, samples: Iterable[AttentionInput]) -> list[dict[str, Any]]:
        materialized = list(samples)
        assignments = [
            self.assignment_procedure.assign(sample, self.calibration)
            for sample in materialized
        ]
        for assignment in assignments:
            if assignment.label not in ATTENTION_LABELS:
                raise ContractError(f"assignment returned unsupported label: {assignment.label}")
            if assignment.angular_distance_degrees is not None and not (
                0 <= assignment.angular_distance_degrees <= 180
            ):
                raise ContractError("angular distance must be in [0, 180]")
            if assignment.label != "person" and assignment.target_track_id is not None:
                raise ContractError("particular target track is provenance only for person")
        raw_labels = [item.label for item in assignments]
        if isinstance(self.smoothing_procedure, FixedCausalRollingMode):
            smoothed = list(
                self.smoothing_procedure.smooth_samples(materialized, raw_labels)
            )
        else:
            smoothed = list(self.smoothing_procedure.smooth(raw_labels))
        if len(smoothed) != len(assignments) or set(smoothed) - set(ATTENTION_LABELS):
            raise ContractError("attention smoothing procedure returned invalid labels")
        return [
            {
                "evidence_id": sample.evidence_id,
                "camera_id": sample.camera_id,
                "track_id": sample.track_id,
                "aligned_timestamp_seconds": sample.aligned_timestamp_seconds,
                "yaw_degrees": sample.yaw_degrees,
                "raw_label": assignment.label,
                "label": label,
                "angular_distance_degrees": assignment.angular_distance_degrees,
                "target_track_id": assignment.target_track_id,
                "calibration_version": self.calibration.schema_version,
                "calibration_session_id": self.calibration.session_id,
                "calibration_camera_id": self.calibration.camera_id,
                "assignment_procedure_id": self.assignment_procedure.procedure_id,
                "smoothing_procedure_id": self.smoothing_procedure.procedure_id,
                "threshold_degrees": ATTENTION_THRESHOLD_DEGREES,
                "rolling_mode_window": ROLLING_MODE_WINDOW,
                # The gate is decided per candidate upstream; it has to travel with the
                # record or the window assembler has nothing to filter on.
                "exact_frame_gate": sample.observer_record.get("exact_frame_gate"),
                "exact_frame_asd_score": sample.observer_record.get("exact_frame_asd_score"),
            }
            for sample, assignment, label in zip(materialized, assignments, smoothed)
        ]


def _selected_segments(
    best_angles: Mapping[str, Any], camera_ids: set[str] | None = None
) -> list[Mapping[str, Any]]:
    segments = best_angles.get("segments")
    if not isinstance(segments, Sequence) or isinstance(segments, (str, bytes)):
        return []
    selected = []
    for segment in segments:
        if not isinstance(segment, Mapping):
            continue
        camera_id = segment.get("selected_camera_id")
        track_id = segment.get("selected_track_id")
        if not isinstance(camera_id, str) or not isinstance(track_id, str):
            continue
        if camera_ids is None or camera_id in camera_ids:
            selected.append(segment)
    return selected


def _identity_has_selection(identity_map: Mapping[str, Any], segment: Mapping[str, Any]) -> bool:
    speaker_id = segment.get("speaker_id")
    camera_id = segment.get("selected_camera_id")
    track_id = segment.get("selected_track_id")
    speakers = identity_map.get("speakers")
    if not isinstance(speakers, Sequence) or isinstance(speakers, (str, bytes)):
        return False
    speaker = next(
        (
            item
            for item in speakers
            if isinstance(item, Mapping) and item.get("speaker_id") == speaker_id
        ),
        None,
    )
    if speaker is None:
        return False
    candidates = speaker.get("camera_candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        return False
    # A speaker links to several track fragments per camera, and a segment selects the
    # fragment that overlaps it -- which is often not the camera-level summary track.
    # Matching only the summary rejected every segment grounded in any other fragment.
    for item in candidates:
        if not isinstance(item, Mapping) or item.get("camera_id") != camera_id:
            continue
        if item.get("track_id") == track_id and item.get("status") in {"linked", "weak"}:
            return True
        for fragment in item.get("linked_fragments") or ():
            if (
                isinstance(fragment, Mapping)
                and fragment.get("track_id") == track_id
                and fragment.get("status") in {"linked", "weak"}
            ):
                return True
    return False


def preflight_eligibility(
    session_id: str,
    *,
    calibrations: CalibrationStore,
    best_angles: Mapping[str, Any] | None,
    identity_map: Mapping[str, Any] | None,
    head_pose_by_camera: Mapping[str, Mapping[str, Any] | None],
    camera_ids: set[str] | None = None,
) -> EligibilityReport:
    """Return one deterministic, typed session eligibility result.

    Pose availability is deliberately not a session-level gate. It is evaluated
    independently for every selected segment during sample construction.
    """

    if best_angles is None or identity_map is None:
        return EligibilityReport(
            session_id, EligibilityStatus.MISSING_IDENTITY, (), detail="identity or best-angle artifact is absent"
        )
    if best_angles.get("session_id") != session_id or identity_map.get("session_id") != session_id:
        return EligibilityReport(
            session_id, EligibilityStatus.MISSING_IDENTITY, (), detail="identity artifact session mismatch"
        )
    segments = _selected_segments(best_angles, camera_ids)
    if not segments or any(not _identity_has_selection(identity_map, row) for row in segments):
        return EligibilityReport(
            session_id,
            EligibilityStatus.MISSING_IDENTITY,
            tuple(sorted({str(row.get("selected_camera_id")) for row in segments})),
            detail="no usable identity-backed segment selection",
        )
    required = tuple(sorted({str(row["selected_camera_id"]) for row in segments}))
    missing_calibration = tuple(
        camera_id for camera_id in required if not calibrations.has(session_id, camera_id)
    )
    if missing_calibration:
        return EligibilityReport(
            session_id,
            EligibilityStatus.MISSING_CALIBRATION,
            required,
            missing_calibration,
            "one or more selected cameras have no authored patient zone",
        )
    # Kept in the signature because callers load all preflight inputs together.
    # Sparse or absent pose is a segment measurement, never a session failure.
    _ = head_pose_by_camera
    return EligibilityReport(session_id, EligibilityStatus.ELIGIBLE, required)


def _track_poses(track_record: object) -> list[Mapping[str, Any]]:
    if isinstance(track_record, Sequence) and not isinstance(track_record, (str, bytes)):
        return [item for item in track_record if isinstance(item, Mapping)]
    if isinstance(track_record, Mapping):
        poses = track_record.get("poses", ())
        if isinstance(poses, Sequence) and not isinstance(poses, (str, bytes)):
            return [item for item in poses if isinstance(item, Mapping)]
    return []


def _frame_index(pose: Mapping[str, Any]) -> int:
    value = pose.get("frame_index", pose.get("frame"))
    if not isinstance(value, int) or value < 0:
        raise ContractError("head-pose samples require a non-negative frame index")
    return value


def _timestamp(pose: Mapping[str, Any], metadata: Mapping[str, Any]) -> float:
    if "aligned_timestamp_seconds" in pose:
        value = float(pose["aligned_timestamp_seconds"])
    else:
        fps = metadata.get("fps")
        if not isinstance(fps, (int, float)) or not isfinite(float(fps)) or float(fps) <= 0:
            raise ContractError("frame-indexed head pose requires explicit finite positive fps")
        value = _frame_index(pose) / float(fps)
    if not isfinite(value) or value < 0:
        raise ContractError("head-pose timestamp must be finite and non-negative")
    return value


def _normalized_pose_bbox(
    pose: Mapping[str, Any], metadata: Mapping[str, Any]
) -> tuple[float, float, float, float]:
    if "bbox_normalized" in pose:
        return _bbox(pose["bbox_normalized"], "head-pose bbox_normalized")
    raw = pose.get("bbox")
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)) and len(raw) == 4:
        raw_values = tuple(float(item) for item in raw)
        if all(0 <= item <= 1 for item in raw_values):
            return _bbox(raw_values, "head-pose bbox")
    resolution = metadata.get("resolution", metadata.get("frame_size"))
    if (
        not isinstance(raw, Sequence)
        or isinstance(raw, (str, bytes))
        or len(raw) != 4
        or not isinstance(resolution, Sequence)
        or isinstance(resolution, (str, bytes))
        or len(resolution) != 2
    ):
        raise ContractError(
            "pixel head-pose bbox requires metadata.resolution [width, height]"
        )
    width, height = float(resolution[0]), float(resolution[1])
    if not isfinite(width) or not isfinite(height) or width <= 0 or height <= 0:
        raise ContractError("head-pose resolution must be finite and positive")
    return _bbox(
        [float(raw[0]) / width, float(raw[1]) / height,
         float(raw[2]) / width, float(raw[3]) / height],
        "normalized head-pose bbox",
    )


# Reasons poses were rejected, so a systematic producer mismatch is distinguishable
# from genuinely sparse data. Reported alongside the segment funnel.
_POSE_REJECTIONS: Counter = Counter()



# The declared method propagates a visual signal only from frames whose SELECTED-view
# active-speaker score is strictly positive. Stage 9 previously received no ASD at all and
# emitted every usable pose inside the selected segment, so 364 of 1,666 attention records
# on session_001 either violated that gate or could not be joined to it.
#
# Both populations are kept. The exact-frame-gated stream is canonical and is the only one
# that reaches events, windows, prompts or citations; the ungated candidate stream is
# retained as a named diagnostic so the coverage the gate costs is a measured result rather
# than a silent preprocessing loss.
EXACT_GATE_PASSED = "exact_frame_asd_positive"
EXACT_GATE_NON_POSITIVE = "exact_frame_asd_not_positive"
EXACT_GATE_MISSING = "exact_frame_asd_missing"


def build_asd_score_index(asd_by_camera):
    """Map (camera_id, track_id, frame_index) to that frame's ASD score.

    Keyed on frame index rather than timestamp: the gate is defined per frame, and a
    timestamp comparison would admit a neighbouring frame whose score differs.
    """
    index = {}
    for camera_id, artifact in (asd_by_camera or {}).items():
        if not isinstance(artifact, Mapping):
            continue
        for track in artifact.get("tracks", ()):
            if not isinstance(track, Mapping):
                continue
            track_id = track.get("track_id")
            for sample in track.get("samples", ()):
                if not isinstance(sample, Mapping):
                    continue
                frame_index = sample.get("frame_index")
                score = sample.get("score")
                if frame_index is None or score is None:
                    continue
                index[(camera_id, track_id, int(frame_index))] = float(score)
    return index


def exact_frame_gate(asd_index, camera_id, track_id, frame_index):
    """Gate outcome for one attention frame, distinguishing absent from non-positive.

    A missing join fails closed for the canonical stream but is counted apart from a
    finite non-positive score: "we could not check" and "we checked and it failed" are
    different facts about the harness.
    """
    score = asd_index.get((camera_id, track_id, int(frame_index)))
    if score is None:
        return EXACT_GATE_MISSING, None
    if score > 0.0:
        return EXACT_GATE_PASSED, score
    return EXACT_GATE_NON_POSITIVE, score


def _usable_pose(
    pose: Mapping[str, Any], metadata: Mapping[str, Any]
) -> tuple[int, float, float, tuple[float, float, float, float]] | None:
    try:
        frame_index = _frame_index(pose)
        timestamp = _timestamp(pose, metadata)
        yaw = float(pose["yaw"])
        bbox = _normalized_pose_bbox(pose, metadata)
    except (ContractError, KeyError, TypeError, ValueError, OverflowError) as error:
        # A malformed individual pose is data; a pose the contract cannot read at all is
        # a producer mismatch. Both landed here as a bare None, so when head pose stopped
        # recording its frame size every pose in the session became silently unusable and
        # the funnel could only say "no usable pose" -- true, but not why.
        _POSE_REJECTIONS[type(error).__name__ + ": " + str(error)[:80]] += 1
        return None
    if not isfinite(yaw):
        return None
    return frame_index, timestamp, yaw, bbox


def _build_selected_camera_samples_with_eligibility(
    best_angles: Mapping[str, Any],
    head_pose_by_camera: Mapping[str, Mapping[str, Any] | None],
    *,
    camera_ids: set[str] | None = None,
    asd_index: Mapping | None = None,
) -> tuple[dict[str, list[AttentionInput]], tuple[SegmentEligibility, ...]]:
    """Build real samples and retain one eligibility result per selected segment."""

    output: dict[str, list[AttentionInput]] = {}
    eligibility: list[SegmentEligibility] = []
    for segment in _selected_segments(best_angles, camera_ids):
        camera_id = str(segment["selected_camera_id"])
        track_id = str(segment["selected_track_id"])
        segment_id = str(segment["transcript_segment_id"])
        artifact = head_pose_by_camera.get(camera_id)
        if not isinstance(artifact, Mapping):
            eligibility.append(
                SegmentEligibility(
                    segment_id,
                    camera_id,
                    track_id,
                    SegmentEligibilityStatus.INELIGIBLE,
                    SegmentIneligibilityReason.MISSING_POSE_ARTIFACT,
                    0,
                )
            )
            continue
        metadata = artifact.get("metadata", {})
        tracks = artifact.get("tracks")
        if not isinstance(metadata, Mapping) or not isinstance(tracks, Mapping):
            eligibility.append(
                SegmentEligibility(
                    segment_id,
                    camera_id,
                    track_id,
                    SegmentEligibilityStatus.INELIGIBLE,
                    SegmentIneligibilityReason.MALFORMED_POSE_ARTIFACT,
                    0,
                )
            )
            continue
        selected_track_poses = _track_poses(tracks.get(track_id))
        if not selected_track_poses:
            eligibility.append(
                SegmentEligibility(
                    segment_id,
                    camera_id,
                    track_id,
                    SegmentEligibilityStatus.INELIGIBLE,
                    SegmentIneligibilityReason.MISSING_SELECTED_TRACK_POSE,
                    0,
                )
            )
            continue
        usable_by_track: dict[
            str, dict[int, tuple[Mapping[str, Any], float, float, tuple[float, float, float, float]]]
        ] = {}
        for other_id, record in tracks.items():
            usable = {}
            for pose in _track_poses(record):
                parsed = _usable_pose(pose, metadata)
                if parsed is None:
                    continue
                frame_index, timestamp, yaw, bbox = parsed
                usable[frame_index] = (pose, timestamp, yaw, bbox)
            usable_by_track[str(other_id)] = usable
        start, end = float(segment["start_seconds"]), float(segment["end_seconds"])
        emitted_index = 0
        for frame_index, (_, timestamp, yaw, bbox) in sorted(
            usable_by_track.get(track_id, {}).items()
        ):
            if not start <= timestamp < end:
                continue
            gate_status, gate_score = exact_frame_gate(
                asd_index or {}, camera_id, track_id, frame_index
            )
            people = []
            for other_id in sorted(usable_by_track):
                if other_id == track_id:
                    continue
                other_pose = usable_by_track[other_id].get(frame_index)
                if other_pose is not None:
                    people.append(
                        {
                            "track_id": other_id,
                            "bbox_normalized": other_pose[3],
                        }
                    )
            sample = AttentionInput(
                # Hyphen-separated, matching every other evidence id in the pipeline
                # (asd-cam1-3-90, coverage-window-0000, transcript segment ids).
                # Colons are reserved for canonical track ids and are rejected by
                # the evidence_id pattern, so a colon form fails schema validation
                # the moment any attention record actually reaches a window.
                evidence_id=f"attention-{segment_id}-{camera_id}-{frame_index}",
                camera_id=camera_id,
                track_id=track_id,
                aligned_timestamp_seconds=timestamp,
                yaw_degrees=yaw,
                observer_record={
                    "bbox_normalized": bbox,
                    "person_targets": people,
                    "grid_index": emitted_index,
                    "transcript_segment_id": segment_id,
                    "speaker_id": segment.get("speaker_id"),
                    "frame_index": frame_index,
                    # Recorded on every candidate, so the gate's cost is measurable rather
                    # than only its result being visible.
                    "exact_frame_gate": gate_status,
                    "exact_frame_asd_score": gate_score,
                },
            )
            output.setdefault(camera_id, []).append(sample)
            emitted_index += 1
        if emitted_index:
            eligibility.append(
                SegmentEligibility(
                    segment_id,
                    camera_id,
                    track_id,
                    SegmentEligibilityStatus.CLASSIFIED,
                    None,
                    emitted_index,
                )
            )
        else:
            eligibility.append(
                SegmentEligibility(
                    segment_id,
                    camera_id,
                    track_id,
                    SegmentEligibilityStatus.INELIGIBLE,
                    SegmentIneligibilityReason.NO_USABLE_POSE_IN_SEGMENT,
                    0,
                )
            )
    return output, tuple(eligibility)


def build_selected_camera_samples(
    best_angles: Mapping[str, Any],
    head_pose_by_camera: Mapping[str, Mapping[str, Any] | None],
    *,
    camera_ids: set[str] | None = None,
) -> dict[str, list[AttentionInput]]:
    """Build inputs only where the selected segment has usable pose."""

    samples, _ = _build_selected_camera_samples_with_eligibility(
        best_angles, head_pose_by_camera, camera_ids=camera_ids
    )
    return samples


def classify_selected_segments_with_diagnostics(
    session_id: str,
    *,
    calibrations: CalibrationStore,
    best_angles: Mapping[str, Any],
    head_pose_by_camera: Mapping[str, Mapping[str, Any] | None],
    camera_ids: set[str] | None = None,
    asd_index: Mapping | None = None,
) -> AttentionClassificationResult:
    required_cameras = sorted(
        {
            str(segment["selected_camera_id"])
            for segment in _selected_segments(best_angles, camera_ids)
        }
    )
    # Resolve every selected-camera calibration before reading pose geometry. This
    # makes missing authored calibration the first and unambiguous hard failure.
    calibration_by_camera = {
        camera_id: calibrations.get(session_id, camera_id)
        for camera_id in required_cameras
    }
    samples_by_camera, segment_eligibility = _build_selected_camera_samples_with_eligibility(
        best_angles, head_pose_by_camera, camera_ids=camera_ids, asd_index=asd_index
    )
    records = []
    for camera_id in sorted(samples_by_camera):
        records.extend(
            ReferenceCalibratedAttention(
                calibration_by_camera[camera_id], paper_mode=True
            ).classify(
                samples_by_camera[camera_id]
            )
        )
    sorted_records = sorted(
        records,
        key=lambda item: (
            item["aligned_timestamp_seconds"], item["camera_id"], item["track_id"], item["evidence_id"]
        ),
    )
    return AttentionClassificationResult(tuple(sorted_records), segment_eligibility)


def classify_selected_segments(
    session_id: str,
    *,
    calibrations: CalibrationStore,
    best_angles: Mapping[str, Any],
    head_pose_by_camera: Mapping[str, Mapping[str, Any] | None],
    camera_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Compatibility wrapper returning classified records without diagnostics."""

    return list(
        classify_selected_segments_with_diagnostics(
            session_id,
            calibrations=calibrations,
            best_angles=best_angles,
            head_pose_by_camera=head_pose_by_camera,
            camera_ids=camera_ids,
        ).records
    )


def _gate_comparison(records) -> dict:
    """Candidate versus exact-frame-gated attention, counted by outcome."""
    counts = Counter()
    for record in records:
        counts[record.get("exact_frame_gate") or "unknown"] += 1
    candidate = sum(counts.values())
    delivered = counts.get(EXACT_GATE_PASSED, 0)
    non_positive = counts.get(EXACT_GATE_NON_POSITIVE, 0)
    missing = counts.get(EXACT_GATE_MISSING, 0)
    # Every candidate must land in exactly one outcome. This first shipped counting an
    # attribute the records do not have, so all 1,666 fell into "unknown" while the three
    # outcome counts read zero and the gate silently admitted everything downstream.
    if delivered + non_positive + missing != candidate:
        raise ContractError(
            "exact-frame gate accounting does not partition its candidates: "
            f"{delivered}+{non_positive}+{missing} != {candidate} "
            f"(unlabelled: {counts.get('unknown', 0)})"
        )
    return {
        "policy_id": "ATTENTION-EXACT-FRAME-ASD-GATE-001",
        "rule": "selected-view ASD score strictly greater than 0.0 at the same frame index",
        "candidate_record_count": candidate,
        "delivered_record_count": delivered,
        "non_positive_record_count": non_positive,
        "missing_join_record_count": missing,
        "admission_fraction": (delivered / candidate) if candidate else None,
        "denominator_statement": (
            "candidate attention records are every valid classification inside the "
            "Stage-3 selected segment; only the gated subset is delivered downstream"
        ),
    }


def build_attention_artifact(
    session_id: str,
    *,
    calibrations: CalibrationStore,
    best_angles: Mapping[str, Any] | None,
    identity_map: Mapping[str, Any] | None,
    head_pose_by_camera: Mapping[str, Mapping[str, Any] | None],
    camera_ids: set[str] | None = None,
    asd_index: Mapping | None = None,
) -> dict[str, Any]:
    """Build a session artifact with hard gates and segment-level pose coverage."""

    report = preflight_eligibility(
        session_id,
        calibrations=calibrations,
        best_angles=best_angles,
        identity_map=identity_map,
        head_pose_by_camera=head_pose_by_camera,
        camera_ids=camera_ids,
    )
    if report.status is not EligibilityStatus.ELIGIBLE:
        _raise_ineligible(report)
    assert best_angles is not None
    result = classify_selected_segments_with_diagnostics(
        session_id,
        calibrations=calibrations,
        best_angles=best_angles,
        head_pose_by_camera=head_pose_by_camera,
        asd_index=asd_index,
        camera_ids=camera_ids,
    )
    tracks: dict[str, dict[str, Any]] = {}
    for record in result.records:
        key = f"{record['camera_id']}:{record['track_id']}"
        track = tracks.setdefault(
            key,
            {"camera_id": record["camera_id"], "track_id": record["track_id"], "poses": []},
        )
        track["poses"].append(
            {
                "timestamp": record["aligned_timestamp_seconds"],
                "gaze_target": record["label"],
                **record,
            }
        )
    for track in tracks.values():
        counts = Counter(pose["gaze_target"] for pose in track["poses"])
        total = len(track["poses"])
        track["summary"] = {
            label: counts[label] / total for label in ATTENTION_LABELS
        }
    artifact = {
        "schema_version": "2.1.0",
        "session_id": session_id,
        "attention_targets": list(ATTENTION_LABELS),
        "eligibility": report.to_dict(),
        "capture_at_run": result.capture_at_run(),
        "segment_eligibility": [item.to_dict() for item in result.segment_eligibility],
        # The gate's cost, reported rather than absorbed. "Candidate" is every valid
        # attention classification inside the Stage-3 selected segment; "delivered" is the
        # subset the exact-frame ASD gate admits. The difference is the visual coverage the
        # declared method discards, which is a result about the harness, not preprocessing.
        "exact_frame_gate": _gate_comparison(result.records),
        "tracks": tracks,
    }
    _validate_attention_records(artifact["tracks"])
    return artifact


def _validate_attention_records(tracks: Mapping[str, Any]) -> None:
    """Hold emitted records to the declared attention contract.

    Nothing validated this artifact, so the contract could say one thing while the producer
    emitted another -- which is how the gate verdict came to be computed and then dropped
    before serialization without any check objecting.
    """
    from jsonschema import Draft202012Validator

    from scripts.core.schema import load_schema

    schema = load_schema("visual_records")
    validator = Draft202012Validator(
        {**schema["$defs"]["attention"], "$defs": schema["$defs"]}
    )
    for track in tracks.values():
        for pose in track.get("poses") or ():
            errors = sorted(validator.iter_errors(pose), key=lambda e: e.path)
            if errors:
                raise ContractError(
                    "attention record violates the declared contract at "
                    f"{list(errors[0].path)}: {errors[0].message}"
                )


def _load_optional(path: Path) -> Mapping[str, Any] | None:
    if not path.is_file():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ContractError(f"JSON artifact root must be a mapping: {path}")
    return document


def _parse_camera_paths(values: Sequence[str], session_id: str) -> dict[str, Path]:
    from scripts.utils.session_paths import raw_dir

    paths = {
        camera_id: raw_dir(session_id) / f"head_pose_{camera_id}.json"
        for camera_id in ("cam1", "cam2", "cam3")
    }
    for value in values:
        camera_id, separator, raw_path = value.partition("=")
        if not separator or not camera_id or not raw_path:
            raise ContractError("--head-pose must be CAMERA_ID=PATH")
        paths[camera_id] = Path(raw_path)
    return paths


def _raise_ineligible(report: EligibilityReport) -> None:
    if report.status is EligibilityStatus.MISSING_CALIBRATION:
        raise MissingCalibrationError(report.session_id, report.missing_camera_ids[0])
    raise MissingIdentityError(f"{MissingIdentityError.code}: {report.detail}")


def main() -> None:
    from scripts.utils.session_paths import processed_dir, raw_dir

    parser = argparse.ArgumentParser(
        description="Classify patient/person/other attention on selected cameras"
    )
    parser.add_argument("--session-id", required=True)
    parser.add_argument(
        "--camera",
        action="append",
        choices=("cam1", "cam2", "cam3"),
        help="Explicitly process selected segments for this camera; repeat as needed",
    )
    parser.add_argument("--calibration", type=Path, default=CALIBRATION_PATH)
    parser.add_argument("--best-angles", type=Path)
    parser.add_argument("--asd", type=Path)
    parser.add_argument("--identity-map", type=Path)
    parser.add_argument(
        "--head-pose", action="append", default=[], metavar="CAMERA_ID=PATH"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()

    best_path = args.best_angles or processed_dir(args.session_id) / "best_angles.json"
    identity_path = args.identity_map or processed_dir(args.session_id) / "identity_map.json"
    head_paths = _parse_camera_paths(args.head_pose, args.session_id)
    calibrations = CalibrationStore.load(args.calibration)
    best_angles = _load_optional(best_path)
    identity_map = _load_optional(identity_path)
    head_pose = {camera: _load_optional(path) for camera, path in head_paths.items()}
    selected_cameras = set(args.camera) if args.camera else None
    if args.preflight_only:
        report = preflight_eligibility(
            args.session_id,
            calibrations=calibrations,
            best_angles=best_angles,
            identity_map=identity_map,
            head_pose_by_camera=head_pose,
            camera_ids=selected_cameras,
        )
        print(json.dumps(report.to_dict(), sort_keys=True))
        return
    # The exact-frame gate needs the ASD artifact this stage never used to receive.
    # Absent it the canonical stream would be empty rather than ungated, so it is required
    # rather than optional: a silently ungated run is what this change exists to end.
    asd_path = args.asd or raw_dir(args.session_id) / "asd_tracks.json"
    asd_document = _load_optional(asd_path)
    if not isinstance(asd_document, Mapping):
        raise ContractError(
            f"attention classification requires the ASD artifact for the exact-frame gate: {asd_path}"
        )
    asd_index = build_asd_score_index(asd_document)

    output = build_attention_artifact(
        args.session_id,
        calibrations=calibrations,
        best_angles=best_angles,
        identity_map=identity_map,
        head_pose_by_camera=head_pose,
        camera_ids=selected_cameras,
        asd_index=asd_index,
    )
    output_path = args.output or raw_dir(args.session_id) / "gaze_tracks.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(output_path)


__all__ = [
    "ATTENTION_LABELS",
    "ATTENTION_THRESHOLD_DEGREES",
    "ROLLING_MODE_WINDOW",
    "Assignment",
    "AttentionClassificationResult",
    "AttentionEligibilityError",
    "AttentionInput",
    "EligibilityReport",
    "EligibilityStatus",
    "FixedCausalRollingMode",
    "FixedTargetAssignment",
    "MissingIdentityError",
    "ReferenceCalibratedAttention",
    "RollingModeProcedure",
    "SegmentEligibility",
    "SegmentEligibilityStatus",
    "SegmentIneligibilityReason",
    "TargetAssignmentProcedure",
    "build_attention_artifact",
    "build_selected_camera_samples",
    "classify_selected_segments",
    "classify_selected_segments_with_diagnostics",
    "preflight_eligibility",
]


if __name__ == "__main__":
    main()
