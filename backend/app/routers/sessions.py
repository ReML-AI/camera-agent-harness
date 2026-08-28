"""Session-related endpoints"""
from fastapi import APIRouter, HTTPException
import json
from pathlib import Path

from ._validation import require_session_id

router = APIRouter()

# Path to data
DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"


def _session_paths(session_id: str) -> tuple[Path, Path]:
    session_id = require_session_id(session_id)
    session_dir = DATA_DIR / "sessions" / session_id
    return (
        session_dir / "processed" / "moment_contexts.json",
        session_dir / "raw" / "diarized_transcript_full.json",
    )


def _load_json(path: Path, detail: str) -> dict:
    if not path.is_file():
        raise HTTPException(status_code=404, detail=detail)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=500, detail=f"Invalid pipeline artifact: {path.name}") from error


@router.get("/")
def list_sessions():
    """List all available sessions by scanning data/sessions/."""
    sessions_dir = DATA_DIR / "sessions"
    if not sessions_dir.exists():
        return []

    result = []
    for session_dir in sorted(sessions_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        processed = session_dir / "processed"
        ctx_path = processed / "moment_contexts.json"
        if not ctx_path.exists():
            continue
        try:
            with open(ctx_path) as f:
                ctx = json.load(f)
            ctx.get("metadata", {})
            moments = ctx.get("moments", [])
            result.append({
                "id": session_dir.name,
                "status": "ready",
                "total_moments": len(moments),
                "videos": ["cam1", "cam2", "cam3", "monitor"],
            })
        except Exception:
            continue
    return result


@router.get("/{session_id}")
def get_session(session_id: str):
    """Get session details"""
    context_path, _ = _session_paths(session_id)
    data = _load_json(context_path, "Session not found")
    moments = data.get("moments", [])
    metadata = data.get("metadata", {})

    return {
        "id": session_id,
        "date": metadata.get("date"),
        "status": "ready",
        "statistics": {"total_moments": len(moments)},
        "videos": ["cam1", "cam2", "cam3", "monitor"]
    }


@router.get("/{session_id}/moments")
def get_moments(session_id: str):
    """Get all critical moments for a session"""
    context_path, _ = _session_paths(session_id)
    data = _load_json(context_path, "Session not found")
    moments = data.get("moments", [])

    return {
        "session_id": session_id,
        "moments": moments,
        "statistics": {"total_moments": len(moments)},
    }


@router.get("/{session_id}/transcript")
def get_transcript(session_id: str):
    """Get transcript for a session"""
    _, transcript_path = _session_paths(session_id)
    data = _load_json(transcript_path, "Transcript not found")

    return {
        "session_id": session_id,
        "segments": data.get("segments", [])
    }
