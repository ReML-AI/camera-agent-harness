#!/usr/bin/env python3
"""
Compute Interaction Analytics from diarized transcript, Stage-8 identity data, and head pose data.
Produces interaction_analytics.json for the frontend.
"""

import json
import argparse
from pathlib import Path
from collections import defaultdict

# Legacy default (backward compat when no --session-id)
_LEGACY_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "processed"


def _get_paths(session_id: str = None) -> dict:
    """Return dict of paths, using session_paths when session_id is provided."""
    if session_id is not None:
        from scripts.utils.session_paths import raw_dir, processed_dir
        _raw = raw_dir(session_id)
        _processed = processed_dir(session_id)
        return {
            "diarized_transcript": _raw / "diarized_transcript_full.json",
            "identity_map": _processed / "identity_map.json",
            "best_angles": _processed / "best_angles.json",
            "head_pose": _raw / "head_pose_cam1.json",
            "gaze_tracks": _raw / "gaze_tracks.json",
            "output_interaction_analytics": _processed / "interaction_analytics.json",
        }
    # Legacy paths
    return {
        "diarized_transcript": _LEGACY_DATA_DIR / "diarized_transcript_full.json",
        "identity_map": _LEGACY_DATA_DIR / "identity_map.json",
        "best_angles": _LEGACY_DATA_DIR / "best_angles.json",
        "head_pose": _LEGACY_DATA_DIR / "head_pose_full.json",
        "gaze_tracks": _LEGACY_DATA_DIR / "gaze_tracks.json",
        "output_interaction_analytics": _LEGACY_DATA_DIR / "interaction_analytics.json",
    }

SPEAKER_COLORS = {
    "SPEAKER_00": "#3B82F6",  # blue
    "SPEAKER_01": "#10B981",  # green
    "SPEAKER_02": "#F59E0B",  # amber
    "SPEAKER_03": "#A855F7",  # purple
}
SPEAKER_LABELS = {
    "SPEAKER_00": "Speaker A",
    "SPEAKER_01": "Speaker B",
    "SPEAKER_02": "Speaker C",
    "SPEAKER_03": "Speaker D",
}
DEFAULT_COLOR = "#6B7280"  # gray


def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def build_speaker_track_map(identity_map, camera_id="cam1"):
    """Resolve Stage-8 speaker identities to mapped tracks for one camera.

    Stage 8 retains weak mappings because they are eligible for segment selection. Rejected
    and unavailable candidates are deliberately not exposed as visual identities.
    """
    speaker_tracks = {}
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
            speaker_tracks[speaker_id] = track_id
    return speaker_tracks


def compute_speaker_stats(segments, identity_map, camera_id="cam1"):
    """Compute per-speaker talk time, segment count, and visual track mapping."""
    speaker_stats = defaultdict(lambda: {"total_talk_time": 0.0, "segment_count": 0, "visual_track": None})

    speaker_tracks = build_speaker_track_map(identity_map, camera_id)

    total_talk = 0.0
    for seg in segments:
        spk = seg.get("speaker") or (seg.get("words", [{}])[0].get("speaker") if seg.get("words") else None)
        if not spk:
            continue
        duration = seg["end"] - seg["start"]
        speaker_stats[spk]["total_talk_time"] += duration
        speaker_stats[spk]["segment_count"] += 1
        total_talk += duration

    speakers = {}
    for spk, stats in speaker_stats.items():
        speakers[spk] = {
            "color": SPEAKER_COLORS.get(spk, DEFAULT_COLOR),
            "label": SPEAKER_LABELS.get(spk, spk),
            "visual_track": speaker_tracks.get(spk),
            "total_talk_time": round(stats["total_talk_time"], 1),
            "segment_count": stats["segment_count"],
            "talk_percentage": round(stats["total_talk_time"] / total_talk * 100, 1) if total_talk > 0 else 0,
        }
    return speakers


