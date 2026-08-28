#!/usr/bin/env python3
"""Build the canonical per-session stream manifest from the session's own media.

Every field is MEASURED from the files. Nothing is assumed: frame rate is read as an
exact rational (29.97 fps is 30000/1001, not 29.97), duration comes from the container,
and each stream carries the sha256 of the bytes that were measured. This artifact is the
time contract the rest of the pipeline binds to, so a guessed value here would propagate
silently into every downstream timestamp.

    python scripts/setup/build_session_manifest.py --session-id session_008
    python scripts/setup/build_session_manifest.py --all
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

import av

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from scripts.utils.session_paths import SESSIONS_ROOT, prerequisites_dir, videos_dir  # noqa: E402

CHUNK = 1 << 20
STREAM_KINDS = {
    "cam1": "room_video",
    "cam2": "room_video",
    "cam3": "room_video",
    "monitor": "monitor_video",
}


def _probe(path: Path) -> tuple[Fraction, Fraction, float]:
    """Return (average_rate, time_base, duration_seconds) as exact values.

    PyAV is used rather than ffprobe: ffprobe is not present in this environment, and
    PyAV reports the rate and time base as exact Fractions. 29.97 fps is really
    30000/1001, and rounding it to a float here would reintroduce the timing error this
    project already had once.
    """
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        rate = stream.average_rate
        time_base = stream.time_base
        if stream.duration is not None and time_base is not None:
            duration = float(stream.duration * time_base)
        elif container.duration is not None:
            duration = container.duration / av.time_base
        else:
            raise RuntimeError(f"cannot measure duration for {path}")
        if rate is None or time_base is None:
            raise RuntimeError(f"cannot measure rate or time base for {path}")
        return Fraction(rate), Fraction(time_base), duration


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _rational(fraction: Fraction) -> dict[str, int]:
    return {"numerator": fraction.numerator, "denominator": fraction.denominator}


def build(session_id: str) -> dict:
    videos = videos_dir(session_id)
    if not videos.is_dir():
        raise SystemExit(f"no videos directory for {session_id}: {videos}")

    streams, durations = [], []
    for name, kind in STREAM_KINDS.items():
        path = videos / f"{name}.mp4"
        if not path.is_file():
            raise SystemExit(f"{session_id}: required stream is missing: {path}")
        rate, time_base, duration = _probe(path)
        durations.append(duration)
        streams.append(
            {
                "stream_id": name,
                "kind": kind,
                "time_base": _rational(time_base),
                "fps": _rational(rate),
                "duration_seconds": duration,
                # Identity transform: the cameras are treated as sharing one clock
                # because no inter-stream offset has been measured. This is a declared
                # assumption, not a measurement — measuring it is capture_at_run.
                "sync_transform": {
                    "transform_id": "identity",
                    "version": "1.0.0",
                    "offset_seconds": 0.0,
                    "drift": 1.0,
                },
                "source_sha256": _sha256(path),
            }
        )

    return {
        "schema_version": "1.0.0",
        "session_id": session_id,
        # Recording wall-clock time is not embedded in these files; the generation time
        # is recorded instead so the manifest is never mistaken for provenance about
        # when the session was recorded.
        "session_origin": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        # The canonical grid spans the shortest stream: beyond it, at least one camera
        # has no data, so counting those bins would inflate every denominator.
        "session_end_seconds": min(durations),
        "streams": streams,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id")
    parser.add_argument("--all", action="store_true", help="every session under data/sessions")
    args = parser.parse_args()

    if args.all:
        # Ask for the sessions root directly. Deriving it as session_dir("_").parent went
        # through require_id, which rejects "_" as an invalid session id, so --all always
        # crashed before listing anything.
        sessions = sorted(
            path.name for path in SESSIONS_ROOT.iterdir() if (path / "videos").is_dir()
        )
    elif args.session_id:
        sessions = [args.session_id]
    else:
        parser.error("pass --session-id or --all")

    for session_id in sessions:
        document = build(session_id)
        out = prerequisites_dir(session_id) / "session_manifest.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        span = document["session_end_seconds"]
        print(f"{session_id}: {len(document['streams'])} streams, grid {span:.2f}s -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
