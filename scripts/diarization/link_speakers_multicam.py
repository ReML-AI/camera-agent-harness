#!/usr/bin/env python3
"""Contract 3/4 speaker linking, segment selection, and strict frame gating.

All input times are already aligned session seconds. There is deliberately no FPS
argument or legacy identifier parser in the paper path.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable

from scripts.core.errors import ContractError
from scripts.core.records import (
    Interval,
    has_diarized_speaker,
    parse_canonical_track_id,
    require_id,
)
from scripts.core.schema import validate_record
from scripts.utils.session_paths import processed_dir


CAMERAS = ("cam1", "cam2", "cam3")
LINK_THRESHOLD = 0.0
WEAK_THRESHOLD = -0.5


def _segments_for_speaker(segments: Iterable[dict], speaker_id: str) -> list[Interval]:
    active = []
    for segment in segments:
        if segment.get("speaker_id") == speaker_id:
            active.append(Interval(segment["start_seconds"], segment["end_seconds"]))
    return active


def _fragment_overlaps(fragment: dict, interval: Interval) -> bool:
    """Whether a linked track fragment covers any part of this speaker segment.

    A fragment without recorded bounds is treated as eligible so that identity artifacts
    written before fragments carried timing still select rather than silently stop.
    """
    first = fragment.get("first_seen_seconds")
    last = fragment.get("last_seen_seconds")
    if first is None or last is None:
        return True
    first, last = float(first), float(last)
    # first_seen/last_seen are the fragment's first and last SAMPLE timestamps, so the
    # last sample is an observation, not an exclusive end. Treating it as exclusive made
    # this prefilter reject a segment starting exactly on that sample while
    # _eligible_scores, which tests start <= t < end, still counted it -- the prefilter
    # and the scorer disagreeing about the same sample.
    if first == last:
        return interval.start_seconds <= first < interval.end_seconds
    return first < interval.end_seconds and last >= interval.start_seconds


def _validate_track(camera_id: str, track: dict) -> str:
    track_id = track["track_id"]
    parsed_camera, _ = parse_canonical_track_id(track_id)
    if parsed_camera != camera_id:
        raise ContractError(
            f"track {track_id!r} belongs to {parsed_camera!r}, not {camera_id!r}"
        )
    return track_id


def _eligible_scores(track: dict, intervals: list[Interval]) -> list[float]:
    scores = []
    for sample in track.get("samples", []):
        timestamp = sample["aligned_timestamp_seconds"]
        if timestamp < 0:
            raise ContractError("ASD aligned timestamp cannot be negative")
        if any(interval.start_seconds <= timestamp < interval.end_seconds for interval in intervals):
            scores.append(float(sample["score"]))
    return scores


def _camera_candidate(camera_id: str, camera_data: dict | None, intervals: list[Interval],
                      tau_link: float, tau_weak: float) -> dict[str, Any]:
    if camera_data is None:
        return {
            "camera_id": camera_id,
            "track_id": None,
            "mean_asd": None,
            "eligible_frame_count": 0,
            "status": "no_data",
            "rejection_reason": "camera_artifact_unavailable",
        }
    candidates = []
    for track in camera_data.get("tracks", []):
        track_id = _validate_track(camera_id, track)
        scores = _eligible_scores(track, intervals)
        if scores:
            timestamps = [
                float(sample["aligned_timestamp_seconds"]) for sample in track.get("samples", [])
            ]
            candidates.append((fmean(scores), track_id, len(scores),
                               min(timestamps), max(timestamps)))
    if not candidates:
        return {
            "camera_id": camera_id,
            "track_id": None,
            "mean_asd": None,
            "eligible_frame_count": 0,
            "status": "no_data",
            "rejection_reason": "no_eligible_asd_frames",
            "linked_fragments": [],
        }

    # Every fragment clearing tau_weak is retained, each keeping its own bounds.
    #
    # Light-ASD emits a new track whenever a face is lost and re-detected, so one person
    # yields many short fragments across a session. Keeping only the highest-scoring one
    # capped per-segment selection at that fragment's duration: on session_001 it retained
    # 15 of 538 tracks, spanning 69.6s of 960s, so Selected coverage could not exceed 5.6%
    # however well the gate performed. A speaker linked by a fragment early in the session
    # had no eligible view for their later segments.
    #
    # Fragments are NOT merged into one continuous identity. Each keeps its own interval so
    # segment-level selection can require temporal overlap; merging would let a segment be
    # grounded in visual evidence recorded at another time.
    ordered = sorted(candidates, key=lambda item: (-item[0], item[1]))
    fragments = []
    for mean_asd, track_id, count, first_seen, last_seen in ordered:
        if mean_asd > tau_link:
            fragment_status, fragment_reason = "linked", None
        elif mean_asd > tau_weak:
            fragment_status, fragment_reason = "weak", "mean_asd_not_strictly_above_tau_link"
        else:
            fragment_status, fragment_reason = "rejected", "mean_asd_not_strictly_above_tau_weak"
        if fragment_status == "rejected":
            continue
        fragments.append({
            "track_id": track_id,
            "mean_asd": mean_asd,
            "eligible_frame_count": count,
            "status": fragment_status,
            "rejection_reason": fragment_reason,
            "first_seen_seconds": first_seen,
            "last_seen_seconds": last_seen,
        })

    # The camera-level summary still reports the strongest fragment, so the identity
    # artifact keeps the same shape for readers that only ask "is this speaker on this
    # camera at all". Thresholds are unchanged; only retention widened.
    mean_asd, track_id, count, _first, _last = ordered[0]
    if mean_asd > tau_link:
        status, reason = "linked", None
    elif mean_asd > tau_weak:
        status, reason = "weak", "mean_asd_not_strictly_above_tau_link"
    else:
        status, reason = "rejected", "mean_asd_not_strictly_above_tau_weak"
    return {
        "camera_id": camera_id,
        "track_id": track_id,
        "mean_asd": mean_asd,
        "eligible_frame_count": count,
        "status": status,
        "rejection_reason": reason,
        "linked_fragments": fragments,
    }


def build_identity_map(
    segments: list[dict],
    asd_per_cam: dict[str, dict | None],
    *,
    session_id: str,
    link_threshold: float = LINK_THRESHOLD,
    weak_threshold: float = WEAK_THRESHOLD,
) -> dict[str, Any]:
    """Map at most one track per camera and classify speakers using any camera.

    Equality at 0.0 is weak (provided it is above -0.5). Equality at -0.5 is
    unlinked. A speaker with no eligible ASD samples is unlinked, never vacuously full.
    """
    require_id(session_id, "session_id")
    if link_threshold != 0.0 or weak_threshold != -0.5:
        raise ContractError("paper contract fixes tau_link=0.0 and tau_weak=-0.5")
    # Diarization may leave short between-turn segments without a speaker. Such segments
    # cannot enter the speaker set, but they remain counted and reported as unassigned.
    diarized = [segment for segment in segments if segment.get("speaker_id")]
    unassigned = [segment for segment in segments if not segment.get("speaker_id")]
    speaker_ids = sorted({segment["speaker_id"] for segment in diarized})
    for segment in diarized:
        require_id(segment["transcript_segment_id"], "transcript_segment_id")
        require_id(segment["speaker_id"], "speaker_id")
        Interval(segment["start_seconds"], segment["end_seconds"])
    for segment in unassigned:
        require_id(segment["transcript_segment_id"], "transcript_segment_id")
        Interval(segment["start_seconds"], segment["end_seconds"])
    segments = diarized

    speakers = []
    totals = {"fully_linked": 0, "partially_linked": 0, "unlinked": 0}
    camera_ids = sorted(set(CAMERAS) | set(asd_per_cam))
    for speaker_id in speaker_ids:
        intervals = _segments_for_speaker(segments, speaker_id)
        camera_candidates = [
            _camera_candidate(
                camera_id, asd_per_cam.get(camera_id), intervals,
                link_threshold, weak_threshold,
            )
            for camera_id in camera_ids
        ]
        statuses = {candidate["status"] for candidate in camera_candidates}
        if "linked" in statuses:
            link_status = "fully_linked"
        elif "weak" in statuses:
            link_status = "partially_linked"
        else:
            link_status = "unlinked"
        totals[link_status] += 1
        speakers.append({
            "speaker_id": speaker_id,
            "link_status": link_status,
            "camera_candidates": camera_candidates,
        })
    result = {
        "schema_version": "1.0.0",
        "session_id": session_id,
        "tau_link": link_threshold,
        "tau_weak": weak_threshold,
        "speakers": speakers,
        "summary": totals,
        # Reported so the speaker-link denominator can be read honestly: these segments
        # carry speech that no diarized speaker claims, so they are outside this metric
        # rather than a failure of it.
        "segments_without_diarized_speaker": {
            "count": len(unassigned),
            "transcript_segment_ids": [
                segment["transcript_segment_id"] for segment in unassigned
            ],
            "denominator_statement": (
                "speaker linking is computed over diarized speakers; segments with no "
                "diarized speaker contribute no speaker and are listed here"
            ),
        },
    }
    validate_record("identity_map", result)
    return result


def _speaker_record(identity_map: dict, speaker_id: str) -> dict | None:
    return next(
        (speaker for speaker in identity_map["speakers"] if speaker["speaker_id"] == speaker_id),
        None,
    )


def select_best_angle(
    segment: dict,
    identity_map: dict,
    asd_per_cam: dict[str, dict | None],
) -> dict[str, Any]:
    """Choose one mapped camera using segment-local mean ASD and retain all scores."""
    segment_id = require_id(segment["transcript_segment_id"], "transcript_segment_id")
    speaker_id = require_id(segment["speaker_id"], "speaker_id")
    interval = Interval(segment["start_seconds"], segment["end_seconds"])
    speaker = _speaker_record(identity_map, speaker_id)
    camera_scores = []
    selectable = []
    candidate_by_camera = {
        item["camera_id"]: item for item in speaker["camera_candidates"]
    } if speaker else {}
    camera_ids = sorted(set(CAMERAS) | set(asd_per_cam) | set(candidate_by_camera))
    for camera_id in camera_ids:
        candidate = candidate_by_camera.get(camera_id)
        if candidate is None or candidate["status"] not in {"linked", "weak"}:
            reason = "speaker_camera_not_mapped" if candidate else "speaker_unavailable"
            camera_scores.append({
                "camera_id": camera_id, "track_id": None, "mean_asd": None,
                "eligible_frame_count": 0, "reason": reason,
            })
            continue
        camera_data = asd_per_cam.get(camera_id)
        tracks_by_id = {
            item["track_id"]: item for item in (camera_data or {}).get("tracks", [])
        }
        # Only fragments whose own interval meets this segment are eligible. A fragment
        # recorded at another time cannot ground this segment, so it is not scored here
        # even though the speaker is linked to it.
        fragments = candidate.get("linked_fragments")
        if fragments is None:
            fragments = [{"track_id": candidate["track_id"]}]
        overlapping = [
            fragment for fragment in fragments
            if fragment.get("track_id") in tracks_by_id
            and _fragment_overlaps(fragment, interval)
        ]
        best_row = None
        for fragment in overlapping:
            track = tracks_by_id[fragment["track_id"]]
            scores = _eligible_scores(track, [interval])
            if not scores:
                continue
            score = fmean(scores)
            row = {
                "camera_id": camera_id, "track_id": fragment["track_id"],
                "mean_asd": score, "eligible_frame_count": len(scores), "reason": None,
            }
            # Highest segment-local mean wins; canonical id breaks exact ties so the
            # choice does not depend on fragment ordering.
            if best_row is None or (-score, row["track_id"]) < (
                -best_row["mean_asd"], best_row["track_id"]
            ):
                best_row = row
        if best_row is None:
            reason = (
                "no_linked_fragment_overlaps_segment" if not overlapping
                else "no_segment_asd_frames"
            )
            camera_scores.append({
                "camera_id": camera_id, "track_id": None, "mean_asd": None,
                "eligible_frame_count": 0, "reason": reason,
            })
            continue
        camera_scores.append(best_row)
        selectable.append((best_row["mean_asd"], camera_id, best_row["track_id"]))
    selected = sorted(selectable, key=lambda item: (-item[0], item[1]))[0] if selectable else None
    return {
        "transcript_segment_id": segment_id,
        "speaker_id": speaker_id,
        "start_seconds": segment["start_seconds"],
        "end_seconds": segment["end_seconds"],
        "camera_scores": camera_scores,
        "selected_camera_id": selected[1] if selected else None,
        "selected_track_id": selected[2] if selected else None,
        "selected_mean_asd": selected[0] if selected else None,
    }


def gate_best_angle_frames(
    selection: dict,
    *,
    asd_samples: list[dict],
    head_pose_samples: list[dict],
) -> dict[str, Any]:
    """Emit pose/attention inputs only for selected-camera frames with ASD > 0."""
    selected_camera = selection["selected_camera_id"]
    selected_track = selection["selected_track_id"]
    if selected_camera is None or selected_track is None:
        return {"emitted": [], "decisions": [], "reason_counts": {"no_selected_camera": 1}}

    asd_lookup = {
        sample["frame_index"]: sample
        for sample in asd_samples
        if sample["camera_id"] == selected_camera and sample["track_id"] == selected_track
    }
    emitted, decisions = [], []
    counts: dict[str, int] = {}
    for pose in head_pose_samples:
        if pose["camera_id"] != selected_camera or pose["track_id"] != selected_track:
            continue
        frame_index = pose["frame_index"]
        asd = asd_lookup.get(frame_index)
        score = None if asd is None else float(asd["score"])
        if asd is None:
            reason, should_emit = "missing_asd", False
        elif score <= LINK_THRESHOLD:
            reason, should_emit = "asd_not_strictly_positive", False
        else:
            reason, should_emit = None, True
        decision = {
            "frame_index": frame_index,
            "aligned_timestamp_seconds": pose["aligned_timestamp_seconds"],
            "asd_score": score,
            "emitted": should_emit,
            "reason": reason,
        }
        decisions.append(decision)
        if should_emit:
            emitted.append({**pose, "asd_score": score})
        else:
            counts[reason] = counts.get(reason, 0) + 1
    return {"emitted": emitted, "decisions": decisions, "reason_counts": counts}


def build_best_angle_artifact(
    session_id: str,
    segments: list[dict],
    identity_map: dict,
    asd_per_cam: dict[str, dict | None],
) -> dict[str, Any]:
    output_segments = []
    for segment in segments:
        # A segment with no diarized speaker has no speaker to anchor a camera choice to,
        # so it yields no best angle and is absent from this artifact. Table 3's Selected
        # column counts assigned segments, and counting an unassignable one as unselected
        # would charge the selector for a diarization gap it never saw.
        if not has_diarized_speaker(segment):
            continue
        selection = select_best_angle(segment, identity_map, asd_per_cam)
        output_segments.append({
            **{key: value for key, value in selection.items() if key != "selected_mean_asd"},
            "frame_gate": [],
        })
    artifact = {"schema_version": "1.0.0", "session_id": session_id, "segments": output_segments}
    validate_record("best_angle", artifact)
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="Canonical multi-camera speaker fusion")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--transcript", required=True)
    parser.add_argument("--asd", required=True,
                        help="Canonical JSON mapping camera IDs to ASD track artifacts")
    args = parser.parse_args()
    with Path(args.transcript).open("r", encoding="utf-8") as handle:
        segments = json.load(handle)["segments"]
    with Path(args.asd).open("r", encoding="utf-8") as handle:
        asd_per_cam = json.load(handle)
    identity = build_identity_map(segments, asd_per_cam, session_id=args.session_id)
    best_angles = build_best_angle_artifact(args.session_id, segments, identity, asd_per_cam)
    output = processed_dir(args.session_id)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "identity_map.json").open("w", encoding="utf-8") as handle:
        json.dump(identity, handle, indent=2)
    with (output / "best_angles.json").open("w", encoding="utf-8") as handle:
        json.dump(best_angles, handle, indent=2)


if __name__ == "__main__":
    main()
