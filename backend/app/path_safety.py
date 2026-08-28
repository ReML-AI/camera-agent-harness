"""Pure path-validation helpers used by the local review prototype."""

from __future__ import annotations

import re
from pathlib import Path


_SESSION_ID = re.compile(r"[A-Za-z0-9_-]+")
_FILE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def validate_session_id(value: str) -> str:
    """Return a safe session identifier or raise ``ValueError``."""
    if not _SESSION_ID.fullmatch(value):
        raise ValueError("session ID may contain only letters, digits, '_' and '-'")
    return value


def validate_file_component(value: str) -> str:
    """Return one safe file-name component or raise ``ValueError``."""
    if value in {".", ".."} or not _FILE_COMPONENT.fullmatch(value):
        raise ValueError("invalid file-name component")
    return value


def path_below(base: Path, *components: str) -> Path:
    """Resolve a path and prove that it remains below ``base``."""
    resolved_base = base.resolve()
    candidate = resolved_base.joinpath(*components).resolve()
    if not candidate.is_relative_to(resolved_base):
        raise ValueError("path escapes its configured data directory")
    return candidate
