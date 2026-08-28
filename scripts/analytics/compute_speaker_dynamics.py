#!/usr/bin/env python3
"""Stage 10: Compute per-window speaker dynamics from diarization.

Produces speaker_dynamics.json with turn-taking, silence, overlap,
and speech rate signals per time window.

Usage:
    python3 scripts/analytics/compute_speaker_dynamics.py --session-id session_001
"""
import json
import argparse
from collections import Counter

try:
    from scripts.utils.session_paths import raw_dir, processed_dir
except ImportError:
    from pathlib import Path as _P
    _ROOT = _P(__file__).resolve().parent.parent.parent
    def raw_dir(sid): return _ROOT / "data" / "sessions" / sid / "raw"
    def processed_dir(sid): return _ROOT / "data" / "sessions" / sid / "processed"


def compute_dynamics_for_window(segments, win_start, win_end):
    """Compute speech dynamics for a single time window."""
    in_window = []
    for seg in segments:
        seg_start = max(seg["start"], win_start)
        seg_end = min(seg["end"], win_end)
        if seg_start < seg_end:
            in_window.append({
                "speaker": seg.get("speaker", "UNKNOWN"),
                "start": seg_start, "end": seg_end,
                "text": seg.get("text", ""),
            })
    in_window.sort(key=lambda item: (item["start"], item["end"], item["speaker"]))

    if not in_window:
        return {
            "turn_count": 0, "speaker_count": 0, "overlap_pct": 0.0,
            "silence_before_sec": 0.0, "dominant_speaker": None,
            "speech_rate_wps": 0.0, "pattern": "silence",
        }

    turn_count = 1
    for i in range(1, len(in_window)):
        if in_window[i]["speaker"] != in_window[i - 1]["speaker"]:
            turn_count += 1

    speakers = set(seg["speaker"] for seg in in_window)
    speaker_count = len(speakers)

    talk_time = Counter()
    for seg in in_window:
        talk_time[seg["speaker"]] += seg["end"] - seg["start"]
    total_talk = sum(talk_time.values())
    dominant_speaker = talk_time.most_common(1)[0][0] if talk_time else None
    dominant_pct = (talk_time.most_common(1)[0][1] / total_talk * 100) if total_talk > 0 else 0

    # Integrate time with at least two distinct active speakers. Pairwise sums would
    # double-count the same wall-clock interval when three or more speakers overlap.
    boundaries = sorted({
        point for segment in in_window for point in (segment["start"], segment["end"])
    })
    overlap_sec = 0.0
    for start, end in zip(boundaries, boundaries[1:]):
        active_speakers = {
            segment["speaker"] for segment in in_window
            if segment["start"] < end and segment["end"] > start
        }
        if len(active_speakers) >= 2:
            overlap_sec += end - start
    win_dur = win_end - win_start
    overlap_pct = (overlap_sec / win_dur * 100) if win_dur > 0 else 0.0

    silence_before = in_window[0]["start"] - win_start

    word_count = sum(len(seg["text"].split()) for seg in in_window)
    speech_rate = word_count / total_talk if total_talk > 0 else 0.0

    pattern = classify_pattern(turn_count, speaker_count, overlap_pct, silence_before, dominant_pct)

    return {
        "turn_count": turn_count, "speaker_count": speaker_count,
        "overlap_pct": round(overlap_pct, 1), "silence_before_sec": round(silence_before, 1),
        "dominant_speaker": dominant_speaker, "speech_rate_wps": round(speech_rate, 1),
        "pattern": pattern,
    }


def classify_pattern(turn_count, speaker_count, overlap_pct, silence_before, dominant_pct):
    """Classify window speech pattern (rule-based)."""
    if silence_before > 8.0:
        return "silence_break"
    if overlap_pct > 20:
        return "overlapping"
    if turn_count > 4 and speaker_count >= 2:
        return "rapid_exchange"
    if dominant_pct > 80:
        return "monologue"
    return "normal"


def compute_all_windows(segments, window_sec=30, slide_sec=15):
    """Compute dynamics for all sliding windows across the session."""
    if not segments:
        return []
    session_end = max(seg["end"] for seg in segments)
    windows = []
    win_start = 0.0
    win_id = 0
    while win_start < session_end:
        win_end = min(win_start + window_sec, session_end)
        dynamics = compute_dynamics_for_window(segments, win_start, win_end)
        dynamics["window_id"] = f"speaker-dynamics-{win_id:06d}"
        dynamics["definition_id"] = "SPEAKER-DYNAMICS-001"
        dynamics["start"] = win_start
        dynamics["end"] = win_end
        windows.append(dynamics)
        win_start += slide_sec
        win_id += 1
    return windows


def main():
    parser = argparse.ArgumentParser(description="Compute per-window speaker dynamics")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--window-sec", type=int, default=30)
    parser.add_argument("--slide-sec", type=int, default=15)
    args = parser.parse_args()

    transcript_path = raw_dir(args.session_id) / "diarized_transcript_full.json"
    with open(transcript_path) as f:
        segments = json.load(f)["segments"]

    windows = compute_all_windows(segments, args.window_sec, args.slide_sec)

    output = {
        "session_id": args.session_id,
        "window_duration_sec": args.window_sec,
        "slide_sec": args.slide_sec,
        "total_windows": len(windows),
        "windows": windows,
    }
    out_path = processed_dir(args.session_id) / "speaker_dynamics.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Wrote {len(windows)} windows to {out_path}")


if __name__ == "__main__":
    main()