def build_timeline_segments(segments):
    """Add color to each segment for timeline display."""
    timeline = []
    for seg in segments:
        spk = seg.get("speaker") or (seg.get("words", [{}])[0].get("speaker") if seg.get("words") else None)
        if not spk:
            continue
        timeline.append({
            "start": seg["start"],
            "end": seg["end"],
            "speaker": spk,
            "text": seg["text"].strip(),
            "color": SPEAKER_COLORS.get(spk, DEFAULT_COLOR),
        })
    return timeline


def build_selected_attention_segments(best_angles, camera_id="cam1"):
    """Translate Stage-3 assignments into the legacy attention function's interval shape."""
    selected = []
    for segment in best_angles.get("segments", []):
        if segment.get("selected_camera_id") != camera_id:
            continue
        track_id = segment.get("selected_track_id")
        if not isinstance(track_id, str) or not track_id:
            raise ValueError(
                f"Stage-3 segment {segment.get('transcript_segment_id')} selected "
                f"{camera_id} without selected_track_id"
            )
        selected.append({
            "speaker": segment.get("speaker_id"),
            "start": segment["start_seconds"],
            "end": segment["end_seconds"],
            "selected_track_id": track_id,
        })
    return selected


def compute_turn_taking(segments):
    """Compute turn-taking transitions and gap/overlap stats."""
    transitions = defaultdict(int)
    gaps = []
    overlaps = []

    speakers_in_order = []
    for seg in segments:
        spk = seg.get("speaker") or (seg.get("words", [{}])[0].get("speaker") if seg.get("words") else None)
        if spk:
            speakers_in_order.append((spk, seg["start"], seg["end"]))

    for i in range(1, len(speakers_in_order)):
        prev_spk, _, prev_end = speakers_in_order[i - 1]
        curr_spk, curr_start, _ = speakers_in_order[i]

        if prev_spk != curr_spk:
            key = f"{prev_spk}->{curr_spk}"
            transitions[key] += 1

            gap = curr_start - prev_end
            if gap > 0:
                gaps.append(gap)
            elif gap < 0:
                overlaps.append(abs(gap))

    return {
        "transitions": dict(transitions),
        "avg_gap_seconds": round(sum(gaps) / len(gaps), 2) if gaps else 0,
        "avg_overlap_seconds": round(sum(overlaps) / len(overlaps), 2) if overlaps else 0,
    }


def compute_attention(segments, head_pose_data, speaker_tracks, fps=None):
    """
    Compute attention metrics:
    - When speaker X talks, check if other tracks' yaw points toward speaker X's bbox
    - Gaze distribution per track (left/center/right)
    """
    tracks = head_pose_data.get("tracks", {})

    # Build frame->pose index per track for fast lookup
    track_poses = {}
    for track_id, track_data in tracks.items():
        poses = track_data if isinstance(track_data, list) else track_data.get("poses", [])
        frame_map = {}
        for p in poses:
            frame_map[p["frame"]] = p
        track_poses[track_id] = frame_map

    # Compute speaker attention received
    speaker_attention = defaultdict(lambda: {"attending": 0, "total": 0})

    for seg in segments:
        spk = seg.get("speaker") or (seg.get("words", [{}])[0].get("speaker") if seg.get("words") else None)
        if not spk:
            continue

        spk_track = str(seg.get("selected_track_id") or speaker_tracks.get(spk, ""))
        if spk_track not in track_poses:
            continue

        start_frame = int(seg["start"] * fps)
        end_frame = int(seg["end"] * fps)
        sample_rate = 5  # sample every 5 frames

        for frame in range(start_frame, end_frame, sample_rate):
            # Get speaker's bbox center x
            spk_pose = track_poses.get(spk_track, {}).get(frame)
            if not spk_pose:
                # Find nearest frame
                nearest = min(track_poses.get(spk_track, {}).keys(),
                              key=lambda f: abs(f - frame), default=None)
                if nearest and abs(nearest - frame) < 25:
                    spk_pose = track_poses[spk_track][nearest]
                else:
                    continue

            spk_cx = (spk_pose["bbox"][0] + spk_pose["bbox"][2]) / 2

            # Check other tracks
            for other_track_id, other_frame_map in track_poses.items():
                if other_track_id == spk_track:
                    continue

                other_pose = other_frame_map.get(frame)
                if not other_pose:
                    nearest = min(other_frame_map.keys(),
                                  key=lambda f: abs(f - frame), default=None)
                    if nearest and abs(nearest - frame) < 25:
                        other_pose = other_frame_map[nearest]
                    else:
                        continue

                other_cx = (other_pose["bbox"][0] + other_pose["bbox"][2]) / 2
                yaw = other_pose["yaw"]

                # Determine if looking toward speaker
                # If speaker is to the right (higher x), yaw should be positive (turning right)
                # If speaker is to the left (lower x), yaw should be negative (turning left)
                direction_to_speaker = spk_cx - other_cx
                looking_toward = (direction_to_speaker > 0 and yaw > -30) or \
                                 (direction_to_speaker < 0 and yaw < 30) or \
                                 (abs(direction_to_speaker) < 100)  # close together = facing

                speaker_attention[spk]["total"] += 1
                if looking_toward:
                    speaker_attention[spk]["attending"] += 1

    attention_received = {}
    for spk, data in speaker_attention.items():
        attention_received[spk] = {
            "avg_attention": round(data["attending"] / data["total"], 2) if data["total"] > 0 else 0,
            "samples": data["total"],
        }

    # Gaze distribution per track
    gaze_dist = {}
    for track_id, frame_map in track_poses.items():
        left = center = right = 0
        for pose in frame_map.values():
            yaw = pose["yaw"]
            if yaw < -20:
                left += 1
            elif yaw > 20:
                right += 1
            else:
                center += 1
        total = left + center + right
        if total > 0:
            gaze_dist[f"Track_{track_id}"] = {
                "left": round(left / total * 100),
                "center": round(center / total * 100),
                "right": round(right / total * 100),
            }

    return {
        "speaker_attention_received": attention_received,
        "gaze_distribution": gaze_dist,
    }


