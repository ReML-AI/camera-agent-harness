"""Serve pre-rendered supervision review clips and their index."""
from __future__ import annotations
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from .videos import range_requests_response


router = APIRouter()

SESSIONS_DIR = Path(__file__).parent.parent.parent.parent / "data" / "sessions"

ALLOWED_CAMS = {"cam1", "cam2", "cam3"}
ALLOWED_PRESETS = {"source", "tracking", "attention", "comms", "yolo"}


def _safe_segment(s: str) -> str:
    if not s or "/" in s or ".." in s or "\\" in s:
        raise HTTPException(status_code=400, detail="Invalid path segment")
    return s


@router.get("/{session_id}")
def get_index(session_id: str):
    session_id = _safe_segment(session_id)
    index_path = SESSIONS_DIR / session_id / "review_clips" / "index.json"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="No review clips rendered")
    return json.loads(index_path.read_text())


@router.get("/{session_id}/{clip_id}/{cam}/{preset}")
def get_clip_video(session_id: str, clip_id: str, cam: str, preset: str,
                   request: Request):
    session_id = _safe_segment(session_id)
    clip_id = _safe_segment(clip_id)
    if cam not in ALLOWED_CAMS:
        raise HTTPException(status_code=400, detail="Invalid cam")
    if preset not in ALLOWED_PRESETS:
        raise HTTPException(status_code=400, detail="Invalid preset")
    video_path = (SESSIONS_DIR / session_id / "review_clips" / clip_id
                  / f"{cam}_{preset}.mp4")
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Clip video not found")
    return range_requests_response(request, video_path)
