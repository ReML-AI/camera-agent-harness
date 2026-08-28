from copy import deepcopy

import pytest
from jsonschema import ValidationError

from scripts.core.schema import load_schema, validate_record


ZERO = "0" * 64


def valid_session():
    return {
        "schema_version": "1.0.0", "session_id": "session-001",
        "session_origin": "2026-01-01T00:00:00Z", "session_end_seconds": 10,
        "streams": [{
            "stream_id": "cam1", "kind": "room_video",
            "time_base": {"numerator": 1, "denominator": 90000},
            "fps": {"numerator": 25, "denominator": 1}, "duration_seconds": 10,
            "sync_transform": {"transform_id": "sync-1", "version": "1.0.0", "offset_seconds": 0, "drift": 1},
            "source_sha256": ZERO,
        }],
    }


def test_all_ten_contract_ids_are_owned_by_versioned_schemas():
    names = ["session", "upstream_artifact", "identity_map", "best_angle", "visual_records", "context_window", "flag_artifact", "keyword_run", "focal_run"]
    ids = {item for name in names for item in load_schema(name)["x-definition-ids"]}
    assert ids == {f"CONTRACT-{number:02d}-{suffix}" for number, suffix in [
        (1, "TIME"), (2, "IDENTITY"), (3, "SPEAKER-LINK"),
        (4, "BEST-ANGLE-GATE"), (5, "VISUAL"), (6, "CONTEXT"),
        (7, "FLAGS"), (8, "KTM"), (9, "FOCAL"), (10, "EVIDENCE"),
    ]}


def test_session_accepts_seconds_and_rejects_wrong_units_unknown_fields_and_ids():
    validate_record("session", valid_session())
    bad = deepcopy(valid_session())
    bad["session_id"] = "../escape"
    with pytest.raises(ValidationError):
        validate_record("session", bad)
    bad = deepcopy(valid_session())
    bad["streams"][0]["timestamp_milliseconds"] = 5
    with pytest.raises(ValidationError):
        validate_record("session", bad)


def test_context_requires_exact_five_fields_and_three_attention_labels():
    coverage = {"evidence_id": "coverage-window-1", **{
        name: {"present": False, "delivered": True, "evidence_ids": []}
        for name in ["transcript", "speaker_dynamics", "visual_scene", "visual_attention"]
    }}
    record = {
        "schema_version": "1.0.0", "window_id": "window-1", "session_id": "session-001",
        "start_seconds": 0, "end_seconds": 30, "flag_ids": ["flag-1"],
        "context": {
            "transcript": [], "speaker_dynamics": {}, "visual_scene": None,
            "visual_attention": {
                "labels": ["patient", "person", "other"],
                "distribution": {"patient": 0, "person": 0, "other": 0},
                "records": [], "events": [],
            },
            "modality_coverage": coverage,
        },
        "provenance": {},
    }
    validate_record("context_window", record)
    bad = deepcopy(record)
    bad["context"]["gaze"] = []
    with pytest.raises(ValidationError):
        validate_record("context_window", bad)
    bad = deepcopy(record)
    bad["context"]["visual_attention"]["labels"] = ["teammate"]
    with pytest.raises(ValidationError):
        validate_record("context_window", bad)
    stale = deepcopy(record)
    stale["context"]["visual_attention"]["labels"] = [
        "patient", "monitor", "person", "other"
    ]
    stale["context"]["visual_attention"]["distribution"]["monitor"] = 0
    with pytest.raises(ValidationError):
        validate_record("context_window", stale)
    stale_event = deepcopy(record)
    stale_event["context"]["visual_attention"]["events"] = [{
        "type": "convergence", "target": "monitor"
    }]
    with pytest.raises(ValidationError):
        validate_record("context_window", stale_event)


def test_visual_record_schema_carries_gated_attention_interface():
    record = {
        "schema_version": "1.0.0", "session_id": "synthetic-session",
        "attention": [{
            "evidence_id": "attention-1", "camera_id": "cam1",
            "track_id": "track:cam1:1", "aligned_timestamp_seconds": 1,
            "yaw_degrees": 0, "raw_label": "person", "label": "person",
            "angular_distance_degrees": 10, "target_track_id": "track:cam1:2",
            "calibration_version": "synthetic-layout",
            "assignment_procedure_id": "synthetic-assignment",
            "smoothing_procedure_id": "synthetic-smoothing",
            "threshold_degrees": 35.0, "rolling_mode_window": 5,
            "exact_frame_gate": "exact_frame_asd_positive",
            "exact_frame_asd_score": 0.87,
        }],
    }
    validate_record("visual_records", record)
