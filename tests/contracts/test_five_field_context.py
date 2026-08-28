from jsonschema import ValidationError
import pytest

from scripts.analytics.assemble_multimodal_windows import SEMANTIC_FIELDS
from scripts.core.schema import validate_record
from tests.test_multimodal_windows import sample_window


def test_five_fields_are_exact_not_aliases_or_envelope_metadata():
    window = sample_window()
    assert tuple(window["context"]) == SEMANTIC_FIELDS
    assert "window_id" not in window["context"]
    assert "flags" not in window["context"]
    assert "gaze" not in window["context"]
    assert "dynamics" not in window["context"]
    validate_record("context_window", window)


def test_sixth_semantic_field_is_rejected_by_schema():
    window = sample_window()
    window["context"]["extra_modality"] = {}
    with pytest.raises(ValidationError):
        validate_record("context_window", window)
