#!/usr/bin/env python3
"""
Stage 1: Moment-Level Cross-Modal Context Extraction.

Reads fused critical moments from the evidence-based pipeline (CLIP + EasyOCR + transcript),
then cross-references each moment with:
- Diarized transcript (who was talking)
- Gaze tracks (where each person was looking)
- Vitals timeline (patient vital signs)
- Interaction insights (auto-detected patterns)

Outputs: data/processed/moment_contexts.json
"""

import re
import json
import argparse
from pathlib import Path
from collections import Counter

# Legacy defaults (backward compat when no --session-id)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_LEGACY_DATA_DIR = _PROJECT_ROOT / "data" / "processed"
_LEGACY_OUTPUT_DIR = _PROJECT_ROOT / "data" / "output"

# The focal stage keys its output by condition. M is the full multimodal system, which is
# what the downstream context, narratives and overlay describe; T is the transcript-only
# ablation and is reported separately rather than consumed here.
CONDITION_MULTIMODAL = "M"


def _get_paths(session_id: str = None) -> dict:
    """Return dict of paths, using session_paths when session_id is provided."""
    if session_id is not None:
        from scripts.utils.session_paths import raw_dir, processed_dir
        _raw = raw_dir(session_id)
        _processed = processed_dir(session_id)
        return {
            "moments": _processed / "moments_multimodal.json",
            "diarized_transcript": _raw / "diarized_transcript_full.json",
            "gaze_tracks": _raw / "gaze_tracks.json",
            "vitals": _raw / "monitor_vitals.json",
            "interaction_analytics": _processed / "interaction_analytics.json",
            "output_moment_contexts": _processed / "moment_contexts.json",
        }
    # Legacy paths
    return {
        "moments": _LEGACY_OUTPUT_DIR / "critical_moments.json",
        "diarized_transcript": _LEGACY_DATA_DIR / "diarized_transcript_full.json",
        "gaze_tracks": _LEGACY_DATA_DIR / "gaze_tracks.json",
        "vitals": _LEGACY_DATA_DIR / "monitor_vitals_fixed.json",
        "interaction_analytics": _LEGACY_DATA_DIR / "interaction_analytics.json",
        "output_moment_contexts": _LEGACY_DATA_DIR / "moment_contexts.json",
    }

# Canonical gaze target categories
GAZE_TARGET_MAP = {
    'patient': 'patient',
    'monitor': 'monitor',
    'other': 'other',
    'person': 'person',  # colleague/team member
}

# Patterns that should map to "person"
_TRACK_ID_RE = re.compile(r'^track_\d+$')
_SPEAKER_LABEL_RE = re.compile(r'^Speaker \w+$', re.IGNORECASE)
_SPEAKER_ID_RE = re.compile(r'^speaker_\d+$', re.IGNORECASE)


def _normalize_gaze_target(target: str) -> str:
    r"""Map a raw gaze target to a canonical category.

    - track_\d+        -> "person"
    - Speaker \w+      -> "person"
    - speaker_\d+      -> "person"
    - patient/monitor/other/person -> kept as-is
    - anything else    -> "other"
    """
    if target in GAZE_TARGET_MAP:
        return target
    if _TRACK_ID_RE.match(target) or _SPEAKER_LABEL_RE.match(target) or _SPEAKER_ID_RE.match(target):
        return 'person'
    return 'other'


def _normalize_gaze_distribution(raw_distribution: dict) -> dict:
    """Remap and merge a {target: pct} distribution using canonical categories.

    Takes a dict like {"patient": 40.0, "track_52": 30.0, "Speaker A": 30.0}
    and returns {"patient": 40.0, "person": 60.0}.
    Percentages are re-normalized so they sum to 100%.
    """
    merged: dict[str, float] = {}
    for target, value in raw_distribution.items():
        canonical = _normalize_gaze_target(target)
        merged[canonical] = merged.get(canonical, 0.0) + value
    # Re-normalize to account for floating-point drift after merging
    total = sum(merged.values())
    if total > 0:
        merged = {k: round(v / total * 100, 1) for k, v in merged.items()}
    return merged


