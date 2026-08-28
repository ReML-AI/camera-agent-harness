import pytest
from scripts.utils.session_paths import (
    PROJECT_ROOT, session_dir, raw_dir, processed_dir,
    metrics_dir, videos_dir, prerequisites_dir, artifacts_dir,
    provenance_dir, configuration_dir,
)
from scripts.core.errors import ContractError

def test_project_root_exists():
    assert PROJECT_ROOT.exists()
    assert (PROJECT_ROOT / "scripts").is_dir()

def test_session_dir():
    p = session_dir("session_001")
    assert p == PROJECT_ROOT / "data" / "sessions" / "session_001"

def test_raw_dir():
    p = raw_dir("session_001")
    assert p.name == "raw"
    assert p.parent.name == "session_001"

def test_processed_dir():
    p = processed_dir("session_001")
    assert p.name == "processed"

def test_metrics_dir():
    p = metrics_dir("session_001")
    assert p.name == "metrics"

def test_videos_dir():
    p = videos_dir("session_001")
    assert p.name == "videos"

def test_prerequisites_dir():
    p = prerequisites_dir("session_001")
    assert p.name == "prerequisites"

def test_canonical_additional_paths():
    assert artifacts_dir("session_001").name == "artifacts"
    assert provenance_dir("session_001").name == "provenance"
    assert configuration_dir("session_001").name == "configuration"

def test_session_id_cannot_escape_session_root():
    with pytest.raises(ContractError):
        session_dir("../outside")
