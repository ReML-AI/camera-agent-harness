"""Shared path helpers for session-based pipeline.

All scripts resolve paths through these functions so session directory
structure is defined in one place.
"""
from pathlib import Path

from scripts.core.records import require_id

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

SESSIONS_ROOT = PROJECT_ROOT / "data" / "sessions"


def session_dir(session_id: str) -> Path:
    return SESSIONS_ROOT / require_id(session_id, "session_id")

def raw_dir(session_id: str) -> Path:
    return session_dir(session_id) / "raw"

def processed_dir(session_id: str) -> Path:
    return session_dir(session_id) / "processed"

def metrics_dir(session_id: str) -> Path:
    return session_dir(session_id) / "metrics"

def videos_dir(session_id: str) -> Path:
    return session_dir(session_id) / "videos"

def prerequisites_dir(session_id: str) -> Path:
    return session_dir(session_id) / "prerequisites"

def artifacts_dir(session_id: str) -> Path:
    return session_dir(session_id) / "artifacts"

def provenance_dir(session_id: str) -> Path:
    return session_dir(session_id) / "provenance"

def configuration_dir(session_id: str) -> Path:
    return session_dir(session_id) / "configuration"
