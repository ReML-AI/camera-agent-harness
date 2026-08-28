#!/usr/bin/env python3
"""Stage 11: Detect team-level gaze attention events.

Reads gaze_tracks.json and diarization, outputs gaze_events.json with
convergence, divergence, and sustained-patient events.

Usage:
    python3 scripts/analytics/compute_gaze_events.py --session-id session_001
"""
import json
import argparse
from collections import defaultdict, Counter

try:
    from scripts.utils.session_paths import raw_dir, processed_dir
except ImportError:
    from pathlib import Path as _P
    _ROOT = _P(__file__).resolve().parent.parent.parent
    def raw_dir(sid): return _ROOT / "data" / "sessions" / sid / "raw"
    def processed_dir(sid): return _ROOT / "data" / "sessions" / sid / "processed"


def _normalize_tracks(gaze_data):
    """Adapt the stage-9 gaze_tracks.json schema to the list-of-tracks the
    detectors expect: [{"speaker", "frames": [{"timestamp", "target"}]}].

    Stage 9 stores tracks as a dict keyed by track id, per-frame samples under
    "poses", and the gaze target under "gaze_target". Unlinked tracks have
    speaker=None, so we fall back to the track id as the viewer identity.
    """
    raw = gaze_data.get("tracks", [])
    items = raw.items() if isinstance(raw, dict) else enumerate(raw)
    normalized = []
    for tid, tv in items:
        if not isinstance(tv, dict):
            continue
        speaker = tv.get("speaker") or f"track_{tid}"
        # Only gate-positive samples are evidence. These events are placed directly into
        # M's visual-attention context, so an ungated sample here lets M differ from T for
        # a reason the declared method says does not propagate.
        frames = [
            {"timestamp": p.get("timestamp", 0),
             "target": p.get("gaze_target", p.get("target", "other"))}
            for p in tv.get("poses", tv.get("frames", []))
            if p.get("exact_frame_gate") == "exact_frame_asd_positive"
        ]
        if not frames:
            continue
        normalized.append({"speaker": speaker, "frames": frames})
    return normalized


def _bin_gaze_by_time(tracks, bin_sec=1.0):
    """Group gaze samples into time bins. Returns {time_bin: {speaker: [targets]}}."""
    bins = defaultdict(lambda: defaultdict(list))
    for track in tracks:
        speaker = track.get("speaker", "UNKNOWN")
        for frame in track.get("frames", []):
            t = frame.get("timestamp", 0)
            target = frame.get("target", "other")
            time_bin = round(t / bin_sec) * bin_sec
            bins[time_bin][speaker].append(target)
    return bins


def detect_convergence_events(tracks, min_speakers=3, time_window_sec=5.0, bin_sec=1.0):
    """Detect when >= min_speakers shift gaze to the same target within a time window."""
    bins = _bin_gaze_by_time(tracks, bin_sec)
    sorted_times = sorted(bins.keys())
    events = []
    used_times = set()

    for t in sorted_times:
        if t in used_times:
            continue
        window_end = t + time_window_sec
        speaker_targets = {}
        for t2 in sorted_times:
            if t2 < t or t2 > window_end:
                continue
            for speaker, targets in bins[t2].items():
                if speaker not in speaker_targets:
                    speaker_targets[speaker] = Counter()
                speaker_targets[speaker].update(targets)

        if len(speaker_targets) < min_speakers:
            continue

        majority_targets = {
            sp: counter.most_common(1)[0][0]
            for sp, counter in speaker_targets.items()
        }
        target_counts = Counter(majority_targets.values())
        best_target, count = target_counts.most_common(1)[0]

        if count >= min_speakers and best_target != "other":
            events.append({
                "type": "convergence",
                "timestamp": round(t, 1),
                "duration": round(time_window_sec, 1),
                "target": best_target,
                "speakers_involved": [s for s, tgt in majority_targets.items() if tgt == best_target],
                "confidence": round(count / len(speaker_targets), 2),
            })
            for t2 in sorted_times:
                if t <= t2 <= window_end:
                    used_times.add(t2)

    return events


