#!/usr/bin/env python3
"""
Generate all visual assets needed for the debrief report.

Outputs: data/processed/report_assets/{session_id}/
  speakers/SPEAKER_00.jpg    — spotlight portrait: full frame, person circled
  speakers/SPEAKER_00_crop.jpg — cropped body portrait
  moments/moment_000.png      — annotated frame: boxes, gaze, speech, gaze bar
  manifest.json

Usage:
  python generate_report_assets.py --session session_001
  python generate_report_assets.py --session session_001 --speakers-only
  python generate_report_assets.py --session session_001 --moments-only
"""
import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import cv2

from scripts.video.annotate_frames import (
    draw_boxes, draw_gaze, draw_speaker, draw_critical_border,
    draw_speech, draw_spotlight, draw_team_gaze_bar, find_keyframe,
)


# ── Path helpers ───────────────────────────────────────────────────────────────

def processed_dir() -> Path:
    return PROJECT_ROOT / "data" / "processed"


def out_dir(session_id: str) -> Path:
    return processed_dir() / "report_assets" / session_id


def load_data(session_id: str):
    d = processed_dir()
    overlay  = json.loads((d / "video_overlay_data.json").read_text())
    contexts = json.loads((d / "moment_contexts.json").read_text())
    analytics= json.loads((d / "interaction_analytics.json").read_text())
    return overlay, contexts, analytics


def _find_person_keyframe(overlay: dict, person_id: str,
                           prefer_speaking: bool = True) -> dict | None:
    """Find a keyframe where person is visible (optionally speaking)."""
    best_speaking, best_any = None, None
    for kf in overlay["keyframes"]:
        for p in kf["persons"]:
            if p["personId"] != person_id:
                continue
            b = p["bbox"]
            bw, bh = b["x2"] - b["x1"], b["y2"] - b["y1"]
            if bw < 0.03 or bh < 0.05:
                continue
            if best_any is None:
                best_any = kf
            if p.get("isSpeaking") and best_speaking is None:
                best_speaking = kf
    return (best_speaking or best_any) if prefer_speaking else best_any


# ── Speaker Portraits ──────────────────────────────────────────────────────────

def generate_speaker_portraits(session_id: str, overlay: dict, analytics: dict) -> dict:
    """
    For each speaker:
    1. spotlight image — full 960×540 frame with dark background, colored
       circle around the person, gaze arrow, speaker label
    2. crop image     — tight body crop (200×260) for small cards
    """
    speakers_out = out_dir(session_id) / "speakers"
    speakers_out.mkdir(parents=True, exist_ok=True)

    video_path = PROJECT_ROOT / "data" / "videos" / f"{overlay['videoId']}.mp4"
    persons_meta = overlay["persons"]
    manifest: dict = {}

    if not video_path.exists():
        print(f"  WARNING: {video_path} not found — skipping portraits")
        return manifest

    cap = cv2.VideoCapture(str(video_path))
    vid_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    vid_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    for speaker_id, sinfo in analytics["speakers"].items():
        role = sinfo.get("label", speaker_id)

        # speaker_id may exist directly as personId in keyframes
        search_ids = [speaker_id]
        for pid, pmeta in persons_meta.items():
            if pmeta["role"] == role and pid != speaker_id:
                search_ids.append(pid)

        kf, matched_pid = None, None
        for pid in search_ids:
            kf = _find_person_keyframe(overlay, pid, prefer_speaking=True)
            if kf:
                matched_pid = pid
                break

        if not kf or not matched_pid:
            print(f"  {speaker_id}: no keyframe found")
            continue

        cap.set(cv2.CAP_PROP_POS_FRAMES, kf["frame"])
        ret, frame = cap.read()
        if not ret:
            print(f"  {speaker_id}: cannot read frame {kf['frame']}")
            continue

        person_data = next((p for p in kf["persons"] if p["personId"] == matched_pid), None)
        if not person_data:
            continue

        # ── 1. Spotlight portrait (full frame, annotated) ──
        spotlight = frame.copy()
        spotlight = draw_spotlight(spotlight, kf, matched_pid, persons_meta)
        # Downscale to 960×540
        spotlight = cv2.resize(spotlight, (960, 540), interpolation=cv2.INTER_AREA)
        spotlight_path = speakers_out / f"{speaker_id}.jpg"
        cv2.imwrite(str(spotlight_path), spotlight, [cv2.IMWRITE_JPEG_QUALITY, 92])

        # ── 2. Crop portrait (tight body crop) ──
        b = person_data["bbox"]
        px1, py1 = int(b["x1"] * vid_w), int(b["y1"] * vid_h)
        px2, py2 = int(b["x2"] * vid_w), int(b["y2"] * vid_h)
        pad_x = int((px2 - px1) * 0.20)
        pad_y = int((py2 - py1) * 0.12)
        cx1 = max(0, px1 - pad_x)
        cy1 = max(0, py1 - pad_y)
        cx2 = min(vid_w, px2 + pad_x)
        cy2 = min(vid_h, py2 + pad_y)
        crop = frame[cy1:cy2, cx1:cx2]
        if crop.size > 0:
            crop = cv2.resize(crop, (200, 260), interpolation=cv2.INTER_AREA)
            crop_path = speakers_out / f"{speaker_id}_crop.jpg"
            cv2.imwrite(str(crop_path), crop, [cv2.IMWRITE_JPEG_QUALITY, 90])

        manifest[speaker_id] = {
            "file": f"speakers/{speaker_id}.jpg",
            "crop_file": f"speakers/{speaker_id}_crop.jpg",
            "person_id": matched_pid,
            "frame": kf["frame"],
            "label": sinfo["label"],
            "role": role,
            "color": sinfo["color"],
        }
        print(f"  {speaker_id} ({sinfo['label']}): frame {kf['frame']} → spotlight + crop saved")

    cap.release()
    return manifest


