"""Hardened CPU-testable boundaries for upstream GPU/ML extractors.

The boundary validates local components before any heavyweight framework is imported.
It never downloads a model. Extractor-specific inference stays in the named wrappers;
all wrappers serialize through this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from scripts.core.errors import ContractError
from scripts.core.records import Provenance, StreamMetadata, sha256_file, sha256_json
from scripts.core.schema import validate_record


EXTRACTORS = {
    "yolov8", "whisperx", "light_asd", "6drepnet360", "clip_scene", "easyocr",
}


@dataclass(frozen=True)
class LocalComponent:
    component_id: str
    component_version: str
    code_path: Path
    code_sha256: str
    weights_path: Path
    weights_sha256: str
    config: dict[str, Any]

    def validate(self) -> None:
        if self.component_id not in EXTRACTORS:
            raise ContractError(f"unsupported extractor: {self.component_id}")
        for label, path, expected in (
            ("code", self.code_path, self.code_sha256),
            ("weights", self.weights_path, self.weights_sha256),
        ):
            if not path.is_file():
                raise ContractError(f"{self.component_id} local {label} file is unavailable: {path}")
            actual = sha256_file(path)
            if actual != expected:
                raise ContractError(
                    f"{self.component_id} {label} checksum mismatch: expected {expected}, got {actual}"
                )


def canonical_sample(
    *,
    evidence_id: str,
    stream: StreamMetadata,
    native_index: int,
    values: dict[str, Any],
) -> dict[str, Any]:
    native, aligned = stream.frame_timestamp(native_index)
    return {
        "evidence_id": evidence_id,
        "stream_id": stream.stream_id,
        "native_index": native_index,
        "native_timestamp_seconds": native,
        "aligned_timestamp_seconds": aligned,
        "sync_transform_id": stream.synchronization.transform_id,
        **values,
    }


def build_upstream_artifact(
    *,
    session_id: str,
    artifact_id: str,
    component: LocalComponent,
    stream: StreamMetadata,
    records: Iterable[dict[str, Any]] = (),
    status: str | None = None,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    component.validate()
    materialized = list(records)
    final_status = status or ("success_nonempty" if materialized else "success_empty")
    if final_status in {"failed", "unavailable"} and materialized:
        raise ContractError(f"{final_status} artifact cannot contain records")
    if final_status in {"failed", "unavailable"} and not failure_reason:
        raise ContractError(f"{final_status} artifact requires a failure reason")
    provenance = Provenance(
        component_id=component.component_id,
        component_version=component.component_version,
        config_sha256=sha256_json(component.config),
        artifact_sha256=component.weights_sha256,
        source_stream_id=stream.stream_id,
    )
    artifact = {
        "schema_version": "1.0.0",
        "session_id": session_id,
        "artifact_id": artifact_id,
        "extractor": component.component_id,
        "status": final_status,
        "failure_reason": failure_reason,
        "records": materialized,
        "provenance": provenance.to_dict(),
    }
    validate_record("upstream_artifact", artifact)
    return artifact
