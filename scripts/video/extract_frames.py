#!/usr/bin/env python3
"""
Extract frames or video clips from simulation recordings.

Usage:
  # Extract a single frame at 1:30
  python extract_frames.py --video data/videos/cam1.mp4 --time 1:30 --output frame.png

  # Extract a video clip from 1:30 to 2:00
  python extract_frames.py --video data/videos/cam1.mp4 --start 1:30 --end 2:00 --output clip.mp4

  # Extract frame at a specific frame number (25fps)
  python extract_frames.py --video data/videos/cam1.mp4 --frame 2820 --output frame.png

  # Extract and crop to a bounding box (normalized 0-1)
  python extract_frames.py --video data/videos/cam1.mp4 --time 1:30 --crop 0.48,0.11,0.57,0.52 --output cropped.png
"""
import argparse
import subprocess
import sys
from pathlib import Path


def parse_time(t: str) -> float:
    """Parse MM:SS or SS or MM:SS.ms to seconds."""
    parts = t.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return float(parts[0])


def frame_to_time(frame: int, fps: float = 25.0) -> float:
    return frame / fps


def extract_frame(video: str, timestamp: float, output: str, crop: str | None = None):
    """Extract a single frame at the given timestamp."""
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(timestamp),
        "-i", video,
        "-frames:v", "1",
        "-q:v", "2",
    ]
    if crop:
        # crop is "x1,y1,x2,y2" normalized 0-1, convert to ffmpeg crop filter
        x1, y1, x2, y2 = [float(v) for v in crop.split(",")]
        # We need video dimensions first — use a probe
        w, h = _get_video_dimensions(video)
        px1, py1 = int(x1 * w), int(y1 * h)
        pw, ph = int((x2 - x1) * w), int((y2 - y1) * h)
        cmd += ["-vf", f"crop={pw}:{ph}:{px1}:{py1}"]
    cmd.append(output)
    _run(cmd)
    print(f"Extracted frame at {timestamp:.2f}s -> {output}")


def extract_clip(video: str, start: float, end: float, output: str):
    """Extract a video clip from start to end."""
    duration = end - start
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", video,
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-an",  # no audio for annotated clips
        output,
    ]
    _run(cmd)
    print(f"Extracted clip {start:.2f}s-{end:.2f}s -> {output}")


def _get_video_dimensions(video: str) -> tuple[int, int]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", video],
        capture_output=True, text=True, check=True,
    )
    w, h = result.stdout.strip().split(",")
    return int(w), int(h)


def _run(cmd: list[str]):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Extract frames or clips from video")
    parser.add_argument("--video", required=True, help="Path to video file")
    parser.add_argument("--time", help="Timestamp for single frame (MM:SS or seconds)")
    parser.add_argument("--frame", type=int, help="Frame number (at 25fps)")
    parser.add_argument("--start", help="Clip start time (MM:SS)")
    parser.add_argument("--end", help="Clip end time (MM:SS)")
    parser.add_argument("--fps", type=float, default=25.0, help="Video FPS (default: 25)")
    parser.add_argument("--crop", help="Crop region as x1,y1,x2,y2 (normalized 0-1)")
    parser.add_argument("--output", required=True, help="Output file path")
    args = parser.parse_args()

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    if args.frame is not None:
        ts = frame_to_time(args.frame, args.fps)
        extract_frame(args.video, ts, args.output, args.crop)
    elif args.time:
        ts = parse_time(args.time)
        extract_frame(args.video, ts, args.output, args.crop)
    elif args.start and args.end:
        extract_clip(args.video, parse_time(args.start), parse_time(args.end), args.output)
    else:
        parser.error("Provide --time/--frame for a frame, or --start + --end for a clip")


if __name__ == "__main__":
    main()
