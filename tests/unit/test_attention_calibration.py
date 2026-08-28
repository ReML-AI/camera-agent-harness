import json

import pytest

from scripts.gaze.calibration import (
    CALIBRATION_PATH,
    CalibrationSchemaError,
    CalibrationStore,
    MissingCalibrationError,
)


def test_calibration_covers_every_session_and_camera():
    """All 27 camera-views are annotated; a gap here means a session cannot be scored."""
    store = CalibrationStore.load(CALIBRATION_PATH)
    # Assert the invariant, not a specific box: a hard-coded coordinate breaks on any
    # legitimate re-annotation (session_001's recording was replaced once already).
    for index in range(1, 10):
        session_id = f"session_{index:03d}"
        for camera_id in ("cam1", "cam2", "cam3"):
            assert store.has(session_id, camera_id), f"{session_id}/{camera_id} uncalibrated"
            x1, y1, x2, y2 = store.get(session_id, camera_id).patient_bbox_normalized
            assert 0.0 <= x1 < x2 <= 1.0, f"{session_id}/{camera_id} bad x extent"
            assert 0.0 <= y1 < y2 <= 1.0, f"{session_id}/{camera_id} bad y extent"


def test_missing_session_camera_calibration_fails_with_typed_error(tmp_path):
    """A gap must fail loudly rather than fall back to a guessed region.

    The shipped calibration is complete, so the gap is constructed here instead of
    relying on a real one.
    """
    document = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    del document["sessions"]["session_002"]["cam2"]
    path = tmp_path / "incomplete.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    store = CalibrationStore.load(path)
    with pytest.raises(MissingCalibrationError) as raised:
        store.get("session_002", "cam2")
    assert raised.value.code == "ATTENTION_CALIBRATION_MISSING"
    assert raised.value.session_id == "session_002"
    assert raised.value.camera_id == "cam2"


def test_calibration_loader_rejects_reversed_boxes(tmp_path):
    document = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    document["sessions"]["session_001"]["cam1"]["patient_bbox_normalized"] = [
        0.8, 0.2, 0.1, 0.9
    ]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(CalibrationSchemaError, match="invalid xyxy ordering"):
        CalibrationStore.load(path)


def test_attention_evidence_ids_satisfy_the_evidence_id_contract():
    """Attention ids used colons, which the evidence_id pattern rejects.

    It never surfaced because no attention record had ever reached a context window:
    the moment Stage 9 produced output, Stage 13 failed schema validation on the first
    one. Colons are reserved for canonical track ids.
    """
    import inspect
    import re

    from scripts.core.records import ID_RE
    from scripts.gaze import classify_gaze_targets

    source = inspect.getsource(classify_gaze_targets)
    minted = re.findall(r'evidence_id=f"([^"]+)"', source)
    assert minted, "no evidence_id template found"

    for template in minted:
        concrete = re.sub(r"\{[^}]+\}", "segment-000020", template)
        assert ID_RE.fullmatch(concrete), f"{template} yields an invalid evidence_id"


def test_exact_frame_gate_separates_missing_from_non_positive():
    """"We could not check" and "we checked and it failed" are different facts.

    A missing join fails closed for the canonical stream, but it is counted apart from a
    finite non-positive score so the funnel can distinguish a coverage gap in the ASD
    artifact from a frame the gate genuinely rejected.
    """
    from scripts.gaze.classify_gaze_targets import (
        EXACT_GATE_MISSING,
        EXACT_GATE_NON_POSITIVE,
        EXACT_GATE_PASSED,
        build_asd_score_index,
        exact_frame_gate,
    )

    index = build_asd_score_index({"cam1": {"tracks": [{
        "track_id": "track:cam1:1",
        "samples": [
            {"frame_index": 10, "score": 1.5},
            {"frame_index": 11, "score": -0.4},
            {"frame_index": 12, "score": 0.0},
        ],
    }]}})

    assert exact_frame_gate(index, "cam1", "track:cam1:1", 10)[0] == EXACT_GATE_PASSED
    assert exact_frame_gate(index, "cam1", "track:cam1:1", 11)[0] == EXACT_GATE_NON_POSITIVE
    # Strictly positive: exactly zero does not pass.
    assert exact_frame_gate(index, "cam1", "track:cam1:1", 12)[0] == EXACT_GATE_NON_POSITIVE
    assert exact_frame_gate(index, "cam1", "track:cam1:1", 99)[0] == EXACT_GATE_MISSING


def test_only_gated_attention_reaches_a_window():
    """Ungated candidates stay in the gaze artifact but must never reach a prompt."""
    from scripts.analytics.assemble_multimodal_windows import _normalise_attention

    document = {"tracks": {"t": {"poses": [
        {"evidence_id": "attention-a", "aligned_timestamp_seconds": 1.0, "label": "patient",
         "exact_frame_gate": "exact_frame_asd_positive"},
        {"evidence_id": "attention-b", "aligned_timestamp_seconds": 2.0, "label": "patient",
         "exact_frame_gate": "exact_frame_asd_not_positive"},
        {"evidence_id": "attention-c", "aligned_timestamp_seconds": 3.0, "label": "patient",
         "exact_frame_gate": "exact_frame_asd_missing"},
    ]}}}

    kept = {record["evidence_id"] for record in _normalise_attention(document)}

    assert kept == {"attention-a"}


def test_a_record_without_a_gate_verdict_is_not_delivered():
    """No verdict means not admitted.

    Admitting the missing verdict is what let the gate ship as a no-op: stage 9 decided
    the gate, dropped it before serialization, and every record reached the assembler
    with no field at all -- so a filter that treats absent as passing filtered nothing.
    """
    from scripts.analytics.assemble_multimodal_windows import _normalise_attention

    document = {"tracks": {"t": {"poses": [
        {"evidence_id": "attention-old", "aligned_timestamp_seconds": 1.0, "label": "patient"},
    ]}}}

    assert _normalise_attention(document) == []


def test_gate_accounting_must_partition_its_candidates():
    """The three outcome counts must sum to the candidate count.

    The gate first shipped reading an attribute the dict records do not have, so every
    candidate fell into "unknown": 1,666 candidates with 0 delivered, 0 non-positive and
    0 missing, and nothing downstream noticed.
    """
    import pytest

    from scripts.core.errors import ContractError
    from scripts.gaze.classify_gaze_targets import _gate_comparison

    with pytest.raises(ContractError, match="does not partition"):
        _gate_comparison([{"evidence_id": "attention-x"}])


def test_gate_comparison_counts_each_outcome():
    from scripts.gaze.classify_gaze_targets import _gate_comparison

    summary = _gate_comparison([
        {"exact_frame_gate": "exact_frame_asd_positive"},
        {"exact_frame_gate": "exact_frame_asd_positive"},
        {"exact_frame_gate": "exact_frame_asd_not_positive"},
        {"exact_frame_gate": "exact_frame_asd_missing"},
    ])

    assert summary["candidate_record_count"] == 4
    assert summary["delivered_record_count"] == 2
    assert summary["non_positive_record_count"] == 1
    assert summary["missing_join_record_count"] == 1
    assert summary["admission_fraction"] == 0.5