def detect_insights(segments, turn_taking):
    """Detect interesting moments: long silences, rapid exchanges, dominance shifts."""
    insights = []

    # Build ordered speaker segments
    ordered = []
    for seg in segments:
        spk = seg.get("speaker") or (seg.get("words", [{}])[0].get("speaker") if seg.get("words") else None)
        if spk:
            ordered.append((spk, seg["start"], seg["end"], seg["text"].strip()))

    # 1. Long silences (gaps > 3s)
    for i in range(1, len(ordered)):
        _, _, prev_end, prev_text = ordered[i - 1]
        _, curr_start, _, _ = ordered[i]
        gap = curr_start - prev_end
        if gap > 3.0:
            insights.append({
                "type": "long_silence",
                "timestamp": round(prev_end, 1),
                "duration": round(gap, 1),
                "description": f"{gap:.1f}s silence after \"{prev_text[:50]}{'...' if len(prev_text) > 50 else ''}\"",
            })

    # 2. Rapid exchanges (> 3 speaker changes in 10s)
    for i in range(len(ordered)):
        window_start = ordered[i][1]
        window_end = window_start + 10.0
        changes = 0
        prev_spk = None
        for j in range(i, len(ordered)):
            if ordered[j][1] > window_end:
                break
            if prev_spk and ordered[j][0] != prev_spk:
                changes += 1
            prev_spk = ordered[j][0]
        if changes >= 4:
            # Avoid duplicate insights within 15s
            already = any(
                ins["type"] == "rapid_exchange" and abs(ins["timestamp"] - window_start) < 15
                for ins in insights
            )
            if not already:
                insights.append({
                    "type": "rapid_exchange",
                    "timestamp": round(window_start, 1),
                    "description": f"{changes} speaker changes in 10 seconds",
                })

    # 3. Dominance shifts (sliding window 60s)
    if ordered:
        total_end = max(s[2] for s in ordered)
        window_size = 60.0
        step = 30.0
        prev_leader = None
        t = ordered[0][1]
        while t + window_size <= total_end:
            talk_in_window = defaultdict(float)
            for spk, start, end, _ in ordered:
                overlap_start = max(start, t)
                overlap_end = min(end, t + window_size)
                if overlap_start < overlap_end:
                    talk_in_window[spk] += overlap_end - overlap_start
            if talk_in_window:
                leader = max(talk_in_window, key=talk_in_window.get)
                if prev_leader and leader != prev_leader:
                    already = any(
                        ins["type"] == "dominance_shift" and abs(ins["timestamp"] - t) < 30
                        for ins in insights
                    )
                    if not already:
                        insights.append({
                            "type": "dominance_shift",
                            "timestamp": round(t, 1),
                            "description": f"{SPEAKER_LABELS.get(leader, leader)} takes over from {SPEAKER_LABELS.get(prev_leader, prev_leader)}",
                        })
                prev_leader = leader
            t += step

    # Sort by timestamp
    insights.sort(key=lambda x: x["timestamp"])
    return insights


