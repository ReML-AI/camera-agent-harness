"""HTTP-facing wrappers around the backend's pure validation helpers."""

from fastapi import HTTPException

from ..path_safety import validate_file_component, validate_session_id


def require_session_id(value: str) -> str:
    try:
        return validate_session_id(value)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


def require_file_component(value: str) -> str:
    try:
        return validate_file_component(value)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