def _derive_category(moment: dict) -> tuple:
    """Derive category and action_type from fused moment sources."""
    sources = moment.get("sources", {})

    # Transcript: emergency keyword takes highest priority
    transcript = sources.get("transcript", {})
    if transcript.get("detected"):
        for item in transcript.get("data", []):
            if "emergency" in item.get("categories", []):
                return "Emergency Recognition", "emergency_recognition"

    # Video sources: CPR/compressions = Emergency Response
    for key, src in sources.items():
        if key.startswith("video_") and src.get("detected"):
            for item in src.get("data", []):
                desc = item.get("description", "").lower()
                if "cpr" in desc or "compression" in desc:
                    return "Emergency Response", "emergency_response"

    # Monitor OCR anomalies = Vital Sign Anomaly
    if sources.get("monitor_ocr", {}).get("detected"):
        return "Vital Sign Anomaly", "vital_sign_anomaly"

    # Video: running/gathering = Emergency Response
    for key, src in sources.items():
        if key.startswith("video_") and src.get("detected"):
            return "Emergency Response", "emergency_response"

    # Transcript: actions category
    if transcript.get("detected"):
        return "Clinical Action", "clinical_action"

    return "Clinical Observation", "clinical_observation"


def load_moments(paths: dict) -> list:
    """Load moments from either legacy critical_moments or pipeline moments_multimodal format."""
    with open(paths["moments"]) as f:
        data = json.load(f)

    # Current format: the focal stage emits one entry per condition, so the moments live
    # under data["M"]["moments"] rather than at the top level. M is the full multimodal
    # system; T is the transcript-only ablation, so downstream context and narratives — the
    # system's own outputs — are built from M. Fields are the canonical *_seconds names.
    if CONDITION_MULTIMODAL in data and isinstance(data[CONDITION_MULTIMODAL], dict):
        raw = sorted(
            data[CONDITION_MULTIMODAL].get("moments", []),
            key=lambda m: m.get("start_seconds", 0),
        )
        print(f"  {len(raw)} moments (condition {CONDITION_MULTIMODAL}, focal LLM detection)")
        moments = []
        for m in raw:
            category = m.get("category", "Clinical Observation")
            evidence = m.get("evidence_ids", [])
            moments.append({
                "timestamp": m["start_seconds"],
                "end_timestamp": m["end_seconds"],
                "importance": "high",
                "category": category,
                "action_type": category.lower().replace(" ", "_"),
                "text": m.get("description", ""),
                "evidence": evidence,
                # The focal contract carries no per-moment confidence, and inventing one
                # would put a fabricated number into a reported artifact.
                "confidence": None,
                "num_sources": len(evidence),
                "categories": [{
                    "category": category,
                    "action_type": category.lower().replace(" ", "_"),
                    "importance": "high",
                }],
            })
        return moments

    # Pipeline format (moments_multimodal.json from the focal runner)
    if "moments" in data:
        raw = data["moments"]
        raw.sort(key=lambda m: m.get("start", 0))
        print(f"  {len(raw)} moments (from pipeline LLM detection)")
        moments = []
        for m in raw:
            category = m.get("category", "Clinical Observation")
            moment = {
                "timestamp": m["start"],
                "end_timestamp": m["end"],
                "importance": "high",
                "category": category,
                "action_type": category.lower().replace(" ", "_"),
                "text": m.get("description", ""),
                "evidence": m.get("evidence_sources", ["transcript"]),
                "confidence": m.get("confidence", 0.5),
                "num_sources": len(m.get("evidence_sources", ["transcript"])),
                "categories": [{
                    "category": category,
                    "action_type": category.lower().replace(" ", "_"),
                    "importance": "high",
                }],
            }
            moments.append(moment)
        return moments

    # Legacy format (critical_moments.json from evidence-based pipeline)
    raw = data["critical_moments"]
    raw.sort(key=lambda m: m["start_time"])
    print(f"  {len(raw)} fused moments (from evidence-based pipeline)")

    moments = []
    for m in raw:
        category, action_type = _derive_category(m)
        importance = "critical" if m["severity"] == "critical" else "high"
        moment = {
            "timestamp": m["start_time"],
            "end_timestamp": m["end_time"],
            "importance": importance,
            "category": category,
            "action_type": action_type,
            "text": m["summary"],
            "evidence": m["sources"],
            "confidence": m["confidence"],
            "num_sources": m["num_sources"],
            "categories": [{
                "category": category,
                "action_type": action_type,
                "importance": importance,
            }],
        }
        moments.append(moment)

    return moments


def load_transcript(paths: dict) -> list:
    """Load diarized transcript segments."""
    with open(paths["diarized_transcript"]) as f:
        data = json.load(f)
    return data["segments"]