def load_gaze_attention(gaze_tracks_path: Path) -> dict:
    """
    Read gaze_tracks.json if present and extract per-speaker gaze attention summary.
    Returns {} if file not found.
    """
    path = gaze_tracks_path
    if not path.exists():
        return {}

    with open(path) as f:
        gaze = json.load(f)

    attention = {}
    for track_id, track_data in gaze["tracks"].items():
        spk = track_data.get("speaker")
        if spk and track_data.get("summary"):
            attention[spk] = track_data["summary"]

    return attention


def main(session_id: str = None):
    paths = _get_paths(session_id)

    print("Loading data files...")
    diarized = load_json(paths["diarized_transcript"])
    identity_map = load_json(paths["identity_map"])
    best_angles = load_json(paths["best_angles"])
    head_pose = load_json(paths["head_pose"])

    segments = diarized["segments"]
    print(f"  Diarized segments: {len(segments)}")
    print(f"  Stage-8 speaker identities: {len(identity_map.get('speakers', []))}")
    print(f"  Stage-3 angle assignments: {len(best_angles.get('segments', []))}")
    print(f"  Head pose tracks: {len(head_pose.get('tracks', {}))}")

    # Speaker stats
    print("Computing speaker stats...")
    speakers = compute_speaker_stats(segments, identity_map, camera_id="cam1")
    print(f"  Found {len(speakers)} speakers")

    # Build speaker_tracks mapping for attention
    speaker_tracks = {spk: info["visual_track"] for spk, info in speakers.items() if info["visual_track"] is not None}

    # Timeline segments
    print("Building timeline segments...")
    timeline = build_timeline_segments(segments)

    # Turn taking
    print("Computing turn-taking...")
    turn_taking = compute_turn_taking(segments)
    print(f"  Transitions: {len(turn_taking['transitions'])}")

    # Attention analysis
    print("Computing attention analysis...")
    # Stale artifacts predate the fps fix; refuse them rather than assume 25.0.
    fps = head_pose.get("metadata", {}).get("fps")
    if not fps or fps <= 0:
        raise SystemExit("head_pose metadata has no usable fps; regenerate stage 3 (head pose)")
    attention_segments = build_selected_attention_segments(best_angles, camera_id="cam1")
    attention = compute_attention(attention_segments, head_pose, speaker_tracks, fps)
    print(f"  Attention data for {len(attention['speaker_attention_received'])} speakers")
    print(f"  Gaze data for {len(attention['gaze_distribution'])} tracks")

    # Insights
    print("Detecting insights...")
    insights = detect_insights(segments, turn_taking)
    print(f"  Found {len(insights)} insights")

    result = {
        "speakers": speakers,
        "timeline_segments": timeline,
        "turn_taking": turn_taking,
        "attention": attention,
        "insights": insights,
    }

    # Optionally enrich with gaze attention
    gaze_attention = load_gaze_attention(paths["gaze_tracks"])
    if gaze_attention:
        result["gaze_attention"] = gaze_attention
        print(f"  Added gaze_attention for {len(gaze_attention)} speakers")

    output_path = paths["output_interaction_analytics"]
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nSaved to {output_path}")
    print(f"  Total size: {output_path.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute interaction analytics")
    parser.add_argument("--session-id", default=None, help="Session ID (omit for legacy paths)")
    args = parser.parse_args()
    main(session_id=args.session_id)
