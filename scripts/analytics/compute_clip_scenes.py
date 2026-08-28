#!/usr/bin/env python3
"""Stage 5: CLIP zero-shot scene descriptions per time window.

Samples frames from each camera, runs CLIP zero-shot classification
against clinical scene categories, picks best description per window.

Usage (GPU required):
    srun --gres=gpu:1 python3 scripts/analytics/compute_clip_scenes.py --session-id session_001
"""
import json
import argparse
from pathlib import Path

try:
    from scripts.utils.session_paths import raw_dir, videos_dir
except ImportError:
    from pathlib import Path as _P
    _ROOT = _P(__file__).resolve().parent.parent.parent
    def raw_dir(sid): return _ROOT / "data" / "sessions" / sid / "raw"
    def videos_dir(sid): return _ROOT / "data" / "sessions" / sid / "videos"

CLINICAL_SCENES = [
    "Team performing chest compressions on patient",
    "Team checking vital signs on monitor",
    "Team administering medication",
    "Team assessing patient airway",
    "Team discussing patient status",
    "Single person operating medical equipment",
    "Team gathered around patient bed",
    "Team member moving rapidly across room",
    "Calm observation or waiting period",
    "Team performing defibrillation",
    "Healthcare worker documenting or taking notes",
    "Team performing patient assessment",
    "Team in briefing or handover discussion",
    "Team responding to alarm or monitor change",
    "Patient being repositioned by team",
]

CAMERAS = ["cam1", "cam2", "cam3"]


def load_clip_model(model_path, device="cuda"):
    from transformers import CLIPModel, CLIPProcessor
    model_path = Path(model_path)
    if not model_path.is_dir():
        raise FileNotFoundError(f"Local CLIP model directory is required: {model_path}")
    model = CLIPModel.from_pretrained(
        str(model_path), use_safetensors=True, local_files_only=True
    ).to(device)
    processor = CLIPProcessor.from_pretrained(str(model_path), local_files_only=True)
    return model, processor


def sample_frames(video_path, window_start, window_end, n_frames=3):
    """Sample n_frames evenly from a video window."""
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = []
    timestamps = np.linspace(window_start, window_end, n_frames + 2)[1:-1]
    for t in timestamps:
        frame_num = int(t * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        if ret:
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    cap.release()
    return frames


def classify_frames(frames, model, processor, device="cuda"):
    """Run CLIP zero-shot on frames, return best scene + confidence."""
    import torch
    import numpy as np
    if not frames:
        return None, 0.0
    inputs = processor(text=CLINICAL_SCENES, images=frames,
                       return_tensors="pt", padding=True).to(device)
    with torch.no_grad():
        outputs = model(**inputs)
    logits = outputs.logits_per_image.cpu().numpy()
    avg_logits = logits.mean(axis=0)
    probs = np.exp(avg_logits) / np.exp(avg_logits).sum()
    best_idx = int(np.argmax(probs))
    return CLINICAL_SCENES[best_idx], float(probs[best_idx])


def compute_scenes(session_id, model_path, window_sec=10, device="cuda"):
    """Compute CLIP scene descriptions for all windows across all cameras."""
    import cv2
    model, processor = load_clip_model(model_path, device)
    vid_dir = videos_dir(session_id)

    cap = cv2.VideoCapture(str(vid_dir / "cam1.mp4"))
    duration = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) / cap.get(cv2.CAP_PROP_FPS)
    cap.release()

    scenes = []
    win_start = 0.0
    while win_start < duration:
        win_end = min(win_start + window_sec, duration)
        per_camera = {}
        best_desc, best_conf, best_cam = None, 0.0, None

        for cam in CAMERAS:
            vid_path = vid_dir / f"{cam}.mp4"
            if not vid_path.exists():
                continue
            frames = sample_frames(vid_path, win_start, win_end, n_frames=3)
            desc, conf = classify_frames(frames, model, processor, device)
            if desc:
                per_camera[cam] = {"description": desc, "confidence": round(conf, 3)}
                if conf > best_conf:
                    best_desc, best_conf, best_cam = desc, conf, cam

        scenes.append({
            "start": round(win_start, 1), "end": round(win_end, 1),
            "description": best_desc or "Unknown scene",
            "confidence": round(best_conf, 3), "best_camera": best_cam,
            "per_camera": per_camera,
        })
        win_start += window_sec

    return {"window_duration_sec": window_sec, "scenes": scenes}


def main():
    parser = argparse.ArgumentParser(description="CLIP scene descriptions")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--window-sec", type=int, default=10)
    parser.add_argument("--model-path", required=True,
                        help="Existing local pinned CLIP model directory")
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    result = compute_scenes(args.session_id, args.model_path, args.window_sec, args.device)
    out_path = raw_dir(args.session_id) / "clip_scene_descriptions.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Wrote {len(result['scenes'])} scenes -> {out_path}")


if __name__ == "__main__":
    main()
