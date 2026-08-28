#!/usr/bin/env python3
"""
Compute Video Overlay Data

Merges person tracking, head pose, speech diarization, and moment data
into a unified keyframe JSON for the frontend canvas overlay system.

Input:
  - person_tracks_cam1.json  (bounding boxes per person per frame)
  - head_pose_full.json      (yaw/pitch/roll per track per frame)
  - identity_map.json        (speaker-to-camera-track identity mapping)
  - best_angles.json         (Stage-3 per-segment camera/track assignment)
  - moment_contexts.json     (critical moments with timestamps)
  - person_roles_per_camera.json (labeled roles)

Output:
  - video_overlay_data.json  (keyframe data for canvas rendering)
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict

# Legacy defaults (backward compat when no --session-id)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_LEGACY_PROCESSED = _PROJECT_ROOT / "data" / "processed"
_LEGACY_LABELED = _PROJECT_ROOT / "data" / "labeled"


def _get_paths(session_id: str = None) -> dict:
    """Return dict of paths, using session_paths when session_id is provided."""
    if session_id is not None:
        from scripts.utils.session_paths import raw_dir, processed_dir, prerequisites_dir
        _raw = raw_dir(session_id)
        _processed = processed_dir(session_id)
        _prereqs = prerequisites_dir(session_id)
        return {
            "person_tracks": _raw / "person_tracks_cam1.json",
            "head_pose": _raw / "head_pose_cam1.json",
            "identity_map": _processed / "identity_map.json",
            "best_angles": _processed / "best_angles.json",
            "moment_contexts": _processed / "moment_contexts.json",
            "person_roles": _prereqs / "person_roles.json",
            "output_video_overlay": _processed / "video_overlay_data.json",
        }
    # Legacy paths
    return {
        "person_tracks": _LEGACY_PROCESSED / "person_tracks_cam1.json",
        "head_pose": _LEGACY_PROCESSED / "head_pose_full.json",
        "identity_map": _LEGACY_PROCESSED / "identity_map.json",
        "best_angles": _LEGACY_PROCESSED / "best_angles.json",
        "moment_contexts": _LEGACY_PROCESSED / "moment_contexts.json",
        "person_roles": _LEGACY_LABELED / "person_roles_per_camera.json",
        "output_video_overlay": _LEGACY_PROCESSED / "video_overlay_data.json",
    }


def load_json(path: Path) -> Any:
    with open(path) as f:
        return json.load(f)


def build_person_bbox_index(tracks_data: dict, fps: float) -> Dict[int, Dict[str, dict]]:
    """Build frame -> {person_id: bbox_info} index from person tracks."""
    frame_index: Dict[int, Dict[str, dict]] = defaultdict(dict)

    for person in tracks_data.get("persons", []):
        pid = f"cam1_person_{person['person_id']}"
        for appearance in person.get("appearances", []):
            for bb in appearance.get("bounding_boxes", []):
                frame = bb["frame_num"]
                bbox = bb["bbox"]
                frame_index[frame][pid] = {
                    "x1": bbox[0],
                    "y1": bbox[1],
                    "x2": bbox[2],
                    "y2": bbox[3],
                    "confidence": bb.get("confidence", 0.0),
                }

    return frame_index


def build_head_pose_index(hp_data: dict, tolerance: int = 3) -> Dict[int, Dict[str, dict]]:
    """Build frame -> {track_id: pose_info} index from head pose data.

    Since head pose frames may not align exactly with keyframes (e.g., modulo 5 = 3),
    we index each pose at its exact frame AND nearby frames within tolerance.
    """
    frame_index: Dict[int, Dict[str, dict]] = defaultdict(dict)

    for track_id, track_data in hp_data.get("tracks", {}).items():
        for pose in track_data.get("poses", []):
            frame = pose["frame"]
            pose_data = {
                "yaw": pose["yaw"],
                "pitch": pose["pitch"],
                "roll": pose["roll"],
                "bbox": pose.get("bbox"),  # pixel coords [x1, y1, x2, y2]
            }
            # Index at the exact frame and nearby frames for keyframe alignment
            for f in range(frame - tolerance, frame + tolerance + 1):
                if f >= 0 and track_id not in frame_index[f]:
                    frame_index[f][track_id] = pose_data

    return frame_index


def build_speaker_map(identity_map: dict, camera_id: str = "cam1") -> Dict[str, str]:
    """Build a speaker -> mapped track index from the Stage-8 identity artifact."""
    speaker_to_track = {}
    for speaker in identity_map.get("speakers", []):
        speaker_id = speaker.get("speaker_id")
        candidates = [
            candidate
            for candidate in speaker.get("camera_candidates", [])
            if candidate.get("camera_id") == camera_id
        ]
        if len(candidates) > 1:
            raise ValueError(f"duplicate {camera_id} identity candidate for {speaker_id}")
        if candidates and candidates[0].get("status") in {"linked", "weak"}:
            track_id = candidates[0].get("track_id")
            if not isinstance(track_id, str) or not track_id:
                raise ValueError(f"mapped identity candidate for {speaker_id} has no track_id")
            speaker_to_track[speaker_id] = track_id
    return speaker_to_track


def build_selected_speaking_intervals(best_angles: dict, camera_id: str = "cam1") -> List[dict]:
    """Return Stage-3 segment assignments for the camera rendered by this overlay."""
    intervals = []
    for segment in best_angles.get("segments", []):
        if segment.get("selected_camera_id") != camera_id:
            continue
        track_id = segment.get("selected_track_id")
        if not isinstance(track_id, str) or not track_id:
            raise ValueError(
                f"Stage-3 segment {segment.get('transcript_segment_id')} selected "
                f"{camera_id} without selected_track_id"
            )
        intervals.append({
            "start": segment["start_seconds"],
            "end": segment["end_seconds"],
            "speaker": segment.get("speaker_id"),
            "track_id": track_id,
            "transcript_segment_id": segment["transcript_segment_id"],
        })
    return sorted(intervals, key=lambda item: (item["start"], item["end"], item["transcript_segment_id"]))


def get_active_speaking_tracks(timestamp: float, intervals: List[dict]) -> set[str]:
    """Resolve speaking tracks using half-open Stage-3 segment assignments."""
    return {
        interval["track_id"]
        for interval in intervals
        if interval["start"] <= timestamp < interval["end"]
    }


def build_moment_intervals(moments_data: dict, fps: float) -> List[dict]:
    """Build list of moment intervals with frame numbers."""
    intervals = []
    for m in moments_data.get("moments", []):
        intervals.append({
            "moment_id": m["moment_id"],
            "start_frame": int(m["timestamp"] * fps),
            "end_frame": int(m["end_timestamp"] * fps),
            "start_time": m["timestamp"],
            "end_time": m["end_timestamp"],
            "category": m["category"],
            "importance": m["importance"],
        })
    return sorted(intervals, key=lambda x: x["start_frame"])


def get_active_moment(frame: int, moments: List[dict]) -> Optional[dict]:
    """Find if a frame falls within a critical moment."""
    for m in moments:
        if m["start_frame"] <= frame <= m["end_frame"]:
            return m
        if m["start_frame"] > frame:
            break
    return None


def load_roles(roles_data: dict) -> Dict[str, dict]:
    """Build person_id -> role info."""
    role_map = {}
    for label_key, info in roles_data.get("person_labels", {}).items():
        # Keys are like "cam1_person_1_frame_0" -> extract "cam1_person_1"
        parts = label_key.split("_frame_")
        person_key = parts[0] if parts else label_key
        role_map[person_key] = {
            "role": info.get("role", "Unknown"),
            "notes": info.get("notes", ""),
        }
    return role_map


def derive_roles_from_tracks(tracks_data: dict) -> Dict[str, dict]:
    """Build the person map from tracking identities instead of hand-labelled roles.

    The tracker assigns each person a stable ID, so the overlay can identify people without
    a governed role-label file. The label states identity rather than a clinical role; naming
    a role would assert information the tracking artifact does not contain.
    """
    role_map = {}
    for person in tracks_data.get("persons", []):
        person_id = person["person_id"]
        role_map[f"cam1_person_{person_id}"] = {
            "role": f"Person {person_id}",
            "notes": "",
        }
    return role_map


# Identity labels are open-ended, so colours cycle by person id rather than being keyed by a
# fixed set of role names.
IDENTITY_COLORS = ("#10B981", "#3B82F6", "#F59E0B", "#8B5CF6", "#EC4899", "#14B8A6")


def identity_color(person_key: str, role: str) -> str:
    """Colour for a person: the role palette when a role is known, else stable by identity."""
    if role in ROLE_COLORS:
        return ROLE_COLORS[role]
    digits = "".join(character for character in person_key if character.isdigit())
    index = int(digits) if digits else 0
    return IDENTITY_COLORS[index % len(IDENTITY_COLORS)]


ROLE_COLORS = {
    "Student Nurse (Primary)": "#10B981",  # green
    "Supervising Nurse/Doctor": "#3B82F6",  # blue
    "Patient/Mannequin": "#F59E0B",  # amber
    "Observer/Other": "#6B7280",  # gray
}

# Maximum gap (in frames) over which to forward-fill person positions.
# At interval=5, 3 keyframe intervals = 15 raw frames.
FORWARD_FILL_MAX_GAP = 15


def forward_fill_keyframes(keyframes: List[dict], keyframe_interval: int) -> Tuple[List[dict], int]:
    """
    Post-processing: for each person track, if they appear in keyframe N and
    then disappear for ≤ FORWARD_FILL_MAX_GAP frames before reappearing,
    fill the gap with their last known bbox (headPose=null, isSpeaking=False).

    Only fills small tracking gaps; does not extrapolate long absences.
    """
    if not keyframes:
        return keyframes, 0

    # Map frame number -> index in keyframes list for fast lookup
    frame_to_idx = {kf["frame"]: i for i, kf in enumerate(keyframes)}

    # Collect per-track appearances first
    track_appearances: Dict[str, List[dict]] = defaultdict(list)
    for kf in keyframes:
        for p in kf["persons"]:
            pid = p.get("trackId") or p["personId"]
            track_appearances[pid].append({"frame": kf["frame"], "person": p})

    filled_count = 0
    for pid, appearances in track_appearances.items():
        if len(appearances) < 2:
            continue
        for i in range(len(appearances) - 1):
            frame_a = appearances[i]["frame"]
            frame_b = appearances[i + 1]["frame"]
            gap = frame_b - frame_a
            if gap <= keyframe_interval:
                continue  # adjacent keyframes, no gap
            if gap > FORWARD_FILL_MAX_GAP + keyframe_interval:
                continue  # gap too large to fill

            last_bbox = appearances[i]["person"]["bbox"]
            last_person_id = appearances[i]["person"]["personId"]
            last_track_id = appearances[i]["person"].get("trackId")

            # Fill all intermediate keyframes in this gap
            fill_frame = frame_a + keyframe_interval
            while fill_frame < frame_b:
                kf_idx = frame_to_idx.get(fill_frame)
                if kf_idx is not None:
                    # Check if this person is already in this keyframe
                    existing_ids = {(p.get("trackId") or p["personId"]) for p in keyframes[kf_idx]["persons"]}
                    if pid not in existing_ids:
                        keyframes[kf_idx]["persons"].append({
                            "personId": last_person_id,
                            "trackId": last_track_id,
                            "bbox": last_bbox,
                            "headPose": None,
                            "isSpeaking": False,
                        })
                        filled_count += 1
                fill_frame += keyframe_interval

    return keyframes, filled_count


def main(session_id: str = None, keyframe_interval: int = 5):
    paths = _get_paths(session_id)

    print("=" * 60)
    print("COMPUTE VIDEO OVERLAY DATA")
    print("=" * 60)

    # Load all data sources
    print("\nLoading data sources...")

    person_tracks = load_json(paths["person_tracks"])
    print(f"  Person tracks: {len(person_tracks.get('persons', []))} persons")

    head_pose = load_json(paths["head_pose"])
    hp_meta = head_pose.get("metadata", {})
    fps = hp_meta.get("fps")
    if not fps or fps <= 0:
        raise SystemExit("head pose metadata has no usable fps; regenerate stage 3 (head pose)")
    print(f"  Head pose: {len(head_pose.get('tracks', {}))} tracks, {fps} fps")

    identity_map = load_json(paths["identity_map"])
    best_angles = load_json(paths["best_angles"])
    print(f"  Stage-8 speaker identities: {len(identity_map.get('speakers', []))}")
    print(f"  Stage-3 angle assignments: {len(best_angles.get('segments', []))} segments")

    moments_data = load_json(paths["moment_contexts"])
    print(f"  Moment contexts: {len(moments_data.get('moments', []))} moments")

    # Hand-labelled roles are an optional override; identities come from the tracker itself.
    roles_path = paths["person_roles"]
    roles_data = load_json(roles_path) if Path(roles_path).exists() else None
    if roles_data is None:
        print("  Person roles: none supplied, labelling by tracking identity")
    else:
        print(f"  Person roles: {len(roles_data.get('person_labels', {}))} labels")

    # Build indices
    print("\nBuilding indices...")
    bbox_index = build_person_bbox_index(person_tracks, fps)
    hp_index = build_head_pose_index(head_pose)
    speaker_map = build_speaker_map(identity_map, camera_id="cam1")
    speaking_intervals = build_selected_speaking_intervals(best_angles, camera_id="cam1")
    moment_intervals = build_moment_intervals(moments_data, fps)
    role_map = load_roles(roles_data) if roles_data else derive_roles_from_tracks(person_tracks)

    print(f"  BBox frames: {len(bbox_index)}")
    print(f"  Head pose frames: {len(hp_index)}")
    print(f"  Speaker-track map: {speaker_map}")
    print(f"  Speaking intervals: {len(speaking_intervals)}")
    print(f"  Moment intervals: {len(moment_intervals)}")
    print(f"  Role map: {list(role_map.keys())}")

    # Determine total frames
    all_frames = set(bbox_index.keys()) | set(hp_index.keys())
    max_frame = max(all_frames) if all_frames else 0
    if moment_intervals:
        max_frame = max(max_frame, max(m["end_frame"] for m in moment_intervals))
    print(f"\n  Total frame range: 0 - {max_frame}")

    # Build person metadata
    persons_meta = {}
    for pid, role_info in role_map.items():
        if pid.startswith("cam1_"):
            role = role_info["role"]
            persons_meta[pid] = {
                "role": role,
                "label": role_info.get("notes", role),
                "color": identity_color(pid, role),
            }

    # Build moment metadata
    moments_meta = []
    for m in moment_intervals:
        moments_meta.append({
            "moment_id": m["moment_id"],
            "start_frame": m["start_frame"],
            "end_frame": m["end_frame"],
            "start_time": m["start_time"],
            "end_time": m["end_time"],
            "category": m["category"],
            "importance": m["importance"],
        })

    # Build track -> speaker -> role mapping
    track_speaker_role = {}
    speaker_roles = moments_data.get("speaker_roles", {})
    for speaker, track_id in speaker_map.items():
        role_info = speaker_roles.get(speaker, {})
        track_speaker_role[track_id] = {
            "speaker": speaker,
            "role": role_info.get("role", "Unknown"),
            "label": role_info.get("label", speaker),
        }

    # Generate keyframes
    print(f"\nGenerating keyframes (interval={keyframe_interval})...")
    keyframes = []
    total_persons = 0
    speaking_frames = 0

    for frame in range(0, max_frame + 1, keyframe_interval):
        timestamp = frame / fps
        speaking_tracks = get_active_speaking_tracks(timestamp, speaking_intervals)
        active_moment = get_active_moment(frame, moment_intervals)

        persons = []
        hp_data_frame = hp_index.get(frame, {})

        # Use head pose tracks as person source (face bboxes)
        for track_id, hp in hp_data_frame.items():
            if not hp.get("bbox"):
                continue

            # Face bbox in pixel coords -> normalize to 0-1
            hp_bbox = hp["bbox"]
            x1 = round(hp_bbox[0] / 1920, 4)
            y1 = round(hp_bbox[1] / 1080, 4)
            x2 = round(hp_bbox[2] / 1920, 4)
            y2 = round(hp_bbox[3] / 1080, 4)

            # Determine identity
            track_info = track_speaker_role.get(track_id, {})
            speaker = track_info.get("speaker")

            # The speaking indicator follows the segment-local Stage-3 camera/track
            # assignment. A segment assigned to another camera must not light up cam1.
            is_speaking = track_id in speaking_tracks

            # Person ID: use speaker name if known, else track ID
            person_id = f"track_{track_id}"
            if speaker:
                person_id = speaker

            persons.append({
                "personId": person_id,
                "trackId": track_id,
                "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                "headPose": {
                    "yaw": round(hp["yaw"], 1),
                    "pitch": round(hp["pitch"], 1),
                    "roll": round(hp["roll"], 1),
                },
                "isSpeaking": is_speaking,
            })

        # Also check YOLO person tracks for this frame (larger body bboxes)
        bbox_data = bbox_index.get(frame, {})
        if bbox_data and not persons:
            # Use person tracks as fallback when no head pose data
            for pid, bbox in bbox_data.items():
                persons.append({
                    "personId": pid,
                    "bbox": {
                        "x1": round(bbox["x1"], 4),
                        "y1": round(bbox["y1"], 4),
                        "x2": round(bbox["x2"], 4),
                        "y2": round(bbox["y2"], 4),
                    },
                    "headPose": None,
                    "isSpeaking": False,
                })

        total_persons += len(persons)
        if any(p["isSpeaking"] for p in persons):
            speaking_frames += 1

        keyframes.append({
            "frame": frame,
            "timestamp": round(timestamp, 3),
            "persons": persons,
            "isCriticalMoment": active_moment is not None,
            "criticalMomentId": active_moment["moment_id"] if active_moment else None,
        })

        if frame % 5000 == 0 and frame > 0:
            print(f"  Processed frame {frame}/{max_frame} ({frame * 100 // max_frame}%)")

    # 5b: Forward-fill small tracking gaps
    print("\nForward-filling tracking gaps...")
    keyframes, filled_count = forward_fill_keyframes(keyframes, keyframe_interval)
    print(f"  Filled {filled_count} person-frame slots")

    # Recount stats after fill
    person_frames = sum(1 for kf in keyframes if kf["persons"])
    speaking_frames_after = sum(1 for kf in keyframes if any(p["isSpeaking"] for p in kf["persons"]))

    # Output — no vitals (5c)
    output = {
        "videoId": "cam1",
        "fps": fps,
        "totalFrames": max_frame,
        "videoWidth": 1920,
        "videoHeight": 1080,
        "keyframeInterval": keyframe_interval,
        "bboxFormat": "normalized",  # 0-1 coordinates
        "persons": persons_meta,
        "moments": moments_meta,
        "keyframes": keyframes,
    }

    output_path = paths["output_video_overlay"]
    with open(output_path, "w") as f:
        json.dump(output, f, separators=(",", ":"))  # compact JSON

    file_size = output_path.stat().st_size
    avg_persons = sum(len(kf["persons"]) for kf in keyframes) / len(keyframes) if keyframes else 0

    print(f"\n{'=' * 60}")
    print(f"Output: {output_path}")
    print(f"Total keyframes: {len(keyframes)}")
    print(f"Frames with persons: {person_frames} ({person_frames * 100 // len(keyframes) if keyframes else 0}%)")
    print(f"Frames with speaking: {speaking_frames_after} ({speaking_frames_after * 100 // len(keyframes) if keyframes else 0}%)")
    print(f"Avg persons/frame: {avg_persons:.2f}")
    print(f"File size: {file_size / 1024:.1f} KB")
    print(f"Moment intervals: {len(moments_meta)}")
    print(f"Persons tracked: {len(persons_meta)}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute video overlay data")
    parser.add_argument("--session-id", default=None, help="Session ID (omit for legacy paths)")
    parser.add_argument("--keyframe-interval", type=int, default=5,
                        help="Store every Nth frame (default: 5)")
    args = parser.parse_args()
    main(session_id=args.session_id, keyframe_interval=args.keyframe_interval)