def detect_divergence_events(tracks, min_speakers=3, time_window_sec=5.0, bin_sec=1.0):
    """Detect when team gaze shifts from aligned to scattered within a time window.

    Looks for consecutive windows where gaze was converged (one dominant target)
    followed by scattered (no dominant target).
    """
    bins = _bin_gaze_by_time(tracks, bin_sec)
    sorted_times = sorted(bins.keys())
    events = []
    used_times = set()

    for i, t in enumerate(sorted_times):
        if t in used_times:
            continue
        # Check if gaze is converged at time t
        speaker_targets_now = {}
        window_end = t + time_window_sec
        for t2 in sorted_times:
            if t2 < t or t2 > t + time_window_sec / 2:
                continue
            for speaker, targets in bins[t2].items():
                if speaker not in speaker_targets_now:
                    speaker_targets_now[speaker] = Counter()
                speaker_targets_now[speaker].update(targets)

        if len(speaker_targets_now) < min_speakers:
            continue

        majority_now = {sp: c.most_common(1)[0][0] for sp, c in speaker_targets_now.items()}
        target_counts_now = Counter(majority_now.values())
        best_now, count_now = target_counts_now.most_common(1)[0]
        convergence_ratio = count_now / len(speaker_targets_now)

        if convergence_ratio < 0.7:
            continue

        # Check if gaze is scattered in next window
        speaker_targets_next = {}
        for t2 in sorted_times:
            if t2 < t + time_window_sec / 2 or t2 > window_end:
                continue
            for speaker, targets in bins[t2].items():
                if speaker not in speaker_targets_next:
                    speaker_targets_next[speaker] = Counter()
                speaker_targets_next[speaker].update(targets)

        if len(speaker_targets_next) < min_speakers:
            continue

        majority_next = {sp: c.most_common(1)[0][0] for sp, c in speaker_targets_next.items()}
        target_counts_next = Counter(majority_next.values())
        _, count_next = target_counts_next.most_common(1)[0]
        scatter_ratio = count_next / len(speaker_targets_next)

        if scatter_ratio < 0.5:  # Now scattered (no clear majority)
            events.append({
                "type": "divergence",
                "timestamp": round(t, 1),
                "duration": round(time_window_sec, 1),
                "from_target": best_now,
                "speakers_involved": sorted(speaker_targets_now.keys()),
                "confidence": round(convergence_ratio - scatter_ratio, 2),
            })
            for t2 in sorted_times:
                if t <= t2 <= window_end:
                    used_times.add(t2)

    return events


def detect_sustained_patient(tracks, min_duration_sec=10.0):
    """Detect when all tracked speakers look at patient for extended time."""
    bins = _bin_gaze_by_time(tracks, bin_sec=1.0)
    sorted_times = sorted(bins.keys())
    events = []
    streak_start = None
    streak_speakers = set()

    for t in sorted_times:
        all_patient = True
        current_speakers = set()
        for speaker, targets in bins[t].items():
            current_speakers.add(speaker)
            most_common = Counter(targets).most_common(1)[0][0]
            if most_common != "patient":
                all_patient = False
                break

        if all_patient and len(current_speakers) >= 2:
            if streak_start is None:
                streak_start = t
                streak_speakers = current_speakers
            else:
                streak_speakers |= current_speakers
        else:
            if streak_start is not None and (t - streak_start) >= min_duration_sec:
                events.append({
                    "type": "sustained_patient", "timestamp": round(streak_start, 1),
                    "duration": round(t - streak_start, 1), "target": "patient",
                    "speakers_involved": sorted(streak_speakers), "confidence": 0.7,
                })
            streak_start = None
            streak_speakers = set()

    # Flush any open streak at end of data
    if streak_start is not None and sorted_times and (sorted_times[-1] - streak_start) >= min_duration_sec:
        events.append({
            "type": "sustained_patient", "timestamp": round(streak_start, 1),
            "duration": round(sorted_times[-1] - streak_start, 1), "target": "patient",
            "speakers_involved": sorted(streak_speakers), "confidence": 0.7,
        })

    return events


def compute_all_events(gaze_data, speech_segments):
    """Run all event detectors and return combined list sorted by timestamp."""
    tracks = _normalize_tracks(gaze_data)
    events = []
    events.extend(detect_convergence_events(tracks))
    events.extend(detect_divergence_events(tracks))
    events.extend(detect_sustained_patient(tracks))
    events.sort(key=lambda e: e["timestamp"])
    return events


def main():
    parser = argparse.ArgumentParser(description="Detect team-level gaze events")
    parser.add_argument("--session-id", required=True)
    args = parser.parse_args()

    gaze_path = raw_dir(args.session_id) / "gaze_tracks.json"
    transcript_path = raw_dir(args.session_id) / "diarized_transcript_full.json"

    with open(gaze_path) as f:
        gaze_data = json.load(f)
    with open(transcript_path) as f:
        transcript_data = json.load(f)

    events = compute_all_events(gaze_data, transcript_data["segments"])

    output = {"session_id": args.session_id, "events": events}
    out_path = processed_dir(args.session_id) / "gaze_events.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Detected {len(events)} gaze events -> {out_path}")


if __name__ == "__main__":
    main()
