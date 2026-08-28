"""Debrief Plans endpoints — persist starred moments and facilitator notes."""
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Dict, List
import json
from pathlib import Path
from datetime import datetime, timezone

from ._validation import require_session_id

router = APIRouter()

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


class DebriefPlan(BaseModel):
    session_id: str
    starred_moment_ids: List[int] = Field(default_factory=list)
    moment_order: List[int] = Field(default_factory=list)
    notes: Dict[str, str] = Field(default_factory=dict)
    updated_at: str = ""


def _plan_path(session_id: str) -> Path:
    """Resolve the JSON file path for a debrief plan."""
    session_id = require_session_id(session_id)
    return PROJECT_ROOT / "data" / "processed" / f"debrief_plan_{session_id}.json"


def _default_plan(session_id: str) -> dict:
    """Return a default empty plan for a session."""
    return {
        "session_id": session_id,
        "starred_moment_ids": [],
        "moment_order": [],
        "notes": {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/{session_id}")
def get_debrief_plan(session_id: str):
    """Load a saved debrief plan. Returns a default empty plan if none exists."""
    path = _plan_path(session_id)
    if not path.exists():
        return _default_plan(session_id)
    with open(path) as f:
        return json.load(f)


@router.put("/{session_id}")
def save_debrief_plan(session_id: str, plan: DebriefPlan):
    """Save a debrief plan to disk."""
    path = _plan_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = plan.model_dump()
    data["session_id"] = session_id
    if not data["updated_at"]:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return data
