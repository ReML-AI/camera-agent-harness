"""Sparse full-session transcript/frame alignment measurements."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Iterable, Mapping

from scripts.core.errors import AlignmentDriftError, TimingProbeError
from scripts.core.records import CameraTimingProbe, TemporalAlignmentRecord


SAMPLE_POSITIONS = ("beginning", "middle", "end")


def _timestamp_candidates(transcript: Mapping[str, Any]) -> list[float]:
    values: set[float] = set()
    for segment in transcript.get("segments", []):
        words = segment.get("words") if isinstance(segment, Mapping) else None
        sources = words if isinstance(words, list) and words else [segment]
        for source in sources:
            if not isinstance(source, Mapping):
                continue
            for field in ("start", "end"):
                value = source.get(field)
                if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                    values.add(float(value))
    return sorted(values)


def select_transcript_timestamps(
    transcript: Mapping[str, Any], duration_seconds: float
) -> list[tuple[str, float]]:
    """Select distinct transcript timestamps nearest the start, midpoint, and end."""
    if duration_seconds <= 0:
        raise TimingProbeError("session duration must be measured and positive")
    candidates = [value for value in _timestamp_candidates(transcript) if value <= duration_seconds]
    if len(candidates) < len(SAMPLE_POSITIONS):
        raise TimingProbeError(
            "transcript has fewer than three distinct in-session timestamps; "
            "full-session drift cannot be checked"
        )
    quarter = duration_seconds / 4.0
    windows = (
        [value for value in candidates if value < quarter],
        [value for value in candidates if quarter <= value <= duration_seconds - quarter],
        [value for value in candidates if value > duration_seconds - quarter],
    )
    if any(not window for window in windows):
        raise TimingProbeError(
            "transcript does not span the beginning, middle, and end of the full session"
        )
    targets = (0.0, duration_seconds / 2.0, duration_seconds)
    return [
        (position, min(window, key=lambda value: (abs(value - target), value)))
        for position, target, window in zip(SAMPLE_POSITIONS, targets, windows)
    ]


def derived_frame_index(timestamp_seconds: float, probe: CameraTimingProbe) -> int:
    frames = (
        Decimal(str(timestamp_seconds))
        * Decimal(probe.fps_numerator)
        / Decimal(probe.fps_denominator)
    )
    return int(frames.to_integral_value(rounding=ROUND_HALF_UP))


def decode_presentation_timestamps(
    video_path: Path,
    frame_indices: Iterable[int],
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict[int, float]:
    """Read actual decoded best-effort PTS values for the requested frame indexes."""
    requested = sorted(set(frame_indices))
    if not requested or requested[0] < 0:
        raise TimingProbeError("decoded frame indexes must be non-negative")
    command = [
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_frames",
        "-show_entries", "frame=best_effort_timestamp_time", "-of", "json",
        str(video_path),
    ]
    result = runner(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise TimingProbeError(
            f"{TimingProbeError.code}: {video_path}: {result.stderr.strip()}"
        )
    try:
        frames = json.loads(result.stdout)["frames"]
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise TimingProbeError(f"{TimingProbeError.code}: invalid frame probe for {video_path}") from error
    wanted = set(requested)
    captured: dict[int, float] = {}
    for index, frame in enumerate(frames):
        if index not in wanted:
            continue
        raw_timestamp = frame.get("best_effort_timestamp_time")
        try:
            captured[index] = float(raw_timestamp)
        except (TypeError, ValueError) as error:
            raise TimingProbeError(
                f"{TimingProbeError.code}: frame {index} has no decoded PTS in {video_path}"
            ) from error
    missing = [index for index in requested if index not in captured]
    if missing:
        raise TimingProbeError(
            f"{TimingProbeError.code}: decoded frames unavailable in {video_path}: {missing}"
        )
    return captured


def build_alignment_records(
    *,
    session_id: str,
    probe: CameraTimingProbe,
    samples: Iterable[tuple[str, float]],
    decoded_timestamps: Mapping[int, float],
    tolerance_seconds: float,
) -> list[TemporalAlignmentRecord]:
    if tolerance_seconds < 0:
        raise TimingProbeError("alignment tolerance must be non-negative")
    captured_at = datetime.now(timezone.utc).isoformat()
    records = []
    for position, transcript_timestamp in samples:
        frame_index = derived_frame_index(transcript_timestamp, probe)
        if frame_index not in decoded_timestamps:
            raise TimingProbeError(
                f"no decoded PTS captured for {probe.camera_id} frame {frame_index}"
            )
        decoded_timestamp = float(decoded_timestamps[frame_index])
        difference = decoded_timestamp - transcript_timestamp
        records.append(
            TemporalAlignmentRecord(
                session_id=session_id,
                camera_id=probe.camera_id,
                sample_position=position,
                transcript_timestamp_seconds=transcript_timestamp,
                derived_frame_index=frame_index,
                decoded_presentation_timestamp_seconds=decoded_timestamp,
                difference_seconds=difference,
                tolerance_seconds=tolerance_seconds,
                within_tolerance=abs(difference) <= tolerance_seconds,
                captured_at=captured_at,
            )
        )
    return records


def validate_alignment_records(records: Iterable[TemporalAlignmentRecord]) -> None:
    records = list(records)
    positions_by_camera: dict[str, set[str]] = {}
    for record in records:
        positions_by_camera.setdefault(record.camera_id, set()).add(record.sample_position)
        if not record.within_tolerance:
            raise AlignmentDriftError(
                record.camera_id,
                record.derived_frame_index,
                record.difference_seconds,
                record.tolerance_seconds,
            )
    expected = set(SAMPLE_POSITIONS)
    incomplete = [camera for camera, positions in positions_by_camera.items() if positions != expected]
    if not positions_by_camera or incomplete:
        raise TimingProbeError(
            f"alignment validation lacks full-session samples for cameras: {incomplete or ['all']}"
        )
