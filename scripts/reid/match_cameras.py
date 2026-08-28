#!/usr/bin/env python3
"""Build global visual identities from per-camera canonical track outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.core.records import sha256_file

from scripts.reid.config import DEFAULT_CONFIG_PATH, load_identity_config
from scripts.reid.identity_graph import CanonicalTrack, build_global_identities


def _parse_assignments(values: Sequence[str], *, numeric: bool) -> dict[str, object]:
    parsed: dict[str, object] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"expected CAMERA=VALUE, got {value!r}")
        camera_id, raw = value.split("=", 1)
        if not camera_id or camera_id in parsed:
            raise ValueError(f"invalid or duplicate camera assignment: {value!r}")
        parsed[camera_id] = float(raw) if numeric else Path(raw)
    return parsed


def load_canonical_tracks(
    camera_outputs: Mapping[str, Path], sync_offsets_seconds: Mapping[str, float]
) -> list[CanonicalTrack]:
    tracks: list[CanonicalTrack] = []
    for camera_id in sorted(camera_outputs):
        payload = json.loads(camera_outputs[camera_id].read_text(encoding="utf-8"))
        if payload.get("camera_id") != camera_id:
            raise ValueError(
                f"camera key {camera_id!r} does not match payload camera_id "
                f"{payload.get('camera_id')!r}"
            )
        offset = float(sync_offsets_seconds.get(camera_id, 0.0))
        for item in payload.get("canonical_tracks", []):
            intervals = tuple(
                (float(interval[0]) + offset, float(interval[1]) + offset)
                for interval in item["active_intervals"]
            )
            tracks.append(
                CanonicalTrack(
                    camera_id=camera_id,
                    canonical_track_id=str(item["canonical_track_id"]),
                    member_tracklet_ids=tuple(str(value) for value in item["member_tracklet_ids"]),
                    active_intervals=intervals,
                    embedding=(
                        tuple(float(value) for value in item["embedding"])
                        if item.get("embedding") is not None
                        else None
                    ),
                )
            )
    return tracks


def match_camera_outputs(
    camera_outputs: Mapping[str, Path],
    *,
    sync_offsets_seconds: Mapping[str, float] | None = None,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> dict[str, object]:
    config = load_identity_config(config_path)
    offsets = sync_offsets_seconds or {}
    tracks = load_canonical_tracks(camera_outputs, offsets)
    identities, edges = build_global_identities(
        tracks,
        similarity_threshold=config.cross_camera.similarity_threshold,
        minimum_copresence_seconds=config.cross_camera.minimum_copresence_seconds,
    )
    return {
        "schema_version": "global-visual-identities/1.0",
        "policy": "deterministic_feed_forward",
        "config_path": str(Path(config_path)),
        "config_sha256": sha256_file(Path(config_path)),
        "sync_offsets_seconds": {
            camera_id: float(offsets.get(camera_id, 0.0)) for camera_id in sorted(camera_outputs)
        },
        "global_identities": identities,
        "edges": edges,
        "capture_at_run": {
            "canonical_track_count": len(tracks),
            "global_identity_count": len(identities),
            "accepted_edge_count": sum(bool(edge["accepted"]) for edge in edges),
            "rejected_edge_count": sum(not bool(edge["accepted"]) for edge in edges),
        },
        "quality_status": "not_evaluated_without_identity_ground_truth",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        metavar="CAMERA=TRACKS_JSON",
        help="repeat once for every camera",
    )
    parser.add_argument(
        "--sync-offset",
        action="append",
        default=[],
        metavar="CAMERA=SECONDS",
        help="session-time offset added to decoded PTS for one camera",
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    inputs = _parse_assignments(args.input, numeric=False)
    offsets = _parse_assignments(args.sync_offset, numeric=True)
    unknown = set(offsets) - set(inputs)
    if unknown:
        parser.error(f"sync offsets supplied for unknown cameras: {sorted(unknown)}")
    payload = match_camera_outputs(inputs, sync_offsets_seconds=offsets, config_path=args.config)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
