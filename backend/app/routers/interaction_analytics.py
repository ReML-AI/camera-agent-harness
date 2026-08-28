"""Interaction Analytics endpoints — serves precomputed diarization + gaze analytics."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import json
from pathlib import Path

from ._validation import require_session_id

router = APIRouter()

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


def _data_dir(session_id: str) -> Path:
    """Resolve data directory for a session. Falls back to flat layout for backward compat."""
    session_id = require_session_id(session_id)
    new_session_dir = PROJECT_ROOT / "data" / "sessions" / session_id / "processed"
    if new_session_dir.is_dir():
        return new_session_dir
    legacy_session_dir = PROJECT_ROOT / "data" / "processed" / session_id
    if legacy_session_dir.is_dir():
        return legacy_session_dir
    return PROJECT_ROOT / "data" / "processed"


class RegenerateRequest(BaseModel):
    moment_id: int


@router.get("/{session_id}/analytics")
def get_interaction_analytics(session_id: str):
    """Return precomputed interaction analytics (speakers, timeline, turn-taking, attention, insights)."""
    path = _data_dir(session_id) / "interaction_analytics.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Interaction analytics not found. Run compute_interaction_analytics.py first.")
    with open(path) as f:
        return json.load(f)


@router.get("/{session_id}/diarized-transcript")
def get_diarized_transcript(session_id: str):
    """Return the full diarized transcript segments."""
    path = _data_dir(session_id) / "diarized_transcript_full.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Diarized transcript not found.")
    with open(path) as f:
        data = json.load(f)
    return {"segments": data.get("segments", [])}


@router.get("/{session_id}/gaze-tracks")
def get_gaze_tracks(session_id: str):
    """Return precomputed gaze target classification per track."""
    path = _data_dir(session_id) / "gaze_tracks.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Gaze tracks not found. Run scripts/gaze/classify_gaze_targets.py first."
        )
    with open(path) as f:
        return json.load(f)


@router.get("/{session_id}/moment-contexts")
def get_moment_contexts(session_id: str):
    """Return moment contexts merged with narratives."""
    data_dir = _data_dir(session_id)
    ctx_path = data_dir / "moment_contexts.json"
    nar_path = data_dir / "moment_narratives.json"

    if not ctx_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Moment contexts not found. Run scripts/analytics/compute_moment_context.py first."
        )

    with open(ctx_path) as f:
        contexts = json.load(f)

    # Merge with narratives if available
    narratives = {}
    if nar_path.exists():
        with open(nar_path) as f:
            nar_data = json.load(f)
        narratives = nar_data.get("narratives", {})

    # Merge narrative into each moment
    for moment in contexts["moments"]:
        mid = str(moment["moment_id"])
        nar = narratives.get(mid, {})
        moment["narrative"] = nar.get("narrative")
        moment["tags"] = nar.get("tags", [])
        moment["discussion_prompt"] = nar.get("discussion_prompt")

    return contexts


@router.get("/{session_id}/video-overlay")
def get_video_overlay(session_id: str):
    """Return precomputed video overlay keyframe data for canvas rendering."""
    path = _data_dir(session_id) / "video_overlay_data.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Video overlay data not found. Run scripts/analytics/compute_video_overlay.py first."
        )
    with open(path) as f:
        return json.load(f)


@router.post("/{session_id}/regenerate-narrative")
async def regenerate_narrative(session_id: str, body: RegenerateRequest):
    """Regenerate LLM narrative for a specific moment."""
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))

    data_dir = _data_dir(session_id)
    ctx_path = data_dir / "moment_contexts.json"
    nar_path = data_dir / "moment_narratives.json"

    if not ctx_path.exists():
        raise HTTPException(status_code=404, detail="Moment contexts not found.")

    with open(ctx_path) as f:
        contexts = json.load(f)

    # Find the moment
    moment = None
    for m in contexts["moments"]:
        if m["moment_id"] == body.moment_id:
            moment = m
            break

    if moment is None:
        raise HTTPException(status_code=404, detail=f"Moment {body.moment_id} not found")

    try:
        from scripts.analytics.generate_moment_narratives import generate_narrative

        result = generate_narrative(None, moment)
        result["generated_at"] = __import__("datetime").datetime.now().isoformat()

        # Update narratives file
        if nar_path.exists():
            with open(nar_path) as f:
                nar_data = json.load(f)
        else:
            nar_data = {"metadata": {}, "narratives": {}}

        nar_data["narratives"][str(body.moment_id)] = result
        with open(nar_path, "w") as f:
            json.dump(nar_data, f, indent=2)

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Narrative generation failed: {str(e)}")