def load_gaze_tracks(paths: dict) -> tuple:
    """Load classified gaze tracks.
    Returns (speaker_poses, all_poses):
    - speaker_poses: {speaker_id: [pose, ...]} for linked tracks only
    - all_poses: [pose, ...] from ALL 16 tracks (for team-level metrics)
    """
    with open(paths["gaze_tracks"]) as f:
        data = json.load(f)
    speaker_poses = {}
    all_poses = []
    for track_id, track_data in data["tracks"].items():
        # Only the exact-frame-ASD-gated population is evidence. This read every candidate,
        # so the narratives and per-speaker distributions here described attention the
        # method says does not propagate -- a different population from the one the focal
        # model was given and the one the paper reports.
        gated = [
            pose for pose in track_data["poses"]
            if pose.get("exact_frame_gate") == "exact_frame_asd_positive"
        ]
        spk = track_data.get("speaker")
        if spk:
            speaker_poses[spk] = gated
        # Collect the gated poses for team-level gaze metrics
        all_poses.extend(gated)
    all_poses.sort(key=lambda p: p["timestamp"])
    return speaker_poses, all_poses


def load_vitals(paths: dict) -> list:
    """Load vitals timeline. Returns list of readings with timestamps."""
    with open(paths["vitals"]) as f:
        data = json.load(f)
    return data.get("timeline", [])


def load_insights(paths: dict) -> list:
    """Load auto-detected interaction insights."""
    with open(paths["interaction_analytics"]) as f:
        data = json.load(f)
    return data.get("insights", [])


def extract_speech(moment: dict, transcript_segments: list) -> dict:
    """
    Find transcript segments overlapping the moment time window.
    Returns per-speaker talk time, utterances, and dynamics.
    """
    t_start = moment["timestamp"]
    t_end = moment["end_timestamp"]
    duration = t_end - t_start

    # Find overlapping segments
    overlapping = []
    for seg in transcript_segments:
        seg_start = seg["start"]
        seg_end = seg["end"]
        # Check overlap
        if seg_start < t_end and seg_end > t_start:
            # Clip to moment window
            clipped_start = max(seg_start, t_start)
            clipped_end = min(seg_end, t_end)
            clipped_duration = clipped_end - clipped_start
            if clipped_duration > 0:
                overlapping.append({
                    "speaker": seg.get("speaker", "UNKNOWN"),
                    "text": seg["text"],
                    "start": seg_start,
                    "end": seg_end,
                    "clipped_duration": round(clipped_duration, 2),
                })

    # Per-speaker aggregation
    per_speaker = {}
    for seg in overlapping:
        spk = seg["speaker"]
        if spk not in per_speaker:
            per_speaker[spk] = {
                "talk_time_seconds": 0.0,
                "talk_time_pct": 0.0,
                "utterances": [],
                "spoke_first": False,
            }
        per_speaker[spk]["talk_time_seconds"] += seg["clipped_duration"]
        per_speaker[spk]["utterances"].append(seg["text"])

    # Compute percentages and who spoke first
    total_talk = sum(s["talk_time_seconds"] for s in per_speaker.values())
    for spk, data in per_speaker.items():
        data["talk_time_seconds"] = round(data["talk_time_seconds"], 2)
        data["talk_time_pct"] = round(data["talk_time_seconds"] / duration * 100, 1) if duration > 0 else 0.0

    # Who spoke first
    if overlapping:
        first_speaker = min(overlapping, key=lambda s: s["start"])["speaker"]
        if first_speaker in per_speaker:
            per_speaker[first_speaker]["spoke_first"] = True

    # Silence = moment duration minus total talk time
    silence = max(0.0, duration - total_talk)

    # Count speaker transitions
    speakers_in_order = [seg["speaker"] for seg in sorted(overlapping, key=lambda s: s["start"])]
    transitions = sum(1 for i in range(1, len(speakers_in_order)) if speakers_in_order[i] != speakers_in_order[i-1])

    chronological = [
        {
            "speaker": seg["speaker"],
            "text": seg["text"],
            "start": round(seg["start"], 2),
        }
        for seg in sorted(overlapping, key=lambda s: s["start"])
    ]

    return {
        "active_speakers": list(per_speaker.keys()),
        "per_speaker": per_speaker,
        "chronological_utterances": chronological,
        "silence_seconds": round(silence, 2),
        "total_utterances": len(overlapping),
        "speaker_transitions": transitions,
        "_utterances": sorted(overlapping, key=lambda s: s["start"]),
    }


