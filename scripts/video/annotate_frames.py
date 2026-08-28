#!/usr/bin/env python3
"""
Draw annotations on video frames: bounding boxes, gaze arrows, speaker
indicators, speech bubbles, highlight rectangles, spotlight circles.

Usage:
  # All annotations on a frame
  python annotate_frames.py --input frame.png --overlay data.json --frame 2820 \\
      --boxes --gaze --speaker --speech "Quote text" --output annotated.png

  # Spotlight a specific person (darken background, circle around them)
  python annotate_frames.py --input frame.png --overlay data.json --frame 7280 \\
      --spotlight SPEAKER_03 --output spotlight.png

  # Highlight circle around a region
  python annotate_frames.py --input frame.png --circle 0.48,0.11,0.57,0.52 \\
      --circle-color blue --output circled.png

  # Highlight box around a region
  python annotate_frames.py --input frame.png --highlight 0.48,0.11,0.57,0.52 \\
      --highlight-color red --output highlighted.png

  # Annotate a video clip
  python annotate_frames.py --input clip.mp4 --overlay data.json --start-frame 2770 \\
      --boxes --gaze --speaker --output annotated_clip.mp4
"""
import argparse
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


# ── Color helpers ──────────────────────────────────────────────────────────────

def hex_to_bgr(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b, g, r)


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


NAMED_COLORS: dict[str, str] = {
    "red": "#EF4444", "green": "#22C55E", "blue": "#3B82F6",
    "amber": "#F59E0B", "purple": "#A855F7", "orange": "#F97316",
    "gray": "#6B7280", "white": "#FFFFFF", "cyan": "#06B6D4",
    "pink": "#EC4899", "emerald": "#10B981", "indigo": "#6366F1",
}


def resolve_color(c: str) -> str:
    return NAMED_COLORS.get(c.lower(), c)


# ── Overlay data loading ───────────────────────────────────────────────────────

