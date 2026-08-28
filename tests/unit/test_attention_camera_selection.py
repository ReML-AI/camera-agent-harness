import pytest

from scripts.gaze.calibration import CalibrationStore, MissingCalibrationError
from scripts.gaze.classify_gaze_targets import (
    ATTENTION_LABELS,
    EligibilityStatus,
    SegmentIneligibilityReason,
    build_attention_artifact,
    build_selected_camera_samples,
    classify_selected_segments,
    preflight_eligibility,
)
from scripts.core.schema import load_schema


def _calibrations(include_cam2=True):
    cameras = {
        "cam1": {
            "patient_bbox_normalized": [0.4, 0.7, 0.6, 0.9],
            "reference_frame": {"frame_index": 1, "timestamp_seconds": None},
            "annotator": "test",
            "source_annotation": "synthetic",
        }
    }
    if include_cam2:
        cameras["cam2"] = {
            "patient_bbox_normalized": [0.3, 0.7, 0.7, 0.95],
            "reference_frame": {"frame_index": 1, "timestamp_seconds": None},
            "annotator": "test",
            "source_annotation": "synthetic",
        }
    return CalibrationStore(
        {
            "schema_version": "1.0.0",
            "coordinate_system": {
                "box_format": "normalized_xyxy",
                "origin": "top-left",
                "range": [0, 1],
            },
            "sessions": {"synthetic-session": cameras},
        }
    )


def _best_angles():
    return {
        "session_id": "synthetic-session",
        "segments": [
            {
                "transcript_segment_id": "segment-1",
                "speaker_id": "speaker-a",
                "start_seconds": 0.0,
                "end_seconds": 1.0,
                "selected_camera_id": "cam1",
                "selected_track_id": "track:cam1:1",
            },
            {
                "transcript_segment_id": "segment-2",
                "speaker_id": "speaker-a",
                "start_seconds": 1.0,
                "end_seconds": 2.0,
                "selected_camera_id": "cam2",
                "selected_track_id": "track:cam2:7",
            },
        ],
    }


def _identity():
    return {
        "session_id": "synthetic-session",
        "speakers": [
            {
                "speaker_id": "speaker-a",
                "camera_candidates": [
                    {"camera_id": "cam1", "track_id": "track:cam1:1", "status": "linked"},
                    {"camera_id": "cam2", "track_id": "track:cam2:7", "status": "linked"},
                ],
            }
        ],
    }


def _pose(camera, track, timestamp):
    return {
        "metadata": {"fps": 10.0},
        "tracks": {
            track: {
                "poses": [
                    {
                        "frame": int(timestamp * 10),
                        "aligned_timestamp_seconds": timestamp,
                        "yaw": 0.0,
                        "bbox_normalized": [0.45, 0.1, 0.55, 0.2],
                    }
                ]
            }
        },
    }


def _poses():
    return {
        "cam1": _pose("cam1", "track:cam1:1", 0.5),
        "cam2": _pose("cam2", "track:cam2:7", 1.5),
    }


def test_attention_target_set_and_output_schema_have_exactly_three_labels():
    assert ATTENTION_LABELS == ("patient", "person", "other")
    attention_schema = load_schema("visual_records")["$defs"]["attention"]
    assert attention_schema["properties"]["raw_label"]["enum"] == list(ATTENTION_LABELS)
    assert attention_schema["properties"]["label"]["enum"] == list(ATTENTION_LABELS)


def test_selected_camera_changes_per_segment_and_is_recorded_per_sample():
    samples = build_selected_camera_samples(_best_angles(), _poses())
    assert set(samples) == {"cam1", "cam2"}
    assert samples["cam1"][0].track_id == "track:cam1:1"
    assert samples["cam2"][0].track_id == "track:cam2:7"

    records = classify_selected_segments(
        "synthetic-session",
        calibrations=_calibrations(),
        best_angles=_best_angles(),
        head_pose_by_camera=_poses(),
    )
    assert [record["camera_id"] for record in records] == ["cam1", "cam2"]
    assert all(record["calibration_camera_id"] == record["camera_id"] for record in records)