# ── Annotated Moment Frames ────────────────────────────────────────────────────

def generate_moment_frames(session_id: str, overlay: dict, contexts: dict) -> dict:
    """
    For each moment generate a richly annotated 960×540 frame:
    boxes + gaze arrows + speaker dashed borders + critical border
    + speech caption + team gaze bar at top
    """
    moments_out = out_dir(session_id) / "moments"
    moments_out.mkdir(parents=True, exist_ok=True)

    video_path = PROJECT_ROOT / "data" / "videos" / f"{overlay['videoId']}.mp4"
    if not video_path.exists():
        print(f"  WARNING: {video_path} not found — skipping moment frames")
        return {}

    cap = cv2.VideoCapture(str(video_path))
    persons_meta = overlay["persons"]
    overlay_moments = {m["moment_id"]: m for m in overlay["moments"]}
    speaker_roles = contexts.get("speaker_roles", {})

    manifest: dict = {}

    for moment in contexts["moments"]:
        mid = moment["moment_id"]
        om = overlay_moments.get(mid)
        if not om:
            continue

        mid_frame = (om["start_frame"] + om["end_frame"]) // 2
        kf = find_keyframe(overlay, mid_frame)
        if not kf:
            continue

        cap.set(cv2.CAP_PROP_POS_FRAMES, mid_frame)
        ret, frame = cap.read()
        if not ret:
            continue

        # Draw all overlay layers
        frame = draw_boxes(frame, kf, persons_meta)
        frame = draw_gaze(frame, kf, persons_meta)
        frame = draw_speaker(frame, kf, persons_meta)

        if moment.get("importance") == "critical":
            frame = draw_critical_border(frame)

        # Team gaze bar (proves attention claim visually)
        tg = moment.get("gaze", {}).get("team_gaze")
        if tg and sum(tg.values()) > 0:
            frame = draw_team_gaze_bar(frame, tg)

        # Speech caption (most substantive quote)
        utts = moment.get("speech", {}).get("chronological_utterances", [])
        if utts:
            best_utt = max(utts, key=lambda u: len(u.get("text", "")))
            spk = best_utt.get("speaker", "")
            spk_label = speaker_roles.get(spk, {}).get("label", spk)
            text = best_utt.get("text", "")
            if len(text) > 120:
                text = text[:117] + "..."
            frame = draw_speech(frame, f"{spk_label}: {text}")

        # Resize to 960×540
        frame = cv2.resize(frame, (960, 540), interpolation=cv2.INTER_AREA)

        out_path = moments_out / f"moment_{mid:03d}.png"
        cv2.imwrite(str(out_path), frame)

        manifest[str(mid)] = {
            "file": f"moments/moment_{mid:03d}.png",
            "moment_id": mid,
            "frame": mid_frame,
            "timestamp": moment["timestamp"],
            "category": moment["category"],
            "importance": moment["importance"],
        }
        print(f"  Moment {mid:>2} ({moment['importance']:8}) {moment['category'][:30]}: "
              f"frame {mid_frame} → {out_path.name}")

    cap.release()
    return manifest


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate report visual assets")
    parser.add_argument("--session", default="session_001")
    parser.add_argument("--speakers-only", action="store_true")
    parser.add_argument("--moments-only", action="store_true")
    args = parser.parse_args()

    print(f"Generating report assets for {args.session}…")
    overlay, contexts, analytics = load_data(args.session)
    full_manifest = {"session_id": args.session, "speakers": {}, "moments": {}}

    if not args.moments_only:
        print("\n── Speaker Portraits ──")
        full_manifest["speakers"] = generate_speaker_portraits(args.session, overlay, analytics)

    if not args.speakers_only:
        print("\n── Moment Frames ──")
        full_manifest["moments"] = generate_moment_frames(args.session, overlay, contexts)

    manifest_path = out_dir(args.session) / "manifest.json"
    manifest_path.write_text(json.dumps(full_manifest, indent=2))
    print(f"\nManifest → {manifest_path}")
    print(f"Done: {len(full_manifest['speakers'])} speakers, "
          f"{len(full_manifest['moments'])} moments")


if __name__ == "__main__":
    main()
