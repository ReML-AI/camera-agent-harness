from hashlib import sha256

import pytest

from scripts.adapters.upstream import LocalComponent, build_upstream_artifact, canonical_sample
from scripts.core.errors import ContractError
from scripts.core.records import StreamMetadata, SynchronizationTransform


def _stream():
    return StreamMetadata(
        stream_id="cam1", session_id="session-001",
        time_base_numerator=1, time_base_denominator=1000,
        fps_numerator=25, fps_denominator=1, duration_seconds=5,
        synchronization=SynchronizationTransform("sync-001", 0, 1),
    )


def _component(tmp_path, component_id="yolov8"):
    code = tmp_path / "component.py"
    weight = tmp_path / "weights.bin"
    code.write_bytes(b"pinned-code")
    weight.write_bytes(b"pinned-weight")
    return LocalComponent(
        component_id=component_id, component_version="v1",
        code_path=code, code_sha256=sha256(code.read_bytes()).hexdigest(),
        weights_path=weight, weights_sha256=sha256(weight.read_bytes()).hexdigest(),
        config={"threshold": 0.25},
    )


@pytest.mark.parametrize("component_id", [
    "yolov8", "whisperx", "light_asd", "6drepnet360", "clip_scene", "easyocr",
])
def test_every_named_adapter_emits_schema_valid_provenance(tmp_path, component_id):
    component = _component(tmp_path, component_id)
    sample = canonical_sample(
        evidence_id="evidence-001", stream=_stream(), native_index=25,
        values={"camera_id": "cam1"},
    )
    artifact = build_upstream_artifact(
        session_id="session-001", artifact_id=f"artifact-{component_id}",
        component=component, stream=_stream(), records=[sample],
    )
    assert artifact["status"] == "success_nonempty"
    assert artifact["records"][0]["aligned_timestamp_seconds"] == 1.0
    assert artifact["provenance"]["artifact_sha256"] == component.weights_sha256


def test_checksum_mismatch_fails_before_inference(tmp_path):
    component = _component(tmp_path)
    component.weights_path.write_bytes(b"changed")
    with pytest.raises(ContractError, match="checksum mismatch"):
        build_upstream_artifact(
            session_id="session-001", artifact_id="artifact-yolo",
            component=component, stream=_stream(), records=[],
        )


def test_failure_status_is_explicit_and_contains_no_records(tmp_path):
    artifact = build_upstream_artifact(
        session_id="session-001", artifact_id="artifact-yolo",
        component=_component(tmp_path), stream=_stream(), status="unavailable",
        failure_reason="authorized weights not provisioned",
    )
    assert artifact["status"] == "unavailable"
    assert artifact["records"] == []