def extract_gaze(moment: dict, speaker_poses: dict, all_poses: list) -> dict:
    """
    Filter gaze poses to the moment time window.
    Returns:
    - per_speaker: gaze distribution for linked speakers only
    - team_gaze: gaze distribution from ALL tracks (linked + unlinked)
    - team_patient_attention_pct: from all tracks
    """
    t_start = moment["timestamp"]
    t_end = moment["end_timestamp"]

    # Per-speaker gaze (linked tracks only)
    per_speaker = {}
    for spk, poses in speaker_poses.items():
        window_poses = [p for p in poses if t_start <= p["timestamp"] <= t_end]
        if not window_poses:
            continue
        target_counts = Counter(p["gaze_target"] for p in window_poses)
        total = len(window_poses)
        raw_distribution = {target: round(count / total * 100, 1) for target, count in target_counts.items()}
        distribution = _normalize_gaze_distribution(raw_distribution)
        per_speaker[spk] = {**distribution, "samples": total}

    # Team-level gaze from ALL tracks (linked + unlinked)
    team_window = [p for p in all_poses if t_start <= p["timestamp"] <= t_end]
    team_samples = len(team_window)

    team_gaze = {}
    team_patient_pct = 0.0
    if team_samples > 0:
        team_counts = Counter(p["gaze_target"] for p in team_window)
        raw_team_gaze = {target: round(count / team_samples * 100, 1) for target, count in team_counts.items()}
        team_gaze = _normalize_gaze_distribution(raw_team_gaze)
        team_patient_pct = team_gaze.get("patient", 0.0)

    # Data quality: based on team-level (all tracks)
    quality = "sufficient" if team_samples >= 5 else ("insufficient" if team_samples > 0 else "no_data")

    return {
        "per_speaker": per_speaker,
        "team_gaze": team_gaze,
        "team_gaze_samples": team_samples,
        "team_patient_attention_pct": team_patient_pct,
        "data_quality": quality,
    }


def extract_vitals(moment: dict, vitals_timeline: list) -> dict:
    """
    Extract vital signs within the moment window.
    Returns start/end values and trends, or null if no data.
    """
    t_start = moment["timestamp"]
    t_end = moment["end_timestamp"]

    window = [v for v in vitals_timeline if t_start <= v["timestamp"] <= t_end]
    # Filter to entries with actual data
    window = [v for v in window if any(v.get(k) is not None for k in ["hr", "spo2", "bp_sys"])]

    if not window:
        return {
            "spo2": None,
            "heart_rate": None,
            "blood_pressure": None,
            "readings_in_window": 0,
        }

    def extract_vital(entries, key):
        values = [e[key] for e in entries if e.get(key) is not None]
        if not values:
            return None
        start_val = values[0]
        end_val = values[-1]
        if end_val < start_val - 2:
            trend = "declining"
        elif end_val > start_val + 2:
            trend = "rising"
        else:
            trend = "stable"
        return {"start": start_val, "end": end_val, "trend": trend}

    return {
        "spo2": extract_vital(window, "spo2"),
        "heart_rate": extract_vital(window, "hr"),
        "blood_pressure": extract_vital(window, "bp_sys"),
        "readings_in_window": len(window),
    }


def detect_closed_loop(utterances: list) -> bool:
    """Detect closed-loop communication: A->B->A pattern.

    Closed-loop = Speaker A says something, Speaker B responds/confirms,
    Speaker A speaks again (acknowledging). Requires at least 3 turns
    with the first speaker returning.
    """
    if len(utterances) < 3:
        return False

    # Get speaker sequence (deduplicate consecutive same-speaker)
    speaker_seq = []
    for u in utterances:
        spk = u.get("speaker") or u.get("speaker_id", "")
        if not speaker_seq or speaker_seq[-1] != spk:
            speaker_seq.append(spk)

    # Look for A->B->A pattern (any speaker returns after another speaks)
    if len(speaker_seq) >= 3:
        for i in range(len(speaker_seq) - 2):
            if speaker_seq[i] == speaker_seq[i + 2] and speaker_seq[i] != speaker_seq[i + 1]:
                return True

    return False


