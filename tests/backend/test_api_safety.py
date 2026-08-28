from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.app.routers._validation import require_session_id
from backend.app.routers.videos import range_requests_response


ROOT = Path(__file__).resolve().parents[2]


def test_http_session_validator_returns_a_client_error_for_traversal():
    with pytest.raises(HTTPException) as raised:
        require_session_id("../../escape")
    assert raised.value.status_code == 400


def test_large_explicit_range_is_clamped_to_the_file_end(tmp_path: Path):
    video = tmp_path / "sample.mp4"
    video.write_bytes(b"0123456789")
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/video",
            "headers": [(b"range", b"bytes=0-9999")],
        }
    )

    response = range_requests_response(request, video)

    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 0-9/10"
    assert response.headers["content-length"] == "10"


def test_auxiliary_api_defaults_to_localhost_without_reload():
    source = (ROOT / "backend" / "run.py").read_text(encoding="utf-8")
    assert 'host="127.0.0.1"' in source
    assert "reload=False" in source