def test_preflight_reports_missing_calibration_before_classification():
    report = preflight_eligibility(
        "synthetic-session",
        calibrations=_calibrations(include_cam2=False),
        best_angles=_best_angles(),
        identity_map=_identity(),
        head_pose_by_camera=_poses(),
    )
    assert report.status is EligibilityStatus.MISSING_CALIBRATION
    assert report.missing_camera_ids == ("cam2",)
    with pytest.raises(MissingCalibrationError) as raised:
        classify_selected_segments(
            "synthetic-session",
            calibrations=_calibrations(include_cam2=False),
            best_angles=_best_angles(),
            head_pose_by_camera=_poses(),
        )
    assert raised.value.camera_id == "cam2"

    with pytest.raises(MissingCalibrationError) as artifact_error:
        build_attention_artifact(
            "synthetic-session",
            calibrations=_calibrations(include_cam2=False),
            best_angles=_best_angles(),
            identity_map=_identity(),
            head_pose_by_camera=_poses(),
        )
    assert artifact_error.value.camera_id == "cam2"


def test_preflight_reports_missing_identity_but_partial_pose_keeps_session_eligible():
    missing_identity = preflight_eligibility(
        "synthetic-session",
        calibrations=_calibrations(),
        best_angles=_best_angles(),
        identity_map=None,
        head_pose_by_camera=_poses(),
    )
    assert missing_identity.status is EligibilityStatus.MISSING_IDENTITY

    partial_pose = preflight_eligibility(
        "synthetic-session",
        calibrations=_calibrations(),
        best_angles=_best_angles(),
        identity_map=_identity(),
        head_pose_by_camera={"cam1": _poses()["cam1"], "cam2": None},
    )
    assert partial_pose.status is EligibilityStatus.ELIGIBLE
    assert partial_pose.missing_camera_ids == ()


def test_partial_pose_classifies_covered_segment_and_counts_uncovered_segment():
    artifact = build_attention_artifact(
        "synthetic-session",
        calibrations=_calibrations(),
        best_angles=_best_angles(),
        identity_map=_identity(),
        head_pose_by_camera={"cam1": _poses()["cam1"], "cam2": None},
    )

    assert artifact["eligibility"]["status"] == EligibilityStatus.ELIGIBLE.value
    assert set(artifact["tracks"]) == {"cam1:track:cam1:1"}
    assert len(artifact["tracks"]["cam1:track:cam1:1"]["poses"]) == 1
    assert artifact["segment_eligibility"] == [
        {
            "transcript_segment_id": "segment-1",
            "camera_id": "cam1",
            "track_id": "track:cam1:1",
            "status": "classified",
            "reason": None,
            "pose_samples_classified": 1,
        },
        {
            "transcript_segment_id": "segment-2",
            "camera_id": "cam2",
            "track_id": "track:cam2:7",
            "status": "ineligible",
            "reason": SegmentIneligibilityReason.MISSING_POSE_ARTIFACT.value,
            "pose_samples_classified": 0,
        },
    ]
    diagnostics = artifact["capture_at_run"]
    assert diagnostics["segments_attempted"] == 2
    assert diagnostics["segments_classified"] == 1
    assert diagnostics["segments_ineligible"] == 1
    assert diagnostics["segments_ineligible_by_reason"][
        SegmentIneligibilityReason.MISSING_POSE_ARTIFACT.value
    ] == 1
    assert diagnostics["pose_samples_classified"] == 1


def test_pose_outside_segment_is_ineligible_absent_signal_not_zero_attention():
    poses = _poses()
    poses["cam2"] = _pose("cam2", "track:cam2:7", 2.5)
    artifact = build_attention_artifact(
        "synthetic-session",
        calibrations=_calibrations(),
        best_angles=_best_angles(),
        identity_map=_identity(),
        head_pose_by_camera=poses,
    )

    uncovered = artifact["segment_eligibility"][1]
    assert uncovered["reason"] == (
        SegmentIneligibilityReason.NO_USABLE_POSE_IN_SEGMENT.value
    )
    assert "cam2:track:cam2:7" not in artifact["tracks"]
    assert artifact["capture_at_run"]["segments_attempted"] == 2
    assert artifact["capture_at_run"]["segments_ineligible"] == 1
