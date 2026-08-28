"""Canonical time, identity, and provenance primitives for the paper path."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import json
import re
from typing import Any

from .errors import ContractError


ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def require_id(value: str, namespace: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ContractError(f"invalid {namespace}: {value!r}")
    return value


# Light-ASD re-encodes every clip to 25 fps before detection
# (third_party/Light-ASD/Columbia_test.py:390 runs ffmpeg with `-r 25`), then numbers its
# faces, tracks and scores by enumerating those resampled frames. Every index in
# pywork/{faces,tracks,scores}.pckl therefore lives in a 25 Hz timebase, NOT the source
# camera's rate.
#
# Convert with time = index / LIGHT_ASD_ANALYSIS_FPS. Do not substitute the probed source
# rate: dividing a 25 Hz index by 29.97 compresses the whole timeline by a factor of
# 0.834, and using such an index to seek the source video reads a different moment than
# the one whose face box was recorded. Both mistakes were live in this pipeline.
LIGHT_ASD_ANALYSIS_FPS = 25.0


def light_asd_index_to_seconds(frame_index: int) -> float:
    """Seconds on the session timeline for a Light-ASD frame index."""
    return float(frame_index) / LIGHT_ASD_ANALYSIS_FPS


def light_asd_index_to_source_frame(frame_index: int, source_fps: float) -> int:
    """The source-video frame showing the same instant as a Light-ASD frame index."""
    if source_fps <= 0:
        raise ContractError(f"source fps must be positive, got {source_fps!r}")
    return int(round(light_asd_index_to_seconds(frame_index) * source_fps))


def has_diarized_speaker(segment) -> bool:
    """Whether diarization assigned this transcript segment a speaker.

    WhisperX emits a segment with no speaker when it overlaps no diarization turn — short
    backchannels falling between turns, roughly one segment in three hundred on this data.
    Such a segment carries speech but anchors to no speaker, so every speaker-anchored
    computation (identity linking, best-angle selection, turn analytics, speaker overlays)
    must decide explicitly what to do with it rather than index and crash.

    This predicate exists so that decision is visible at each call site. Filtering silently
    inside one helper would hide segments from denominators that are read as measurements.
    """
    return bool(segment.get("speaker_id"))


def canonical_track_id(camera_id: str, upstream_track_id: str | int) -> str:
    """Build a collision-resistant serialized ID without parsing list positions."""
    camera = require_id(camera_id, "camera_id")
    upstream = require_id(str(upstream_track_id), "upstream_track_id")
    return f"track:{camera}:{upstream}"


def parse_canonical_track_id(value: str) -> tuple[str, str]:
    parts = value.split(":")
    if len(parts) != 3 or parts[0] != "track":
        raise ContractError(f"ambiguous or non-canonical track_id: {value!r}")
    camera, upstream = parts[1:]
    require_id(camera, "camera_id")
    require_id(upstream, "upstream_track_id")
    if canonical_track_id(camera, upstream) != value:
        raise ContractError(f"non-canonical track_id: {value!r}")
    return camera, upstream


@dataclass(frozen=True)
class Interval:
    start_seconds: float
    end_seconds: float

    def __post_init__(self) -> None:
        if self.start_seconds < 0 or self.end_seconds <= self.start_seconds:
            raise ContractError("interval must be non-negative and half-open with start < end")

    def overlaps(self, other: "Interval") -> bool:
        return max(self.start_seconds, other.start_seconds) < min(
            self.end_seconds, other.end_seconds
        )


@dataclass(frozen=True)
class SynchronizationTransform:
    transform_id: str
    offset_seconds: float
    drift: float
    version: str = "1.0.0"

    def __post_init__(self) -> None:
        require_id(self.transform_id, "transform_id")
        if self.drift <= 0:
            raise ContractError("synchronization drift must be positive")

    def align(self, native_timestamp_seconds: float) -> float:
        if native_timestamp_seconds < 0:
            raise ContractError("native timestamp cannot be negative")
        aligned = float(Decimal(str(native_timestamp_seconds)) * Decimal(str(self.drift)) + Decimal(str(self.offset_seconds)))
        if aligned < 0:
            raise ContractError("aligned session timestamp cannot be negative")
        return aligned


@dataclass(frozen=True)
class StreamMetadata:
    stream_id: str
    session_id: str
    time_base_numerator: int
    time_base_denominator: int
    fps_numerator: int | None
    fps_denominator: int | None
    duration_seconds: float
    synchronization: SynchronizationTransform

    def __post_init__(self) -> None:
        require_id(self.stream_id, "stream_id")
        require_id(self.session_id, "session_id")
        if self.time_base_numerator <= 0 or self.time_base_denominator <= 0:
            raise ContractError("stream time base must be positive")
        if (self.fps_numerator is None) != (self.fps_denominator is None):
            raise ContractError("fps numerator and denominator must be supplied together")
        if self.fps_numerator is not None and (
            self.fps_numerator <= 0 or self.fps_denominator <= 0
        ):
            raise ContractError("fps rational must be positive")
        if self.duration_seconds <= 0:
            raise ContractError("stream duration must be positive")

    def frame_timestamp(self, frame_index: int) -> tuple[float, float]:
        if frame_index < 0:
            raise ContractError("frame index cannot be negative")
        if self.fps_numerator is None:
            raise ContractError("stream has no declared FPS; frame join is unavailable")
        native = frame_index * self.fps_denominator / self.fps_numerator
        aligned = self.synchronization.align(native)
        if aligned > self.duration_seconds:
            raise ContractError("aligned timestamp is outside the session stream")
        return native, aligned


@dataclass(frozen=True)
class CameraTimingProbe:
    """Authoritative video timing measured by ffprobe for one run."""

    camera_id: str
    video_path: str
    fps_numerator: int
    fps_denominator: int
    duration_seconds: float
    decoded_frame_count: int
    fps_probe_field: str
    duration_probe_field: str
    captured_at: str
    measurement: str = "capture_at_run"

    def __post_init__(self) -> None:
        require_id(self.camera_id, "camera_id")
        if self.fps_numerator <= 0 or self.fps_denominator <= 0:
            raise ContractError("probed FPS rational must be positive")
        if self.duration_seconds <= 0:
            raise ContractError("probed duration must be positive")
        if self.decoded_frame_count <= 0:
            raise ContractError("decoded frame count must be positive")
        if not self.video_path or not self.fps_probe_field or not self.duration_probe_field:
            raise ContractError("camera timing probe fields must name their measured sources")
        if self.measurement != "capture_at_run":
            raise ContractError("camera timing values must be capture_at_run")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TemporalAlignmentRecord:
    """One transcript-to-decoded-frame comparison sampled during a run."""

    session_id: str
    camera_id: str
    sample_position: str
    transcript_timestamp_seconds: float
    derived_frame_index: int
    decoded_presentation_timestamp_seconds: float
    difference_seconds: float
    tolerance_seconds: float
    within_tolerance: bool
    captured_at: str
    measurement: str = "capture_at_run"

    def __post_init__(self) -> None:
        require_id(self.session_id, "session_id")
        require_id(self.camera_id, "camera_id")
        if self.sample_position not in {"beginning", "middle", "end"}:
            raise ContractError("alignment sample position must be beginning, middle, or end")
        if self.transcript_timestamp_seconds < 0:
            raise ContractError("transcript timestamp cannot be negative")
        if self.derived_frame_index < 0:
            raise ContractError("derived frame index cannot be negative")
        if self.decoded_presentation_timestamp_seconds < 0:
            raise ContractError("decoded presentation timestamp cannot be negative")
        if self.tolerance_seconds < 0:
            raise ContractError("alignment tolerance cannot be negative")
        if self.measurement != "capture_at_run":
            raise ContractError("alignment values must be capture_at_run")
        measured_difference = (
            self.decoded_presentation_timestamp_seconds
            - self.transcript_timestamp_seconds
        )
        if abs(measured_difference - self.difference_seconds) > 1e-9:
            raise ContractError("alignment difference is inconsistent with captured timestamps")
        if self.within_tolerance != (abs(self.difference_seconds) <= self.tolerance_seconds):
            raise ContractError("alignment tolerance result is inconsistent with captured difference")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class Provenance:
    component_id: str
    component_version: str
    config_sha256: str
    artifact_sha256: str
    source_stream_id: str

    def __post_init__(self) -> None:
        require_id(self.component_id, "component_id")
        require_id(self.component_version, "component_version")
        require_id(self.source_stream_id, "source_stream_id")
        if not SHA256_RE.fullmatch(self.config_sha256):
            raise ContractError("config_sha256 must be a lowercase SHA-256 digest")
        if not SHA256_RE.fullmatch(self.artifact_sha256):
            raise ContractError("artifact_sha256 must be a lowercase SHA-256 digest")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
