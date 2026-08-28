#!/usr/bin/env python3
"""Produce auditable per-session paper metrics from current-run artifacts.

Only quantities retained for the paper are emitted.  Every result is count-first and
contains immutable source-artifact records copied from the run manifest.  No historical
paper value is an input to this producer.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from math import ceil, floor, isfinite
from pathlib import Path
import pickle
import sys
from typing import Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.metrics.definitions import (
    MEASURED,
    ATTENTION_TARGETS,
    HARNESS_FUNNEL_SIGNALS,
    HarnessDeliveryFunnel,
    TABLE3_CAMERAS,
    Table3Coverage,
    UnavailableMetric,
    compute_attention_distribution,
    compute_cross_modal_share,
    compute_evidence_distribution,
    compute_example_silence,
    compute_harness_delivery_funnel,
    compute_m_only,
    compute_monly_visual_share,
    compute_provenance_integrity,
    compute_speaker_link_coverage,
    compute_symmetric_overlap,
    compute_table3_coverage,
)
from scripts.core.errors import MetricDefinitionUnresolvedError
from scripts.core.records import LIGHT_ASD_ANALYSIS_FPS
from scripts.utils.session_paths import metrics_dir, prerequisites_dir, processed_dir, raw_dir


PRODUCER_VERSION = "3.1.0"
MEASUREMENT = "capture_at_run"
S3FD_CONFIDENCE_THRESHOLD = 0.9
S3FD_CONFIDENCE_OPERATOR = ">"
SOURCE_KEYS = (
    "session_manifest",
    "asd",
    "faces_cam1",
    "faces_cam2",
    "faces_cam3",
    "head_pose_cam1",
    "head_pose_cam2",
    "head_pose_cam3",
    "best_angles",
    "identity_map",
    "diarized_transcript",
    "gaze_tracks",
    "focal_runs",
    "multimodal_windows",
)
QUANTITY_SOURCES = {
    "table3.asd.best_cam": ("session_manifest", "asd"),
    "table3.asd.union": ("session_manifest", "asd"),
    "table3.asd.selected": ("session_manifest", "asd", "best_angles"),
    "table3.face.best_cam": (
        "session_manifest", "faces_cam1", "faces_cam2", "faces_cam3",
    ),
    "table3.face.union": (
        "session_manifest", "faces_cam1", "faces_cam2", "faces_cam3",
    ),
    "table3.face.selected": (
        "session_manifest", "faces_cam1", "faces_cam2", "faces_cam3", "asd", "best_angles",
    ),
    "table3.head_pose.best_cam": (
        "session_manifest", "head_pose_cam1", "head_pose_cam2", "head_pose_cam3",
    ),
    "table3.head_pose.union": (
        "session_manifest", "head_pose_cam1", "head_pose_cam2", "head_pose_cam3",
    ),
    "table3.head_pose.selected": (
        "session_manifest", "head_pose_cam1", "head_pose_cam2", "head_pose_cam3",
        "asd", "best_angles",
    ),
    "speaker_identity_link": ("diarized_transcript", "identity_map"),
    "tm_overlap": ("focal_runs",),
    "m_only_count": ("focal_runs",),
    "m_only_cross_modal_evidence": ("focal_runs",),
    "aggregate_cross_modal_evidence": ("focal_runs",),
    "provenance_integrity": ("focal_runs", "multimodal_windows"),
    "evidence_distribution": ("focal_runs",),
    "attention_distribution": ("session_manifest", "multimodal_windows"),
    "example_silence": ("session_manifest", "diarized_transcript"),
    "moment_counts": ("focal_runs",),
    "category_diversity": ("focal_runs",),
    "directional_overlap": ("focal_runs",),
    "camera_selection_distribution": ("best_angles",),
    "transcript_context_coverage": ("session_manifest", "multimodal_windows"),
    "scene_context_coverage": ("session_manifest", "multimodal_windows"),
    "attention_context_coverage": ("session_manifest", "multimodal_windows"),
    "wilcoxon_signed_rank": ("focal_runs",),
    "session_count": ("session_manifest",),
    "scenario_distribution": ("session_manifest",),
    "session_durations": ("session_manifest",),
    "participant_counts": ("session_manifest",),
    "table3_ratio": ("session_manifest", "asd", "best_angles"),
    "harness_delivery_failure_funnel": (
        "session_manifest", "diarized_transcript", "identity_map", "best_angles",
        "faces_cam1", "faces_cam2", "faces_cam3", "asd",
        "head_pose_cam1", "head_pose_cam2", "head_pose_cam3",
        "gaze_tracks", "multimodal_windows",
    ),
}

SESSION_ONLY_QUANTITY_IDS = (
    "evidence_distribution",
    "attention_distribution",
    "example_silence",
)
SESSION_QUANTITY_IDS = (*SESSION_ONLY_QUANTITY_IDS, "provenance_integrity")
TABLE3_GAP_QUANTITY_IDS = tuple(
    f"table3.{signal}.gap.{comparison}"
    for signal in ("asd", "face", "head_pose")
    for comparison in (
        "union_minus_best_cam",
        "selected_minus_best_cam",
        "union_minus_selected",
    )
)
COHORT_QUANTITY_IDS = tuple(
    quantity_id
    for quantity_id in QUANTITY_SOURCES
    if quantity_id not in SESSION_ONLY_QUANTITY_IDS
) + TABLE3_GAP_QUANTITY_IDS


def _load(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"required upstream artifact is missing: {path}")
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


class _OutOfSpanSample(ValueError):
    """A sample beyond the shared analysis grid; excluded, never fatal."""


def _bin_index(timestamp: object, duration_seconds: float, *, source: str) -> int:
    """Bin a timestamp onto the canonical one-second grid.

    The grid has ceil(duration) bins, so the terminal bin is partial and a sample landing
    inside it is in-session. Testing against the raw duration rejected such samples: with a
    manifest span of 1259.95 an ASD sample at 1259.96 falls in bin 1259, which exists and is
    counted in the denominator, yet the session failed at Stage 18.
    """
    value = float(timestamp)
    if not isfinite(value) or value < 0:
        raise ValueError(f"{source} timestamp {value!r} is not a usable time")
    index = floor(value)
    if index >= ceil(duration_seconds):
        # The span is the MINIMUM stream duration, so a longer stream genuinely carries
        # samples past it. Those lie outside the common analysis grid and are excluded,
        # not counted -- but excluding them must not kill the session: session_002 died at
        # Stage 18 over a sample 0.05s past a 1259.95s span, after three hours of work.
        raise _OutOfSpanSample(f"{source} timestamp {value!r} is past the session span")
    return index


def _tracks(artifact: Mapping[str, object], camera_id: str) -> Sequence[Mapping[str, object]]:
    tracks = artifact.get("tracks")
    if isinstance(tracks, Mapping):
        return tuple(
            {"track_id": track_id, **track}
            for track_id, track in tracks.items()
            if isinstance(track_id, str) and isinstance(track, Mapping)
        )
    if isinstance(tracks, Sequence) and not isinstance(tracks, (str, bytes)):
        if any(not isinstance(track, Mapping) for track in tracks):
            raise ValueError(f"{camera_id} tracks must contain mappings")
        return tuple(tracks)  # type: ignore[return-value]
    raise ValueError(f"{camera_id} artifact has no typed tracks collection")


def _asd_presence(
    asd_by_camera: Mapping[str, Mapping[str, object] | None],
    duration_seconds: float,
) -> dict[str, list[bool] | None]:
    denominator = ceil(duration_seconds)
    result: dict[str, list[bool] | None] = {}
    for camera_id in TABLE3_CAMERAS:
        artifact = asd_by_camera.get(camera_id)
        if artifact is None:
            result[camera_id] = None
            continue
        bins = [False] * denominator
        for track in _tracks(artifact, camera_id):
            samples = track.get("samples", ())
            if not isinstance(samples, Sequence) or isinstance(samples, (str, bytes)):
                raise ValueError(f"{camera_id} ASD samples must be a sequence")
            for sample in samples:
                if not isinstance(sample, Mapping):
                    raise ValueError(f"{camera_id} ASD samples must contain mappings")
                try:
                    bin_index = _bin_index(
                        sample.get("aligned_timestamp_seconds"), duration_seconds,
                        source=f"{camera_id} ASD",
                    )
                except _OutOfSpanSample:
                    continue
                score = sample.get("score")
                if score is None:
                    continue
                numeric_score = float(score)
                if not isfinite(numeric_score):
                    raise ValueError(f"{camera_id} ASD score must be finite")
                if numeric_score > 0.0:
                    bins[bin_index] = True
        result[camera_id] = bins
    return result


def _face_presence(
    faces_by_camera: Mapping[str, Sequence[object] | None],
    duration_seconds: float,
    *,
    excluded_out_of_session_detection_frame_ids: dict[str, list[int]] | None = None,
) -> dict[str, list[bool] | None]:
    """Project raw S3FD detections from Light-ASD's 25 Hz stream onto the canonical grid.

    The outer pickle list is indexed by the resampled analysis-frame index. Tracking output
    is deliberately not consulted: interpolation and short-track removal would change the
    raw detector ceiling this metric is intended to measure.
    """
    denominator = ceil(duration_seconds)
    if set(faces_by_camera) != set(TABLE3_CAMERAS):
        raise ValueError("face artifact map must contain exactly cam1, cam2, and cam3")
    result: dict[str, list[bool] | None] = {}
    for camera_id in TABLE3_CAMERAS:
        frames = faces_by_camera[camera_id]
        if frames is None:
            result[camera_id] = None
            continue
        if isinstance(frames, (str, bytes)):
            raise ValueError(f"{camera_id} faces.pckl must contain a frame sequence")
        bins = [False] * denominator
        for frame_index, detections in enumerate(frames):
            if not isinstance(detections, Sequence) or isinstance(detections, (str, bytes)):
                raise ValueError(f"{camera_id} faces.pckl frame {frame_index} must be a sequence")
            timestamp = frame_index / LIGHT_ASD_ANALYSIS_FPS
            if timestamp >= duration_seconds:
                if detections:
                    if excluded_out_of_session_detection_frame_ids is None:
                        raise ValueError(
                            f"{camera_id} S3FD detection frame {frame_index} is outside "
                            "the canonical grid"
                        )
                    excluded_out_of_session_detection_frame_ids.setdefault(
                        camera_id, []
                    ).append(frame_index)
                continue
            for detection in detections:
                if not isinstance(detection, Mapping):
                    raise ValueError(f"{camera_id} S3FD detections must be mappings")
                recorded_frame = detection.get("frame")
                if recorded_frame != frame_index:
                    raise ValueError(
                        f"{camera_id} S3FD frame index mismatch: outer={frame_index}, "
                        f"record={recorded_frame!r}"
                    )
                confidence = float(detection.get("conf", float("nan")))
                if not isfinite(confidence) or confidence <= S3FD_CONFIDENCE_THRESHOLD:
                    raise ValueError(
                        f"{camera_id} S3FD confidence does not satisfy "
                        f"{S3FD_CONFIDENCE_OPERATOR}{S3FD_CONFIDENCE_THRESHOLD}: {confidence!r}"
                    )
                bbox = detection.get("bbox")
                if not isinstance(bbox, Sequence) or isinstance(bbox, (str, bytes)) or len(bbox) != 4:
                    raise ValueError(f"{camera_id} S3FD detection requires an xyxy bounding box")
                if not all(isfinite(float(value)) for value in bbox):
                    raise ValueError(f"{camera_id} S3FD bounding box must be finite")
                bins[floor(timestamp)] = True
        result[camera_id] = bins
    return result


def _artifact_fps(artifact: Mapping[str, object], camera_id: str) -> float:
    metadata = artifact.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ValueError(
            f"{camera_id} head-pose records without aligned timestamps require decoded fps metadata"
        )
    value = metadata.get("decoded_fps", metadata.get("fps"))
    if value is None:
        raise ValueError(
            f"{camera_id} head-pose records without aligned timestamps require probed decoded fps"
        )
    fps = float(value)
    if not isfinite(fps) or fps <= 0:
        raise ValueError(f"{camera_id} decoded fps must be finite and positive")
    return fps


def _head_pose_presence_by_track(
    head_pose_by_camera: Mapping[str, Mapping[str, object] | None],
    duration_seconds: float,
) -> dict[str, dict[str, list[bool]]]:
    """Usable head-pose presence per (camera, track), for the Selected column.

    The camera-level map cannot answer whether the SELECTED speaker had a pose, only
    whether somebody on that camera did, so Selected head-pose coverage could be satisfied
    by another person standing in frame.
    """
    denominator = ceil(duration_seconds)
    result: dict[str, dict[str, list[bool]]] = {}
    for camera_id in TABLE3_CAMERAS:
        artifact = head_pose_by_camera.get(camera_id)
        if artifact is None:
            continue
        per_track: dict[str, list[bool]] = {}
        fps: float | None = None
        for track in _tracks(artifact, camera_id):
            track_id = track.get("track_id")
            if not isinstance(track_id, str) or not track_id:
                continue
            bins = per_track.setdefault(track_id, [False] * denominator)
            for pose in track.get("poses", ()) or ():
                if not isinstance(pose, Mapping):
                    continue
                angles = tuple(
                    float(pose.get(name, float("nan"))) for name in ("yaw", "pitch", "roll")
                )
                if not all(isfinite(angle) and -180 <= angle <= 180 for angle in angles):
                    continue
                timestamp = pose.get("aligned_timestamp_seconds")
                if timestamp is None:
                    frame = pose.get("frame_index", pose.get("frame"))
                    if not isinstance(frame, int) or frame < 0:
                        continue
                    fps = fps if fps is not None else _artifact_fps(artifact, camera_id)
                    timestamp = frame / fps
                try:
                    bins[_bin_index(timestamp, duration_seconds, source=f"{camera_id} head pose")] = True
                except _OutOfSpanSample:
                    continue
        result[camera_id] = per_track
    return result


def _head_pose_presence(
    head_pose_by_camera: Mapping[str, Mapping[str, object] | None],
    duration_seconds: float,
) -> dict[str, list[bool] | None]:
    denominator = ceil(duration_seconds)
    result: dict[str, list[bool] | None] = {}
    for camera_id in TABLE3_CAMERAS:
        artifact = head_pose_by_camera.get(camera_id)
        if artifact is None:
            result[camera_id] = None
            continue
        bins = [False] * denominator
        fps: float | None = None
        for track in _tracks(artifact, camera_id):
            poses = track.get("poses", ())
            if not isinstance(poses, Sequence) or isinstance(poses, (str, bytes)):
                raise ValueError(f"{camera_id} head-pose records must be a sequence")
            for pose in poses:
                if not isinstance(pose, Mapping):
                    raise ValueError(f"{camera_id} head-pose records must contain mappings")
                angles = tuple(float(pose.get(name, float("nan"))) for name in ("yaw", "pitch", "roll"))
                if not all(isfinite(angle) and -180 <= angle <= 180 for angle in angles):
                    continue
                timestamp = pose.get("aligned_timestamp_seconds")
                if timestamp is None:
                    frame = pose.get("frame_index", pose.get("frame"))
                    if not isinstance(frame, int) or frame < 0:
                        raise ValueError(f"{camera_id} usable head pose needs timestamp or frame index")
                    fps = fps if fps is not None else _artifact_fps(artifact, camera_id)
                    timestamp = frame / fps
                try:
                    bins[_bin_index(timestamp, duration_seconds, source=f"{camera_id} head pose")] = True
                except _OutOfSpanSample:
                    continue
        result[camera_id] = bins
    return result


def _valid_pose_bins_by_track(
    head_pose_by_camera: Mapping[str, Mapping[str, object] | None],
    duration_seconds: float,
) -> dict[str, dict[str, set[int]]]:
    result = {camera: {} for camera in TABLE3_CAMERAS}
    for camera_id in TABLE3_CAMERAS:
        artifact = head_pose_by_camera.get(camera_id)
        if artifact is None:
            continue
        fps: float | None = None
        for track in _tracks(artifact, camera_id):
            track_id = track.get("track_id")
            if not isinstance(track_id, str) or not track_id:
                raise ValueError(f"{camera_id} head-pose track requires track_id")
            bins = result[camera_id].setdefault(track_id, set())
            poses = track.get("poses", ())
            if not isinstance(poses, Sequence) or isinstance(poses, (str, bytes)):
                raise ValueError(f"{camera_id} head-pose records must be a sequence")
            for pose in poses:
                if not isinstance(pose, Mapping):
                    raise ValueError(f"{camera_id} head-pose records must contain mappings")
                angles = tuple(float(pose.get(name, float("nan"))) for name in ("yaw", "pitch", "roll"))
                if not all(isfinite(angle) and -180 <= angle <= 180 for angle in angles):
                    continue
                timestamp = pose.get("aligned_timestamp_seconds")
                if timestamp is None:
                    frame = pose.get("frame_index", pose.get("frame"))
                    if not isinstance(frame, int) or frame < 0:
                        raise ValueError(f"{camera_id} usable head pose needs timestamp or frame index")
                    fps = fps if fps is not None else _artifact_fps(artifact, camera_id)
                    timestamp = frame / fps
                try:
                    bins.add(_bin_index(timestamp, duration_seconds, source=f"{camera_id} head pose"))
                except _OutOfSpanSample:
                    continue
    return result


def _attention_records(document: Mapping[str, object]) -> list[Mapping[str, object]]:
    direct = document.get("attention")
    if isinstance(direct, Sequence) and not isinstance(direct, (str, bytes)):
        if any(not isinstance(item, Mapping) for item in direct):
            raise ValueError("gaze attention records must be mappings")
        return list(direct)  # type: ignore[return-value]
    tracks = document.get("tracks")
    if not isinstance(tracks, (Mapping, Sequence)) or isinstance(tracks, (str, bytes)):
        raise ValueError("gaze artifact must contain attention records or tracks")
    values = tracks.values() if isinstance(tracks, Mapping) else tracks
    records: list[Mapping[str, object]] = []
    for track in values:
        if not isinstance(track, Mapping):
            raise ValueError("gaze tracks must be mappings")
        camera_id = track.get("camera_id")
        track_id = track.get("track_id")
        poses = track.get("poses", track.get("frames", ()))
        if not isinstance(poses, Sequence) or isinstance(poses, (str, bytes)):
            raise ValueError("gaze track poses must be a sequence")
        for pose in poses:
            if not isinstance(pose, Mapping):
                raise ValueError("gaze poses must be mappings")
            records.append({"camera_id": camera_id, "track_id": track_id, **pose})
    return records


def _valid_attention_keys(
    records: Sequence[Mapping[str, object]], duration_seconds: float, *, source: str
) -> set[tuple[str, str, int]]:
    result: set[tuple[str, str, int]] = set()
    for record in records:
        label = record.get("label", record.get("gaze_target", record.get("target")))
        if label not in ATTENTION_TARGETS:
            continue
        camera_id = record.get("camera_id")
        track_id = record.get("track_id")
        if camera_id not in TABLE3_CAMERAS or not isinstance(track_id, str) or not track_id:
            continue
        timestamp = record.get("aligned_timestamp_seconds", record.get("timestamp"))
        if timestamp is None:
            continue
        try:
            result.add((
                str(camera_id), track_id,
                _bin_index(timestamp, duration_seconds, source=source),
            ))
        except _OutOfSpanSample:
            continue
    return result


def _delivered_windows(multimodal_windows: Mapping[str, object]) -> list[Mapping]:
    """The windows that actually reached the focal call, not every assembled window.

    Stage 13 assembles every flagged window and then records which subset fits the focal
    context budget in `focal_delivery`. A metric that scans `windows` therefore counts
    evidence the model was never shown: on session_001 that reported 371 of 820 bins
    delivered when the 14 delivered windows support 153.

    A window artifact without a `focal_delivery` record predates budget selection; every
    assembled window was delivered then, so all of them count.
    """
    windows = multimodal_windows.get("windows")
    if not isinstance(windows, Sequence) or isinstance(windows, (str, bytes)):
        raise ValueError("multimodal-window artifact must contain a windows array")
    for window in windows:
        if not isinstance(window, Mapping):
            raise ValueError("multimodal windows must contain mappings")
    delivery = multimodal_windows.get("focal_delivery")
    if not isinstance(delivery, Mapping):
        return list(windows)
    delivered_ids = delivery.get("delivered_window_ids")
    if not isinstance(delivered_ids, Sequence) or isinstance(delivered_ids, (str, bytes)):
        raise ValueError("focal_delivery must list delivered_window_ids")
    allowed = set(delivered_ids)
    return [window for window in windows if window.get("window_id") in allowed]


def _delivered_attention_keys(
    multimodal_windows: Mapping[str, object], duration_seconds: float
) -> set[tuple[str, str, int]]:
    records: list[Mapping[str, object]] = []
    for window in _delivered_windows(multimodal_windows):
        context = window.get("context")
        attention = context.get("visual_attention") if isinstance(context, Mapping) else None
        window_records = attention.get("records") if isinstance(attention, Mapping) else ()
        if window_records is None:
            window_records = ()
        if not isinstance(window_records, Sequence) or isinstance(window_records, (str, bytes)):
            raise ValueError("delivered visual-attention records must be a sequence")
        if any(not isinstance(item, Mapping) for item in window_records):
            raise ValueError("delivered visual-attention records must contain mappings")
        records.extend(window_records)  # type: ignore[arg-type]
    return _valid_attention_keys(records, duration_seconds, source="delivered attention")


def _transcript_segments_by_bin(
    diarized_transcript: Mapping[str, object], duration_seconds: float
) -> dict[int, list[dict[str, object]]]:
    segments = diarized_transcript.get("segments")
    if not isinstance(segments, Sequence) or isinstance(segments, (str, bytes)):
        raise ValueError("diarized transcript must contain segments")
    result: dict[int, list[dict[str, object]]] = {}
    seen: set[str] = set()
    for index, segment in enumerate(segments):
        if not isinstance(segment, Mapping):
            raise ValueError("diarized transcript segments must be mappings")
        segment_id = segment.get("transcript_segment_id", f"segment-{index:06d}")
        speaker_id = segment.get("speaker_id", segment.get("speaker"))
        if not isinstance(segment_id, str) or not segment_id or segment_id in seen:
            raise ValueError("diarized transcript requires unique transcript_segment_id values")
        if not isinstance(speaker_id, str) or not speaker_id:
            # Diarization assigns no speaker to a segment overlapping no turn. The segment
            # still carries speech, so the funnel's definition puts its bins in the
            # denominator and attributes them to speaker_unlinked -- that reason exists
            # for exactly this case. Skipping the segment outright, as this did, silently
            # removed a bin from a denominator documented as exhaustive: session_001's
            # bin 308 is covered by no other segment and simply vanished.
            speaker_id = None
        seen.add(segment_id)
        start = float(segment.get("start_seconds", segment.get("start", float("nan"))))
        end = float(segment.get("end_seconds", segment.get("end", float("nan"))))
        if not isfinite(start) or not isfinite(end) or start < 0 or end <= start:
            raise ValueError(f"invalid diarized interval for {segment_id}")
        if start >= duration_seconds:
            continue
        clipped_end = min(end, duration_seconds)
        for bin_id in range(floor(start), min(ceil(duration_seconds), ceil(clipped_end))):
            if start < bin_id + 1 and bin_id < clipped_end:
                result.setdefault(bin_id, []).append({
                    "transcript_segment_id": segment_id,
                    "speaker_id": speaker_id,
                    "start_seconds": start,
                    "end_seconds": clipped_end,
                })
    return result


def _harness_bin_records(
    *,
    duration_seconds: float,
    diarized_transcript: Mapping[str, object],
    identity_map: Mapping[str, object],
    best_angles: Mapping[str, object],
    face_presence: Mapping[str, Sequence[bool] | None],
    asd_by_camera: Mapping[str, Mapping[str, object] | None],
    head_pose_by_camera: Mapping[str, Mapping[str, object] | None],
    gaze_tracks: Mapping[str, object] | None,
    multimodal_windows: Mapping[str, object],
) -> list[dict[str, object]] | None:
    if (
        gaze_tracks is None
        or any(face_presence.get(camera) is None for camera in TABLE3_CAMERAS)
        or any(asd_by_camera.get(camera) is None for camera in TABLE3_CAMERAS)
        or any(head_pose_by_camera.get(camera) is None for camera in TABLE3_CAMERAS)
    ):
        return None
    transcript_by_bin = _transcript_segments_by_bin(diarized_transcript, duration_seconds)
    identities = {
        item.get("speaker_id"): item.get("link_status")
        for item in identity_map.get("speakers", ())
        if isinstance(item, Mapping) and isinstance(item.get("speaker_id"), str)
    }
    best_segments = {
        item.get("transcript_segment_id"): item
        for item in best_angles.get("segments", ())
        if isinstance(item, Mapping) and isinstance(item.get("transcript_segment_id"), str)
    }
    pose_bins = _valid_pose_bins_by_track(head_pose_by_camera, duration_seconds)
    raw_attention = _valid_attention_keys(
        _attention_records(gaze_tracks), duration_seconds, source="gaze attention"
    )
    delivered_attention = _delivered_attention_keys(multimodal_windows, duration_seconds)

    asd_samples: dict[tuple[str, str], list[Mapping[str, object]]] = {}
    for camera_id in TABLE3_CAMERAS:
        artifact = asd_by_camera[camera_id]
        assert artifact is not None
        for track in _tracks(artifact, camera_id):
            track_id = track.get("track_id")
            samples = track.get("samples", ())
            if not isinstance(track_id, str) or not isinstance(samples, Sequence) or isinstance(samples, (str, bytes)):
                raise ValueError(f"invalid ASD track for harness funnel on {camera_id}")
            if any(not isinstance(sample, Mapping) for sample in samples):
                raise ValueError(f"invalid ASD sample for harness funnel on {camera_id}")
            asd_samples[(camera_id, track_id)] = list(samples)  # type: ignore[list-item]

    face_union = {
        bin_id for bin_id in transcript_by_bin
        if any(bool(face_presence[camera][bin_id]) for camera in TABLE3_CAMERAS)  # type: ignore[index]
    }
    asd_scored_union: set[int] = set()
    for samples in asd_samples.values():
        for sample in samples:
            score_value = sample.get("score")
            if score_value is None:
                continue
            score = float(score_value)
            if not isfinite(score):
                raise ValueError("harness funnel ASD scores must be finite")
            try:
                bin_id = _bin_index(
                    sample.get("aligned_timestamp_seconds"), duration_seconds,
                    source="harness ASD",
                )
            except _OutOfSpanSample:
                continue
            if bin_id in transcript_by_bin:
                asd_scored_union.add(bin_id)
    pose_union = {
        bin_id for bin_id in transcript_by_bin
        if any(bin_id in bins for camera in pose_bins.values() for bins in camera.values())
    }
    attention_union = {bin_id for _, _, bin_id in raw_attention if bin_id in transcript_by_bin}
    union_by_signal = {
        "face": face_union,
        "asd": asd_scored_union,
        "head_pose": pose_union,
        "attention": attention_union,
    }

    output: list[dict[str, object]] = []
    for bin_id, transcript_segments in sorted(transcript_by_bin.items()):
        linked = [
            segment for segment in transcript_segments
            # A segment diarization gave no speaker cannot be linked to one, so .get on a
            # missing key is the correct read: it yields no identity and the segment is
            # simply not linked, rather than raising partway through the metric.
            if identities.get(segment.get("speaker_id")) in {"fully_linked", "partially_linked"}
        ]
        assignments = []
        for transcript_segment in linked:
            selection = best_segments.get(transcript_segment["transcript_segment_id"])
            if not isinstance(selection, Mapping):
                continue
            camera = selection.get("selected_camera_id")
            track = selection.get("selected_track_id")
            if camera in TABLE3_CAMERAS and isinstance(track, str) and track:
                assignments.append((transcript_segment, str(camera), track))

        selected_face = any(
            bool(face_presence[camera][bin_id]) for _, camera, _ in assignments  # type: ignore[index]
        )
        selected_pose = any(
            bin_id in pose_bins[camera].get(track, set()) for _, camera, track in assignments
        )
        selected_attention = any(
            (camera, track, bin_id) in raw_attention for _, camera, track in assignments
        )
        scored = False
        positive = False
        for segment, camera, track in assignments:
            start = float(segment["start_seconds"])
            end = float(segment["end_seconds"])
            for sample in asd_samples.get((camera, track), ()):
                timestamp = float(sample.get("aligned_timestamp_seconds", float("nan")))
                if not isfinite(timestamp):
                    raise ValueError("harness funnel ASD timestamps must be finite")
                if floor(timestamp) != bin_id or not start <= timestamp < end:
                    continue
                value = sample.get("score")
                if value is None:
                    continue
                score = float(value)
                if not isfinite(score):
                    raise ValueError("harness funnel ASD scores must be finite")
                scored = True
                positive = positive or score > 0.0
        delivered = any(
            (camera, track, bin_id) in delivered_attention for _, camera, track in assignments
        )

        selected_by_signal = {
            "face": selected_face,
            "asd": scored,
            "head_pose": selected_pose,
            "attention": selected_attention,
        }
        signals: dict[str, dict[str, bool]] = {}
        for signal in HARNESS_FUNNEL_SIGNALS:
            union = bin_id in union_by_signal[signal]
            assigned = union and bool(assignments)
            selected = assigned and selected_by_signal[signal]
            gated = selected and positive
            signal_delivered = gated and delivered
            signals[signal] = {
                "eligible_union": union,
                "stage3_assigned": assigned,
                "selected_camera_signal": selected,
                "strict_asd_gate_passed": gated,
                "delivered": signal_delivered,
                "valid_downstream_label_delivered": signal_delivered,
            }

        if not linked:
            reason = "speaker_unlinked"
        elif not assignments:
            reason = "no_selected_camera_track"
        elif not selected_face:
            reason = "no_raw_face"
        elif not scored:
            reason = "no_scored_asd_sample"
        elif not positive:
            reason = "asd_score_not_strictly_positive"
        elif not selected_pose:
            reason = "no_usable_head_pose"
        elif not delivered:
            reason = "no_valid_attention_label"
        else:
            reason = None
        output.append({
            "bin_id": bin_id,
            "signals": signals,
            "delivered": reason is None,
            "withholding_reason": reason,
        })
    return output


def _speaker_duration_by_id(diarized_transcript: Mapping[str, object]) -> dict[str, float]:
    segments = diarized_transcript.get("segments")
    if not isinstance(segments, Sequence) or isinstance(segments, (str, bytes)):
        raise ValueError("diarized transcript must contain segments")
    durations: dict[str, float] = {}
    for segment in segments:
        if not isinstance(segment, Mapping):
            raise ValueError("diarized transcript segments must be mappings")
        speaker_id = segment.get("speaker_id", segment.get("speaker"))
        if not isinstance(speaker_id, str) or not speaker_id:
            # No speaker means no speaker duration to attribute. Counting it under a
            # placeholder would invent a speaker that diarization never found.
            continue
        start = float(segment.get("start_seconds", segment.get("start", float("nan"))))
        end = float(segment.get("end_seconds", segment.get("end", float("nan"))))
        if not isfinite(start) or not isfinite(end) or start < 0 or end <= start:
            raise ValueError(f"invalid diarized interval for {speaker_id}")
        durations[speaker_id] = durations.get(speaker_id, 0.0) + end - start
    return durations


def _serialize_coverage(result: Table3Coverage | UnavailableMetric) -> dict:
    if isinstance(result, UnavailableMetric):
        return asdict(result)
    denominator = result.denominator_bins

    def rate_record(bins: frozenset[int]) -> dict:
        return {
            "numerator": len(bins), "denominator": denominator,
            "denominator_unit": "canonical_one_second_bins",
            "value": len(bins) / denominator, "covered_bin_ids": sorted(bins),
        }

    return {
        "definition_id": result.definition_id,
        "status": result.status,
        "signal": result.signal,
        "denominator_bins": denominator,
        "per_camera": {
            camera_id: rate_record(result.per_camera_covered_bins[camera_id])
            for camera_id in TABLE3_CAMERAS
        },
        "best_cam": {"camera_id": result.best_camera_id, **rate_record(result.best_camera_covered_bins)},
        "union": rate_record(result.union_covered_bins),
        "selected": rate_record(result.selected_covered_bins),
        "selected_segments_by_bin": [list(map(list, items)) for items in result.selected_segments_by_bin],
        "selected_gate_passed_bin_ids": sorted(result.selected_gate_passed_bins),
        "selected_gate_failed_bin_ids": sorted(result.selected_gate_failed_bins),
        "inter_segment_bin_ids": sorted(result.inter_segment_bins),
        "aggregation_trace": list(result.aggregation_trace),
        "n": result.n,
        "invariants": {"union_greater_than_or_equal_to_selected": True},
    }


def _condition_moments(
    focal_runs: Mapping[str, object], session_id: str, condition: str
) -> list[Mapping[str, object]]:
    run = focal_runs.get(condition)
    if not isinstance(run, Mapping):
        raise ValueError(f"focal-run artifact is missing the {condition} condition")
    if run.get("session_id") != session_id or run.get("condition") != condition:
        raise ValueError(f"focal {condition} run belongs to a different session or condition")
    moments = run.get("moments")
    if not isinstance(moments, Sequence) or isinstance(moments, (str, bytes)):
        raise ValueError(f"focal {condition} run must contain a moments array")
    if any(not isinstance(moment, Mapping) for moment in moments):
        raise ValueError(f"focal {condition} moments must contain mappings")
    return list(moments)  # type: ignore[return-value]


def _all_condition_moments(
    focal_runs: Mapping[str, object], session_id: str
) -> dict[str, list[Mapping[str, object]]]:
    k_run = focal_runs.get("K")
    if not isinstance(k_run, Mapping) or k_run.get("session_id") != session_id:
        raise ValueError("focal-run artifact is missing the K condition")
    k_moments = k_run.get("matches")
    if not isinstance(k_moments, Sequence) or isinstance(k_moments, (str, bytes)):
        raise ValueError("focal K run must contain a matches array")
    if any(not isinstance(moment, Mapping) for moment in k_moments):
        raise ValueError("focal K matches must contain mappings")
    return {
        "K": list(k_moments),  # type: ignore[arg-type]
        "T": _condition_moments(focal_runs, session_id, "T"),
        "M": _condition_moments(focal_runs, session_id, "M"),
    }


def _unavailable_definition(
    definition_id: str, error: MetricDefinitionUnresolvedError, missing_unit_ids: Sequence[str]
) -> dict:
    return asdict(
        UnavailableMetric(
            definition_id=definition_id,
            status="unavailable",
            unavailable_reason=str(error),
            missing_unit_ids=tuple(missing_unit_ids),
        )
    )


def _normalize_source_artifacts(
    source_artifacts: Mapping[str, Mapping[str, object]], session_id: str, run_id: str
) -> dict[str, dict]:
    if set(source_artifacts) != set(SOURCE_KEYS):
        missing = sorted(set(SOURCE_KEYS) - set(source_artifacts))
        extra = sorted(set(source_artifacts) - set(SOURCE_KEYS))
        raise ValueError(f"source artifact map mismatch; missing={missing}, extra={extra}")
    normalized = {}
    for key in SOURCE_KEYS:
        record = dict(source_artifacts[key])
        if record.get("run_id") != run_id:
            raise ValueError(f"source artifact {key} does not belong to run {run_id}")
        if record.get("session_id") != session_id:
            raise ValueError(f"source artifact {key} does not belong to session {session_id}")
        if not isinstance(record.get("path"), str) or not record["path"]:
            raise ValueError(f"source artifact {key} needs an exact path")
        digest = record.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"source artifact {key} needs a SHA-256 digest")
        try:
            int(digest, 16)
        except ValueError as error:
            raise ValueError(f"source artifact {key} needs a hexadecimal SHA-256 digest") from error
        if not isinstance(record.get("producer_stage"), str) or not record["producer_stage"]:
            raise ValueError(f"source artifact {key} needs a producer stage")
        if record.get("measurement") != MEASUREMENT:
            raise ValueError(f"source artifact {key} is not capture_at_run")
        normalized[key] = record
    return normalized


def _quantity_lineage(
    session_id: str, run_id: str, source_artifacts: Mapping[str, dict]
) -> dict[str, dict]:
    result = {
        quantity_id: {
            "quantity_id": quantity_id,
            "measurement": MEASUREMENT,
            "session_id": session_id,
            "run_id": run_id,
            "artifact_keys": list(keys),
            "artifacts": [source_artifacts[key] for key in keys],
        }
        for quantity_id, keys in QUANTITY_SOURCES.items()
    }
    # The run manifest uses indexed names to distinguish session artifacts. Declare
    # those exact names as aliases so its exact-key lineage check cannot erase them.
    for quantity_id in SESSION_QUANTITY_IDS:
        alias = f"{quantity_id}[{session_id}]"
        result[alias] = {**result[quantity_id], "quantity_id": alias}
    paper_alias = f"paper_metrics[{session_id}]"
    result[paper_alias] = {
        "quantity_id": paper_alias,
        "measurement": MEASUREMENT,
        "session_id": session_id,
        "run_id": run_id,
        "artifact_keys": list(SOURCE_KEYS),
        "artifacts": [source_artifacts[key] for key in SOURCE_KEYS],
    }
    return result


def _serialize_cross_modal(metric: object, *, denominator_unit: str) -> dict:
    unit = metric.units[0]  # type: ignore[attr-defined]
    record = {
        "definition_id": metric.definition_id,  # type: ignore[attr-defined]
        "status": metric.status,  # type: ignore[attr-defined]
        "numerator": unit.numerator,
        "denominator": unit.denominator,
        "denominator_unit": denominator_unit,
        "value": unit.value,
        "numerator_moment_ids": list(unit.numerator_unit_ids),
        "denominator_moment_ids": list(unit.denominator_unit_ids),
        "excluded_moment_ids": list(unit.excluded_unit_ids),
    }
    # A measured metric has no unavailable reason; the schema requires a string when the
    # field is present, so omit it rather than serializing null.
    if unit.unavailable_reason:
        record["unavailable_reason"] = unit.unavailable_reason
    return record


def compute_session_paper_metrics(
    *,
    session_manifest: Mapping[str, object],
    asd_by_camera: Mapping[str, Mapping[str, object] | None],
    head_pose_by_camera: Mapping[str, Mapping[str, object] | None],
    best_angles: Mapping[str, object],
    identity_map: Mapping[str, object],
    diarized_transcript: Mapping[str, object],
    focal_runs: Mapping[str, object],
    multimodal_windows: Mapping[str, object],
    run_id: str,
    source_artifacts: Mapping[str, Mapping[str, object]],
    run_manifest_path: str,
    faces_by_camera: Mapping[str, Sequence[object] | None] | None = None,
    gaze_tracks: Mapping[str, object] | None = None,
) -> dict:
    session_id = session_manifest.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("session manifest requires session_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("paper metrics require a captured run_id")
    if not isinstance(run_manifest_path, str) or not run_manifest_path:
        raise ValueError("paper metrics require the exact run-manifest path")
    sources = _normalize_source_artifacts(source_artifacts, session_id, run_id)
    duration_seconds = float(session_manifest.get("session_end_seconds", float("nan")))
    if not isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError("session manifest requires a finite positive session_end_seconds")
    for name, artifact in (
        ("best angles", best_angles), ("identity map", identity_map),
        ("focal runs", focal_runs), ("multimodal windows", multimodal_windows),
    ):
        if artifact.get("session_id") != session_id:
            raise ValueError(f"{name} belongs to a different session")
    if set(asd_by_camera) != set(TABLE3_CAMERAS):
        raise ValueError("ASD artifact must contain exactly cam1, cam2, and cam3")
    if set(head_pose_by_camera) != set(TABLE3_CAMERAS):
        raise ValueError("head-pose artifact map must contain exactly cam1, cam2, and cam3")
    if faces_by_camera is None:
        faces_by_camera = {camera: None for camera in TABLE3_CAMERAS}
    if set(faces_by_camera) != set(TABLE3_CAMERAS):
        raise ValueError("face artifact map must contain exactly cam1, cam2, and cam3")

    asd_presence = _asd_presence(asd_by_camera, duration_seconds)
    excluded_face_frame_ids: dict[str, list[int]] = {
        camera: [] for camera in TABLE3_CAMERAS
    }
    face_presence = _face_presence(
        faces_by_camera,
        duration_seconds,
        excluded_out_of_session_detection_frame_ids=excluded_face_frame_ids,
    )
    pose_presence = _head_pose_presence(head_pose_by_camera, duration_seconds)
    # Only head pose is resolved per track today: the ASD Selected column is already gated
    # on the selected track, and face detections carry no track identity to attribute.
    pose_presence_by_track = _head_pose_presence_by_track(
        head_pose_by_camera, duration_seconds
    )
    table3 = {
        signal: _serialize_coverage(
            compute_table3_coverage(
                signal, presence, best_angles, asd_by_camera,
                signal_present_by_camera_track=(
                    pose_presence_by_track if signal == "head_pose" else None
                ),
            )
        )
        for signal, presence in {
            "asd": asd_presence, "face": face_presence, "head_pose": pose_presence,
        }.items()
    }
    table3["face"]["detector_provenance"] = {
        "detector": "S3FD",
        "role": "Light-ASD face-front-end dependency ceiling",
        "confidence_threshold": S3FD_CONFIDENCE_THRESHOLD,
        "confidence_operator": S3FD_CONFIDENCE_OPERATOR,
        "analysis_stream_fps": LIGHT_ASD_ANALYSIS_FPS,
        "timestamp_rule": "zero_based_faces_pickle_frame_index / analysis_stream_fps",
        "source": "raw/asd_camN/pywork/faces.pckl",
        "tracking_used": False,
        "excluded_out_of_session_detection_frame_ids_by_camera": excluded_face_frame_ids,
        "excluded_out_of_session_detection_frame_count": sum(
            len(frame_ids) for frame_ids in excluded_face_frame_ids.values()
        ),
    }
    for signal, row in table3.items():
        if row.get("status") == MEASURED and row["selected"]["numerator"] > row["union"]["numerator"]:
            raise ValueError(f"Selected exceeds Union for {session_id}/{signal}")

    harness_bin_records = _harness_bin_records(
        duration_seconds=duration_seconds,
        diarized_transcript=diarized_transcript,
        identity_map=identity_map,
        best_angles=best_angles,
        face_presence=face_presence,
        asd_by_camera=asd_by_camera,
        head_pose_by_camera=head_pose_by_camera,
        gaze_tracks=gaze_tracks,
        multimodal_windows=multimodal_windows,
    )
    harness_metric = compute_harness_delivery_funnel(harness_bin_records)
    harness_funnel = asdict(harness_metric)
    if isinstance(harness_metric, HarnessDeliveryFunnel):
        harness_funnel["transition_definitions"] = {
            "eligible_union": "signal exists on at least one camera",
            "stage3_assigned": "eligible Union bin has a linked Stage 3 camera and track",
            "selected_camera_signal": "signal exists on the assigned camera/track before gating",
            "strict_asd_gate_passed": "selected-camera signal exists and a scored ASD sample is > 0",
            "delivered": "the gated dependency chain yields a matching visual-attention record in multimodal_windows.json",
            "valid_downstream_label_delivered": "the delivered record has patient/person/other label; not applicable to face or ASD",
        }
        harness_funnel["withholding_partition_invariant"] = {
            "delivered_plus_reason_counts_equals_denominator": True,
            "reasons_are_mutually_exclusive": True,
        }

    durations = _speaker_duration_by_id(diarized_transcript)
    identities = {
        speaker["speaker_id"]: speaker
        for speaker in identity_map.get("speakers", ())
        if isinstance(speaker, Mapping) and isinstance(speaker.get("speaker_id"), str)
    }
    speaker_records = [
        {
            "speaker_id": speaker_id,
            "speech_duration_seconds": duration,
            "link_status": identities.get(speaker_id, {}).get("link_status", "unlinked"),
        }
        for speaker_id, duration in sorted(durations.items())
    ]
    speaker_metric = compute_speaker_link_coverage((session_id,), {session_id: speaker_records})
    speaker_unit = speaker_metric.units[0]
    if speaker_unit.status != MEASURED:
        raise ValueError(f"speaker identity link is unavailable for {session_id}")
    speaker_link = {
        "definition_id": speaker_metric.definition_id,
        "status": speaker_unit.status,
        "numerator": speaker_unit.numerator,
        "denominator": speaker_unit.denominator,
        "denominator_unit": "positive_duration_diarized_speakers",
        "value": speaker_unit.value,
        "linked_speaker_ids": list(speaker_unit.numerator_unit_ids),
        "diarized_speaker_ids": list(speaker_unit.denominator_unit_ids),
        "excluded_speaker_ids": list(speaker_unit.excluded_unit_ids),
    }

    moments_by_condition = _all_condition_moments(focal_runs, session_id)
    t_moments = moments_by_condition["T"]
    m_moments = moments_by_condition["M"]
    t_control = focal_runs["T"].get("control_manifest")  # type: ignore[union-attr]
    m_control = focal_runs["M"].get("control_manifest")  # type: ignore[union-attr]
    if t_control != m_control:
        raise ValueError(f"T/M focal controls diverge for {session_id}")
    by_t = {session_id: t_moments}
    by_m = {session_id: m_moments}
    overlap = compute_symmetric_overlap("T", "M", (session_id,), by_t, by_m)
    m_only = compute_m_only((session_id,), by_t, by_m)
    m_by_id = {str(moment["moment_id"]): moment for moment in m_moments}
    m_only_moments = [m_by_id[moment_id] for moment_id in m_only.m_only_moment_ids]
    m_only_cross_modal = compute_monly_visual_share(m_only_moments)
    all_m_cross_modal = compute_cross_modal_share(m_moments)
    evidence_distribution = compute_evidence_distribution(m_moments)

    # Audit against what the model was actually shown. Auditing every assembled window
    # would resolve a citation to evidence that never reached the prompt, which is the
    # opposite of what an integrity check is for.
    windows = _delivered_windows(multimodal_windows)

    provenance_integrity = compute_provenance_integrity(
        session_id=session_id,
        focal_runs=focal_runs,
        windows=windows,
        delivered_artifact_sha256=sources["multimodal_windows"]["sha256"],
    )

    try:
        attention_distribution = asdict(
            compute_attention_distribution(None, 0.0, duration_seconds, (), ())
        )
    except MetricDefinitionUnresolvedError as error:
        attention_distribution = _unavailable_definition(
            "METRIC-EXAMPLE-ATTENTION-001",
            error,
            ("example_interval_id", "authorized_participant_ids", "attention_samples"),
        )
    try:
        example_silence = asdict(
            compute_example_silence(None, 0.0, duration_seconds, ())
        )
    except MetricDefinitionUnresolvedError as error:
        example_silence = _unavailable_definition(
            "METRIC-EXAMPLE-SILENCE-001",
            error,
            ("example_interval_id", "example_interval_boundaries"),
        )

    tm_overlap = {
        "definition_id": overlap.definition_id,
        "status": overlap.status,
        "value": overlap.value,
        "denominator_definition": "arithmetic_mean_of_two_directional_rates",
        "t_to_m": {
            "numerator": overlap.left_to_right.numerator,
            "denominator": overlap.left_to_right.denominator,
            "denominator_unit": "T_moments",
            "value": overlap.left_to_right.value,
            "overlapping_moment_ids": list(overlap.left_to_right.overlapping_moment_ids),
        },
        "m_to_t": {
            "numerator": overlap.right_to_left.numerator,
            "denominator": overlap.right_to_left.denominator,
            "denominator_unit": "M_moments",
            "value": overlap.right_to_left.value,
            "overlapping_moment_ids": list(overlap.right_to_left.overlapping_moment_ids),
        },
    }
    m_only_count = {
        "definition_id": m_only.definition_id,
        "status": m_only.status,
        "count": m_only.numerator,
        "denominator_sessions": 1,
        "denominator_unit": "complete_T_and_M_session_artifacts",
        "all_m_moment_count": m_only.denominator,
        "m_only_moment_ids": list(m_only.m_only_moment_ids),
        "all_m_moment_ids": list(m_only.all_m_moment_ids),
    }

    return {
        "schema_version": PRODUCER_VERSION,
        "producer": "compute_paper_metrics",
        "measurement": MEASUREMENT,
        "run_id": run_id,
        "run_manifest_path": run_manifest_path,
        "session_id": session_id,
        "canonical_grid": {
            "grid_id": "canonical-eval-grid-v1.0.0",
            "bin_width_seconds": 1.0,
            "session_duration_seconds": duration_seconds,
            "denominator_bins": ceil(duration_seconds),
            "denominator_unit": "canonical_one_second_bins",
        },
        "table3": table3,
        "harness_delivery_failure_funnel": harness_funnel,
        "speaker_identity_link": speaker_link,
        "tm_overlap": tm_overlap,
        "m_only_count": m_only_count,
        "m_only_cross_modal_evidence": _serialize_cross_modal(
            m_only_cross_modal, denominator_unit="valid_M_only_moments"
        ),
        "aggregate_cross_modal_evidence": _serialize_cross_modal(
            all_m_cross_modal, denominator_unit="valid_M_moments"
        ),
        "provenance_integrity": provenance_integrity,
        "evidence_distribution": asdict(evidence_distribution),
        "attention_distribution": attention_distribution,
        "example_silence": example_silence,
        "cohort_inputs": {
            "session_manifest": dict(session_manifest),
            "moments_by_condition": moments_by_condition,
            "best_angles": dict(best_angles),
            "session_end_seconds": duration_seconds,
            "multimodal_windows": list(windows),
            "role_records": None,
            "role_records_status": {
                "status": "unavailable",
                "unavailable_reason": "authorized role manifest is not produced by the paper pipeline",
            },
        },
        "source_artifacts": sources,
        "quantity_artifact_map": _quantity_lineage(session_id, run_id, sources),
    }


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_faces_pickle(path: Path) -> Sequence[object]:
    if not path.is_file():
        raise FileNotFoundError(f"required upstream artifact is missing: {path}")
    with path.open("rb") as handle:
        value = pickle.load(handle)  # trusted, run-manifest-verified Light-ASD artifact
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"expected a frame sequence in {path}")
    return value


def _manifest_source_record(
    manifest: Mapping[str, object], manifest_path: Path, artifact_path: Path, session_id: str
) -> dict:
    project_root = Path(__file__).resolve().parents[2]
    resolved = artifact_path.resolve()
    try:
        key = resolved.relative_to(project_root).as_posix()
    except ValueError:
        key = str(resolved)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping) or not isinstance(artifacts.get(key), Mapping):
        raise ValueError(f"required upstream artifact is absent from run manifest: {key}")
    record = dict(artifacts[key])  # type: ignore[arg-type]
    run_id = manifest.get("run_id")
    if record.get("run_id") != run_id or record.get("session_id") != session_id:
        raise ValueError(f"stale or cross-session upstream artifact: {key}")
    if not resolved.is_file():
        raise FileNotFoundError(f"required upstream artifact is missing: {resolved}")
    actual = _sha256_file(resolved)
    if actual != record.get("sha256"):
        raise ValueError(f"upstream artifact hash differs from run manifest: {key}")
    record["path"] = key
    record["run_manifest_path"] = str(manifest_path.resolve())
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute current-run paper metrics for one session")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--run-manifest", type=Path, required=True)
    parser.add_argument("--session-manifest", type=Path)
    parser.add_argument("--asd", type=Path, help="Canonical camera-to-ASD JSON")
    parser.add_argument("--best-angles", type=Path)
    parser.add_argument("--identity-map", type=Path)
    parser.add_argument("--diarized-transcript", type=Path)
    parser.add_argument("--focal-runs", type=Path, help="Stage-14 artifact containing T and M runs")
    parser.add_argument("--head-pose", action="append", metavar="CAMERA=PATH")
    parser.add_argument("--faces", action="append", metavar="CAMERA=PATH")
    parser.add_argument("--gaze-tracks", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    head_pose_paths = {
        camera_id: raw_dir(args.session_id) / f"head_pose_{camera_id}.json"
        for camera_id in TABLE3_CAMERAS
    }
    for value in args.head_pose or ():
        camera_id, separator, path = value.partition("=")
        if not separator or camera_id not in TABLE3_CAMERAS:
            parser.error("--head-pose must use CAMERA=PATH for cam1, cam2, or cam3")
        head_pose_paths[camera_id] = Path(path)

    face_paths = {
        camera_id: raw_dir(args.session_id) / f"asd_{camera_id}" / "pywork" / "faces.pckl"
        for camera_id in TABLE3_CAMERAS
    }
    for value in args.faces or ():
        camera_id, separator, path = value.partition("=")
        if not separator or camera_id not in TABLE3_CAMERAS:
            parser.error("--faces must use CAMERA=PATH for cam1, cam2, or cam3")
        face_paths[camera_id] = Path(path)

    paths = {
        "session_manifest": args.session_manifest or prerequisites_dir(args.session_id) / "session_manifest.json",
        "asd": args.asd or raw_dir(args.session_id) / "asd_tracks.json",
        "best_angles": args.best_angles or processed_dir(args.session_id) / "best_angles.json",
        "identity_map": args.identity_map or processed_dir(args.session_id) / "identity_map.json",
        "diarized_transcript": args.diarized_transcript or raw_dir(args.session_id) / "diarized_transcript_full.json",
        "gaze_tracks": args.gaze_tracks or raw_dir(args.session_id) / "gaze_tracks.json",
        "focal_runs": args.focal_runs or processed_dir(args.session_id) / "moments_multimodal.json",
        "multimodal_windows": processed_dir(args.session_id) / "multimodal_windows.json",
        **{f"head_pose_{camera}": path for camera, path in head_pose_paths.items()},
        **{f"faces_{camera}": path for camera, path in face_paths.items()},
    }
    manifest = _load(args.run_manifest)
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run manifest requires run_id")
    source_artifacts = {
        key: _manifest_source_record(manifest, args.run_manifest, path, args.session_id)
        for key, path in paths.items()
    }
    result = compute_session_paper_metrics(
        session_manifest=_load(paths["session_manifest"]),
        asd_by_camera=_load(paths["asd"]),
        head_pose_by_camera={camera: _load(path) for camera, path in head_pose_paths.items()},
        best_angles=_load(paths["best_angles"]),
        identity_map=_load(paths["identity_map"]),
        diarized_transcript=_load(paths["diarized_transcript"]),
        focal_runs=_load(paths["focal_runs"]),
        multimodal_windows=_load(paths["multimodal_windows"]),
        faces_by_camera={camera: _load_faces_pickle(path) for camera, path in face_paths.items()},
        gaze_tracks=_load(paths["gaze_tracks"]),
        run_id=run_id,
        source_artifacts=source_artifacts,
        run_manifest_path=str(args.run_manifest.resolve()),
    )
    output = args.output or metrics_dir(args.session_id) / "paper_metrics.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
