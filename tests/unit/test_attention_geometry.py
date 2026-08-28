import pytest

from scripts.core.errors import ContractError
from scripts.gaze.classify_gaze_targets import (
    ATTENTION_LABELS,
    ATTENTION_THRESHOLD_DEGREES,
    ROLLING_MODE_WINDOW,
    Assignment,
    AttentionInput,
    ReferenceCalibratedAttention,
)
from scripts.gaze.calibration import PatientZoneCalibration


class SyntheticProcedure:
    procedure_id = "synthetic-assignment-v1"
    threshold_degrees = 35.0

    def __init__(self, labels=("patient",)):
        self.labels = labels
        self.index = 0

    def assign(self, sample, calibration):
        label = self.labels[self.index % len(self.labels)]
        self.index += 1
        return Assignment(label, 10.0, "track:cam1:2" if label == "person" else None)


class SyntheticSmoothing:
    procedure_id = "synthetic-mode-policy"
    window_size = 5

    def smooth(self, labels):
        return labels


def calibration():
    return PatientZoneCalibration(
        schema_version="1.0.0",
        session_id="synthetic-session",
        camera_id="cam1",
        patient_bbox_normalized=(0.4, 0.6, 0.6, 0.9),
        reference_frame_index=1,
        reference_timestamp_seconds=None,
        annotator="test",
        source_annotation="synthetic",
    )


def sample():
    return AttentionInput("attention-1", "cam1", "track:cam1:1", 1.0, 0.0, {})


def test_paper_constants_are_exactly_the_three_values_stated_by_the_paper():
    assert ATTENTION_LABELS == ("patient", "person", "other")
    assert ATTENTION_THRESHOLD_DEGREES == 35.0
    assert ROLLING_MODE_WINDOW == 5


def test_custom_assignment_procedure_is_available_only_outside_paper_mode():
    procedure = SyntheticProcedure()
    adapter = ReferenceCalibratedAttention(
        calibration(), procedure, smoothing_procedure=SyntheticSmoothing(), paper_mode=False
    )
    result = adapter.classify([sample()])[0]
    assert procedure.index == 1
    assert result["label"] == "patient"


def test_paper_mode_rejects_caller_supplied_attention_substitutes():
    with pytest.raises(ContractError, match="fixed target-assignment"):
        ReferenceCalibratedAttention(
            calibration(), SyntheticProcedure(),
            smoothing_procedure=SyntheticSmoothing(), paper_mode=True,
        )


def test_synthetic_adapter_preserves_person_target_only_as_provenance():
    adapter = ReferenceCalibratedAttention(
        calibration(), SyntheticProcedure(("person",)),
        smoothing_procedure=SyntheticSmoothing(), paper_mode=False,
    )
    result = adapter.classify([sample()])[0]
    assert result["label"] == "person"
    assert result["target_track_id"] == "track:cam1:2"
    assert result["threshold_degrees"] == 35.0


def test_adapter_rejects_dynamic_or_unsupported_labels():
    adapter = ReferenceCalibratedAttention(
        calibration(), SyntheticProcedure(("speaker-A",)),
        smoothing_procedure=SyntheticSmoothing(), paper_mode=False,
    )
    with pytest.raises(ContractError, match="unsupported label"):
        adapter.classify([sample()])
