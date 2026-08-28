"""Strict loader for author-annotated mannequin zones."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from scripts.core.errors import ContractError


SCHEMA_VERSION = "1.0.0"
CALIBRATION_PATH = Path(__file__).with_name("patient_zone_calibrations.json")
CALIBRATION_SCHEMA_PATH = Path(__file__).with_name("patient_zone_calibration.schema.json")


class CalibrationError(ContractError):
    """Base error for invalid or unavailable attention calibration."""

    code = "ATTENTION_CALIBRATION_ERROR"


class CalibrationSchemaError(CalibrationError):
    """Raised when the versioned calibration artifact is malformed."""

    code = "ATTENTION_CALIBRATION_SCHEMA_INVALID"


class MissingCalibrationError(CalibrationError):
    """Raised when no authored zone exists for the requested session and camera."""

    code = "ATTENTION_CALIBRATION_MISSING"

    def __init__(self, session_id: str, camera_id: str) -> None:
        self.session_id = session_id
        self.camera_id = camera_id
        super().__init__(f"{self.code}: no patient zone for {session_id}/{camera_id}")


@dataclass(frozen=True)
class PatientZoneCalibration:
    schema_version: str
    session_id: str
    camera_id: str
    patient_bbox_normalized: tuple[float, float, float, float]
    reference_frame_index: int | None
    reference_timestamp_seconds: float | None
    annotator: str
    source_annotation: str


class CalibrationStore:
    """Validated, immutable access to the authored calibration artifact."""

    def __init__(self, document: Mapping[str, Any]) -> None:
        schema = json.loads(CALIBRATION_SCHEMA_PATH.read_text(encoding="utf-8"))
        errors = sorted(
            Draft202012Validator(schema).iter_errors(document),
            key=lambda item: tuple(str(part) for part in item.absolute_path),
        )
        if errors:
            location = "/".join(str(part) for part in errors[0].absolute_path) or "<root>"
            raise CalibrationSchemaError(f"{CalibrationSchemaError.code} at {location}: {errors[0].message}")
        self._document = document
        self.schema_version = str(document["schema_version"])
        for session_id, cameras in document["sessions"].items():
            for camera_id, record in cameras.items():
                x1, y1, x2, y2 = (float(value) for value in record["patient_bbox_normalized"])
                if not x1 < x2 or not y1 < y2:
                    raise CalibrationSchemaError(
                        f"{CalibrationSchemaError.code}: invalid xyxy ordering for "
                        f"{session_id}/{camera_id}"
                    )

    @classmethod
    def load(cls, path: Path = CALIBRATION_PATH) -> "CalibrationStore":
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CalibrationSchemaError(
                f"{CalibrationSchemaError.code}: cannot load {path}: {exc}"
            ) from exc
        if not isinstance(document, Mapping):
            raise CalibrationSchemaError(
                f"{CalibrationSchemaError.code}: calibration root must be a mapping"
            )
        return cls(document)

    def has(self, session_id: str, camera_id: str) -> bool:
        sessions = self._document["sessions"]
        return session_id in sessions and camera_id in sessions[session_id]

    def get(self, session_id: str, camera_id: str) -> PatientZoneCalibration:
        if not self.has(session_id, camera_id):
            raise MissingCalibrationError(session_id, camera_id)
        record = self._document["sessions"][session_id][camera_id]
        reference = record["reference_frame"]
        return PatientZoneCalibration(
            schema_version=self.schema_version,
            session_id=session_id,
            camera_id=camera_id,
            patient_bbox_normalized=tuple(
                float(value) for value in record["patient_bbox_normalized"]
            ),
            reference_frame_index=reference["frame_index"],
            reference_timestamp_seconds=(
                None
                if reference["timestamp_seconds"] is None
                else float(reference["timestamp_seconds"])
            ),
            annotator=record["annotator"],
            source_annotation=record["source_annotation"],
        )


def load_patient_zone(
    session_id: str,
    camera_id: str,
    path: Path = CALIBRATION_PATH,
) -> PatientZoneCalibration:
    """Load one exact calibration; absence is always a typed hard failure."""

    return CalibrationStore.load(path).get(session_id, camera_id)


__all__ = [
    "CALIBRATION_PATH",
    "CALIBRATION_SCHEMA_PATH",
    "SCHEMA_VERSION",
    "CalibrationError",
    "CalibrationSchemaError",
    "CalibrationStore",
    "MissingCalibrationError",
    "PatientZoneCalibration",
    "load_patient_zone",
]