def load_overlay(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def find_keyframe(overlay: dict, frame_num: int) -> dict | None:
    """Find the nearest keyframe with person data."""
    best, best_dist = None, float("inf")
    for kf in overlay["keyframes"]:
        dist = abs(kf["frame"] - frame_num)
        if dist < best_dist and kf["persons"]:
            best_dist = dist
            best = kf
        if kf["frame"] > frame_num + 150 and best:
            break
    return best


def get_person_data(keyframe: dict, person_id: str) -> dict | None:
    """Get a specific person's data from a keyframe."""
    return next((p for p in keyframe["persons"] if p["personId"] == person_id), None)


# ── Core drawing functions ─────────────────────────────────────────────────────

def draw_boxes(img: np.ndarray, keyframe: dict, persons_meta: dict,
               exclude_ids: set[str] | None = None) -> np.ndarray:
    """Draw bounding boxes with role labels."""
    h, w = img.shape[:2]
    for p in keyframe["persons"]:
        if exclude_ids and p["personId"] in exclude_ids:
            continue
        meta = persons_meta.get(p["personId"], {})
        color = hex_to_bgr(meta.get("color", "#94A3B8"))
        bbox = p["bbox"]
        x1, y1 = int(bbox["x1"] * w), int(bbox["y1"] * h)
        x2, y2 = int(bbox["x2"] * w), int(bbox["y2"] * h)

        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

        label = meta.get("role", p["personId"])
        if len(label) > 22:
            label = label[:19] + "..."
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(img, (x1, max(0, y1 - th - 8)), (x1 + tw + 8, y1), color, -1)
        cv2.putText(img, label, (x1 + 4, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX,
                    0.45, (255, 255, 255), 1, cv2.LINE_AA)
    return img


def draw_gaze(img: np.ndarray, keyframe: dict, persons_meta: dict) -> np.ndarray:
    """Draw gaze direction arrows from head pose yaw."""
    h, w = img.shape[:2]
    arrow_color = hex_to_bgr("#F97316")
    for p in keyframe["persons"]:
        if not p.get("headPose"):
            continue
        bbox = p["bbox"]
        x1, y1 = int(bbox["x1"] * w), int(bbox["y1"] * h)
        x2, y2 = int(bbox["x2"] * w), int(bbox["y2"] * h)
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        bw, bh = x2 - x1, y2 - y1

        yaw = p["headPose"]["yaw"]
        arrow_len = max(bw, bh) * 1.3
        rad = math.radians(yaw)
        ex = int(cx + math.sin(rad) * arrow_len)
        ey = cy

        cv2.arrowedLine(img, (cx, cy), (ex, ey), arrow_color, 2, tipLength=0.2)
    return img


def draw_speaker(img: np.ndarray, keyframe: dict, persons_meta: dict) -> np.ndarray:
    """Draw speaker indicator: dashed border + red dot."""
    h, w = img.shape[:2]
    red = hex_to_bgr("#EF4444")
    for p in keyframe["persons"]:
        if not p.get("isSpeaking"):
            continue
        bbox = p["bbox"]
        x1, y1 = int(bbox["x1"] * w), int(bbox["y1"] * h)
        x2, y2 = int(bbox["x2"] * w), int(bbox["y2"] * h)

        pad = 5
        for i in range(x1 - pad, x2 + pad, 10):
            cv2.line(img, (i, y1 - pad), (min(i + 6, x2 + pad), y1 - pad), red, 2)
            cv2.line(img, (i, y2 + pad), (min(i + 6, x2 + pad), y2 + pad), red, 2)
        for j in range(y1 - pad, y2 + pad, 10):
            cv2.line(img, (x1 - pad, j), (x1 - pad, min(j + 6, y2 + pad)), red, 2)
            cv2.line(img, (x2 + pad, j), (x2 + pad, min(j + 6, y2 + pad)), red, 2)

        cv2.circle(img, (x2 + 8, y1 - 6), 6, red, -1)
        cv2.putText(img, "SPEAKING", (x1, y2 + 18), cv2.FONT_HERSHEY_SIMPLEX,
                    0.35, red, 1, cv2.LINE_AA)
    return img


def draw_highlight(img: np.ndarray, region: str, color_hex: str,
                   thickness: int = 4) -> np.ndarray:
    """Highlight a normalized region with a colored rectangle border."""
    h, w = img.shape[:2]
    x1n, y1n, x2n, y2n = [float(v) for v in region.split(",")]
    x1, y1 = int(x1n * w), int(y1n * h)
    x2, y2 = int(x2n * w), int(y2n * h)
    cv2.rectangle(img, (x1, y1), (x2, y2), hex_to_bgr(color_hex), thickness)
    return img


def draw_circle_highlight(img: np.ndarray, region: str, color_hex: str,
                           thickness: int = 4) -> np.ndarray:
    """Draw an ellipse/circle around a normalized bbox region."""
    h, w = img.shape[:2]
    x1n, y1n, x2n, y2n = [float(v) for v in region.split(",")]
    x1, y1 = int(x1n * w), int(y1n * h)
    x2, y2 = int(x2n * w), int(y2n * h)
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    rx = (x2 - x1) // 2 + 12
    ry = (y2 - y1) // 2 + 12
    cv2.ellipse(img, (cx, cy), (rx, ry), 0, 0, 360, hex_to_bgr(color_hex), thickness)
    return img


def draw_spotlight(img: np.ndarray, keyframe: dict, person_id: str,
                   persons_meta: dict) -> np.ndarray:
    """
    Spotlight effect: darken everything except the target person.
    Draws a softened dark overlay, then draws the person's bbox clearly
    with a colored circle border and name label.
    """
    h, w = img.shape[:2]

    person_data = get_person_data(keyframe, person_id)
    if not person_data:
        return img

    meta = persons_meta.get(person_id, {})
    color_hex = meta.get("color", "#3B82F6")
    color_bgr = hex_to_bgr(color_hex)
    role = meta.get("role", person_id)

    bbox = person_data["bbox"]
    x1, y1 = int(bbox["x1"] * w), int(bbox["y1"] * h)
    x2, y2 = int(bbox["x2"] * w), int(bbox["y2"] * h)

    # Pad the spotlight area
    pad_x = int((x2 - x1) * 0.25)
    pad_y = int((y2 - y1) * 0.15)
    sx1 = max(0, x1 - pad_x)
    sy1 = max(0, y1 - pad_y)
    sx2 = min(w, x2 + pad_x)
    sy2 = min(h, y2 + pad_y)

    # Dark overlay on the whole image
    dark = img.copy()
    cv2.rectangle(dark, (0, 0), (w, h), (0, 0, 0), -1)
    img = cv2.addWeighted(img, 0.35, dark, 0.65, 0)

    # Also draw all other persons with thin dim boxes
    for p in keyframe["persons"]:
        if p["personId"] == person_id:
            continue
        b = p["bbox"]
        px1, py1 = int(b["x1"] * w), int(b["y1"] * h)
        px2, py2 = int(b["x2"] * w), int(b["y2"] * h)
        cv2.rectangle(img, (px1, py1), (px2, py2), (100, 100, 100), 1)

    # Draw gaze arrows for other persons (dim orange)
    for p in keyframe["persons"]:
        if p["personId"] == person_id or not p.get("headPose"):
            continue
        b = p["bbox"]
        cx = int((b["x1"] + b["x2"]) / 2 * w)
        cy = int((b["y1"] + b["y2"]) / 2 * h)
        bw = int((b["x2"] - b["x1"]) * w)
        bh = int((b["y2"] - b["y1"]) * h)
        yaw = p["headPose"]["yaw"]
        arrow_len = max(bw, bh) * 1.2
        ex = int(cx + math.sin(math.radians(yaw)) * arrow_len)
        cv2.arrowedLine(img, (cx, cy), (ex, cy), (60, 80, 120), 1, tipLength=0.2)

    # Large colored ellipse around the target person
    cx, cy = (sx1 + sx2) // 2, (sy1 + sy2) // 2
    rx, ry = (sx2 - sx1) // 2 + 8, (sy2 - sy1) // 2 + 8
    cv2.ellipse(img, (cx, cy), (rx, ry), 0, 0, 360, color_bgr, 4)
    # Inner highlight ellipse (slightly smaller, translucent)
    overlay2 = img.copy()
    cv2.ellipse(overlay2, (cx, cy), (rx - 4, ry - 4), 0, 0, 360, color_bgr, 2)
    img = cv2.addWeighted(img, 0.7, overlay2, 0.3, 0)

    # Bright gaze arrow for the target person
    if person_data.get("headPose"):
        yaw = person_data["headPose"]["yaw"]
        bw = x2 - x1
        bh = y2 - y1
        arrow_len = max(bw, bh) * 1.5
        ex = int(cx + math.sin(math.radians(yaw)) * arrow_len)
        cv2.arrowedLine(img, (cx, cy), (ex, cy), hex_to_bgr("#F97316"), 3, tipLength=0.15)

    # Name label banner at bottom of spotlight
    label_y = min(sy2 + 45, h - 5)
    (tw, th), _ = cv2.getTextSize(role, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
    lx1 = max(0, cx - tw // 2 - 12)
    lx2 = min(w, cx + tw // 2 + 12)
    cv2.rectangle(img, (lx1, label_y - th - 10), (lx2, label_y + 4), color_bgr, -1)
    cv2.putText(img, role, (lx1 + 10, label_y - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)

    return img


def draw_speech(img: np.ndarray, text: str, position: str = "bottom",
                font_size: int = 20) -> np.ndarray:
    """Add a speech caption bar at top or bottom."""
    h, w = img.shape[:2]
    pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
        ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()

    # Word-wrap
    max_chars = w // (font_size // 2)
    lines, current = [], ""
    for word in text.split():
        if len(current) + len(word) + 1 <= max_chars:
            current = f"{current} {word}".strip()
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    line_h = font_size + 8
    bar_h = len(lines) * line_h + 20
    bar_y = h - bar_h if position == "bottom" else 0

    # Draw semi-transparent background
    draw = ImageDraw.Draw(pil_img, "RGBA")
    draw.rectangle([(0, bar_y), (w, bar_y + bar_h)], fill=(0, 0, 0, 190))

    # Quote marks
    draw = ImageDraw.Draw(pil_img)
    for i, line in enumerate(lines):
        y = bar_y + 10 + i * line_h
        # First line gets quote-mark prefix
        prefix = '" ' if i == 0 else "  "
        draw.text((16, y), prefix + line, fill=(255, 255, 255), font=font)

    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def draw_critical_border(img: np.ndarray) -> np.ndarray:
    """Draw a red critical-moment border + badge."""
    h, w = img.shape[:2]
    red = hex_to_bgr("#EF4444")
    cv2.rectangle(img, (2, 2), (w - 3, h - 3), red, 3)
    badge = "CRITICAL MOMENT"
    (tw, th), _ = cv2.getTextSize(badge, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
    bx = w - tw - 20
    cv2.rectangle(img, (bx - 6, 4), (w - 4, th + 16), (0, 0, 180), -1)
    cv2.putText(img, badge, (bx, th + 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
    return img


def draw_team_gaze_bar(img: np.ndarray, team_gaze: dict) -> np.ndarray:
    """Draw a compact team gaze distribution bar at the top of the image."""
    h, w = img.shape[:2]
    bar_h = 28
    total = sum(team_gaze.values()) or 1
    GAZE_COLORS = {
        "patient": hex_to_bgr("#22C55E"),
        "monitor": hex_to_bgr("#3B82F6"),
        "person": hex_to_bgr("#A855F7"),
        "other": hex_to_bgr("#94A3B8"),
    }
    sorted_gaze = sorted(team_gaze.items(), key=lambda x: -x[1])
    x = 0
    bar_strip = np.zeros((bar_h, w, 3), dtype=np.uint8)
    for key, val in sorted_gaze:
        seg_w = int((val / total) * w)
        color = GAZE_COLORS.get(key, hex_to_bgr("#94A3B8"))
        cv2.rectangle(bar_strip, (x, 0), (x + seg_w, bar_h), color, -1)
        label = f"{key} {int((val/total)*100)}%"
        cv2.putText(bar_strip, label, (x + 4, 19),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1, cv2.LINE_AA)
        x += seg_w

    # Composite at top
    result = np.vstack([bar_strip, img])
    return result


# ── Video annotation ───────────────────────────────────────────────────────────

def annotate_video(input_path: str, output_path: str, overlay: dict,
                   start_frame: int, boxes: bool, gaze: bool, speaker: bool):
    """Annotate each frame of a video clip."""
    cap = cv2.VideoCapture(input_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (frame_w, frame_h))

    persons_meta = overlay.get("persons", {})
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        kf = find_keyframe(overlay, start_frame + frame_idx)
        if kf:
            if boxes:
                frame = draw_boxes(frame, kf, persons_meta)
            if gaze:
                frame = draw_gaze(frame, kf, persons_meta)
            if speaker:
                frame = draw_speaker(frame, kf, persons_meta)
            if kf.get("isCriticalMoment"):
                frame = draw_critical_border(frame)
        out.write(frame)
        frame_idx += 1

    cap.release()
    out.release()
    print(f"Annotated {frame_idx} frames -> {output_path}")


# ── Image annotation ───────────────────────────────────────────────────────────

def annotate_image(input_path: str, output_path: str, overlay: dict | None,
                   frame_num: int | None, boxes: bool, gaze: bool, speaker: bool,
                   speech_text: str | None, highlight: str | None,
                   highlight_color: str, circle: str | None, circle_color: str,
                   spotlight_id: str | None, is_critical: bool,
                   team_gaze: dict | None = None):
    img = cv2.imread(input_path)
    if img is None:
        print(f"Error: cannot read {input_path}", file=sys.stderr)
        sys.exit(1)

    persons_meta = overlay.get("persons", {}) if overlay else {}
    kf: dict | None = None
    if overlay and frame_num is not None:
        kf = find_keyframe(overlay, frame_num)

    if spotlight_id and kf and overlay:
        img = draw_spotlight(img, kf, spotlight_id, persons_meta)
    else:
        if kf:
            if boxes:
                img = draw_boxes(img, kf, persons_meta)
            if gaze:
                img = draw_gaze(img, kf, persons_meta)
            if speaker:
                img = draw_speaker(img, kf, persons_meta)

    if is_critical:
        img = draw_critical_border(img)
    if highlight:
        img = draw_highlight(img, highlight, resolve_color(highlight_color))
    if circle:
        img = draw_circle_highlight(img, circle, resolve_color(circle_color))
    if team_gaze:
        img = draw_team_gaze_bar(img, team_gaze)
    if speech_text:
        img = draw_speech(img, speech_text)

    cv2.imwrite(output_path, img)
    print(f"Annotated -> {output_path}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Annotate video frames")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--overlay", help="video_overlay_data.json path")
    parser.add_argument("--frame", type=int)
    parser.add_argument("--start-frame", type=int)
    parser.add_argument("--boxes", action="store_true")
    parser.add_argument("--gaze", action="store_true")
    parser.add_argument("--speaker", action="store_true")
    parser.add_argument("--speech", help="Speech caption text")
    parser.add_argument("--highlight", help="Rectangle highlight x1,y1,x2,y2")
    parser.add_argument("--highlight-color", default="red")
    parser.add_argument("--circle", help="Circle highlight x1,y1,x2,y2")
    parser.add_argument("--circle-color", default="blue")
    parser.add_argument("--spotlight", help="Person ID to spotlight")
    parser.add_argument("--critical", action="store_true")
    args = parser.parse_args()

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    overlay = load_overlay(args.overlay) if args.overlay else None
    is_video = args.input.lower().endswith((".mp4", ".avi", ".mov"))

    if is_video:
        if not overlay:
            parser.error("--overlay required for video")
        annotate_video(args.input, args.output, overlay,
                       args.start_frame or 0, args.boxes, args.gaze, args.speaker)
    else:
        annotate_image(args.input, args.output, overlay, args.frame,
                       args.boxes, args.gaze, args.speaker,
                       args.speech, args.highlight, args.highlight_color,
                       args.circle, args.circle_color, args.spotlight,
                       args.critical)


if __name__ == "__main__":
    main()
