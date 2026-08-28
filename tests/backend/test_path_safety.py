from pathlib import Path

import pytest

from backend.app.path_safety import (
    path_below,
    validate_file_component,
    validate_session_id,
)


@pytest.mark.parametrize("value", ["session_001", "pilot-2", "A9"])
def test_session_ids_accept_only_simple_identifiers(value):
    assert validate_session_id(value) == value


@pytest.mark.parametrize("value", ["", ".", "..", "../escape", "a/b", "a\\b", "a b"])
def test_session_ids_reject_path_syntax(value):
    with pytest.raises(ValueError):
        validate_session_id(value)


def test_file_component_allows_extensions_but_not_traversal():
    assert validate_file_component("frame-001.jpg") == "frame-001.jpg"
    with pytest.raises(ValueError):
        validate_file_component("../frame.jpg")


def test_path_below_proves_containment(tmp_path: Path):
    assert path_below(tmp_path, "session_001", "artifact.json").is_relative_to(
        tmp_path.resolve()
    )
    with pytest.raises(ValueError):
        path_below(tmp_path, "..", "escape.json")
