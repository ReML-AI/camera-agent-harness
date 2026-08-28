"""Authoritative ffprobe-based video timing capture."""

from __future__ import annotations

from datetime import datetime, timezone
from fractions import Fraction
import json
from pathlib import Path
import subprocess
from typing import Callable

from scripts.core.errors import TimingProbeError
from scripts.core.records import CameraTimingProbe


def probe_video(
    video_path: Path,
    camera_id: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> CameraTimingProbe:
    """Measure a video's rational average rate and duration; never substitutes defaults."""
    command = [
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
        "-show_entries", "stream=avg_frame_rate,duration,nb_read_frames:format=duration",
        "-of", "json", str(video_path),
    ]
    result = runner(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise TimingProbeError(
            f"{TimingProbeError.code}: {video_path}: {result.stderr.strip()}"
        )
    try:
        payload = json.loads(result.stdout)
        stream = payload["streams"][0]
        rate = Fraction(stream["avg_frame_rate"])
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError) as error:
        raise TimingProbeError(
            f"{TimingProbeError.code}: {video_path}: no measured avg_frame_rate"
        ) from error
    if rate <= 0:
        raise TimingProbeError(
            f"{TimingProbeError.code}: {video_path}: non-positive avg_frame_rate"
        )
    duration_field = "stream.duration"
    duration_raw = stream.get("duration")
    if duration_raw in (None, "N/A"):
        duration_field = "format.duration"
        duration_raw = payload.get("format", {}).get("duration")
    try:
        duration = float(duration_raw)
    except (TypeError, ValueError) as error:
        raise TimingProbeError(
            f"{TimingProbeError.code}: {video_path}: no measured duration"
        ) from error
    if duration <= 0:
        raise TimingProbeError(
            f"{TimingProbeError.code}: {video_path}: non-positive duration"
        )
    try:
        decoded_frame_count = int(stream["nb_read_frames"])
    except (KeyError, TypeError, ValueError) as error:
        raise TimingProbeError(
            f"{TimingProbeError.code}: {video_path}: decoded frame count was not measured"
        ) from error
    if decoded_frame_count <= 0:
        raise TimingProbeError(
            f"{TimingProbeError.code}: {video_path}: decoded frame count is non-positive"
        )
    return CameraTimingProbe(
        camera_id=camera_id,
        video_path=str(video_path.resolve()),
        fps_numerator=rate.numerator,
        fps_denominator=rate.denominator,
        duration_seconds=duration,
        decoded_frame_count=decoded_frame_count,
        fps_probe_field="stream.avg_frame_rate",
        duration_probe_field=duration_field,
        captured_at=datetime.now(timezone.utc).isoformat(),
    )