def extract_dynamics(moment: dict, speech: dict, insights: list) -> dict:
    """
    Compute team dynamics: response latency, closed-loop detection,
    silence gaps, and overlapping insights.
    """
    t_start = moment["timestamp"]
    t_end = moment["end_timestamp"]

    # Response latency: time from moment start to first utterance
    utterances = speech.get("_utterances", [])
    first_response = None
    if utterances:
        first_utterance_start = utterances[0]["start"]
        latency = first_utterance_start - t_start
        first_response = round(max(0.0, latency), 2)

    # Closed-loop detection: look for A->B->A speaker pattern
    closed_loop = detect_closed_loop(utterances)

    # Silence gaps >5s within the moment
    silence_gaps = []
    if speech["silence_seconds"] > 5.0:
        silence_gaps.append({"duration": speech["silence_seconds"]})

    # Overlapping insights
    overlapping = [
        {"type": ins["type"], "timestamp": ins["timestamp"], "description": ins["description"]}
        for ins in insights
        if t_start <= ins["timestamp"] <= t_end
    ]

    return {
        "first_response_latency_seconds": first_response,
        "closed_loop_detected": closed_loop,
        "silence_gaps": silence_gaps,
        "overlapping_insights": overlapping,
    }


def main(session_id: str = None):
    paths = _get_paths(session_id)
    # Clinical roles are governed labels and are not distributed with the public artifact.
    # Downstream consumers use stable speaker IDs unless an authorized application joins
    # role metadata outside this pipeline.
    speaker_roles = {}

    print("=" * 60)
    print("MOMENT-LEVEL CROSS-MODAL CONTEXT EXTRACTION")
    print("=" * 60)

    print("\n[1/5] Loading fused critical moments (CLIP + EasyOCR + transcript)...")
    moments = load_moments(paths)

    print("\n[2/5] Loading transcript...")
    transcript = load_transcript(paths)
    print(f"  {len(transcript)} segments")

    print("\n[3/5] Loading gaze tracks...")
    gaze, all_gaze_poses = load_gaze_tracks(paths)
    print(f"  {len(gaze)} speaker tracks, {len(all_gaze_poses)} total poses (all tracks)")

    print("\n[4/5] Loading vitals + insights...")
    vitals = load_vitals(paths)
    insights = load_insights(paths)
    print(f"  {len(vitals)} vitals entries, {len(insights)} insights")

    print("\n[5/5] Extracting context per moment...")
    results = []
    for i, moment in enumerate(moments):
        speech = extract_speech(moment, transcript)
        gaze_data = extract_gaze(moment, gaze, all_gaze_poses)
        vitals_data = extract_vitals(moment, vitals)
        dynamics = extract_dynamics(moment, speech, insights)

        # Remove the temporary aggregation field before serialization.
        speech.pop("_utterances", None)

        result = {
            "moment_id": i,
            "timestamp": moment["timestamp"],
            "end_timestamp": moment["end_timestamp"],
            "duration": round(moment["end_timestamp"] - moment["timestamp"], 2),
            "category": moment["category"],
            "importance": moment["importance"],
            "original_text": moment["text"],
            "action_type": moment.get("action_type"),
            "confidence": moment.get("confidence"),
            "num_sources": moment.get("num_sources"),
            "evidence": moment.get("evidence", {}),
            "categories": moment.get("categories", []),
            "speech": speech,
            "gaze": gaze_data,
            "vitals": vitals_data,
            "dynamics": dynamics,
        }
        results.append(result)

        if (i + 1) % 10 == 0:
            print(f"  Processed {i + 1}/{len(moments)} moments")

    output = {
        "metadata": {
            "total_moments": len(results),
            "pipeline": "fused_evidence",
            "generated_at": __import__("datetime").datetime.now().isoformat(),
            "source_files": {
                "moments": "data/output/critical_moments.json",
                "transcript": "data/processed/diarized_transcript_full.json",
                "gaze": "data/processed/gaze_tracks.json",
                "vitals": "data/processed/monitor_vitals_fixed.json",
            },
        },
        "speaker_roles": speaker_roles,
        "moments": results,
    }

    output_path = paths["output_moment_contexts"]
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved {len(results)} moment contexts")
    print(f"Output: {output_path} ({output_path.stat().st_size / 1024:.1f} KB)")

    # Summary stats
    with_speech = sum(1 for r in results if r["speech"]["active_speakers"])
    with_gaze = sum(1 for r in results if r["gaze"]["data_quality"] != "no_data")
    with_vitals = sum(1 for r in results if r["vitals"]["readings_in_window"] > 0)
    print(f"\nCoverage: {with_speech} with speech, {with_gaze} with gaze, {with_vitals} with vitals")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Moment-level cross-modal context extraction")
    parser.add_argument("--session-id", default=None, help="Session ID (omit for legacy paths)")
    args = parser.parse_args()
    main(session_id=args.session_id)
