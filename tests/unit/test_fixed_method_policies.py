from scripts.gaze.classify_gaze_targets import (
    AttentionInput,
    FixedCausalRollingMode,
    ReferenceCalibratedAttention,
)
from scripts.gaze.calibration import PatientZoneCalibration
from scripts.flags.clip_urgency import ClipUrgencyAdapter


def _attention_sample(grid_index, yaw=0.0, gate="exact_frame_asd_positive"):
    return AttentionInput(
        f"attention-{grid_index}", "cam1", "track:cam1:observer", float(grid_index), yaw,
        {
            "grid_index": grid_index,
            "transcript_segment_id": "segment-1",
            # Production stamps a verdict on every candidate; smoothing only carries the
            # positive ones, so a helper without this tests nothing.
            "exact_frame_gate": gate,
            "bbox_normalized": [0.45, 0.05, 0.55, 0.15],
            "person_targets": [
                {
                    "track_id": "track:cam1:other",
                    "bbox_normalized": [0.0, 0.4, 0.1, 0.6],
                },
            ],
        },
    )


def test_fixed_attention_geometry_and_causal_tie_policy_run_in_paper_mode():
    calibration = PatientZoneCalibration(
        schema_version="1.0.0",
        session_id="synthetic-session",
        camera_id="cam1",
        patient_bbox_normalized=(0.4, 0.7, 0.6, 0.9),
        reference_frame_index=1,
        reference_timestamp_seconds=None,
        annotator="test",
        source_annotation="synthetic",
    )
    adapter = ReferenceCalibratedAttention(calibration, paper_mode=True)
    record = adapter.classify([_attention_sample(0)])[0]
    assert record["raw_label"] == "patient"
    assert record["label"] == "patient"
    assert record["assignment_procedure_id"] == "image-box-attention-assignment-v2.0.0"

    smoother = FixedCausalRollingMode()
    labels = smoother.smooth_samples(
        [_attention_sample(0), _attention_sample(1), _attention_sample(3)],
        ["patient", "person", "other"],
    )
    # The two-label tie uses the most recent label; the missing grid index resets history.
    assert list(labels) == ["patient", "person", "other"]


def _clip_frame(camera, bin_index, emergency_max):
    return {
        "evidence_id": f"clip-{camera}-{bin_index}",
        "camera_id": camera,
        "bin_index": bin_index,
        "aligned_timestamp_seconds": bin_index + 0.5,
        "routine_logits": [0.0, 0.0, 0.0, 0.0],
        "emergency_logits": [emergency_max, -1.0, -1.0, -1.0, -1.0, -1.0],
    }


def test_fixed_clip_policy_is_strict_and_retains_five_consecutive_bins():
    frames = [_clip_frame("cam1", index, 0.4) for index in range(5)]
    frames.extend(_clip_frame("cam2", index, 0.0) for index in range(6))
    artifact = ClipUrgencyAdapter(paper_mode=True).run("session-new", frames)

    assert len(artifact.flags) == 1
    flag = artifact.flags[0]
    assert (flag.start_seconds, flag.end_seconds) == (0.0, 5.0)
    assert flag.payload["camera_ids"] == ["cam1"]
    assert flag.payload["score_record"]["positive_bin_ids"] == [0, 1, 2, 3, 4]


def test_smoothing_never_carries_a_gate_excluded_frame_into_a_delivered_label():
    """An excluded neighbour must not decide a delivered frame's label.

    Smoothing once ran over every candidate, so a run of excluded frames could win the
    rolling mode and overwrite the label on a frame the gate admitted -- the delivered
    record then disagreed with the exact-frame rule the method declares.
    """
    smoother = FixedCausalRollingMode()
    samples = [
        _attention_sample(0, gate="exact_frame_asd_not_positive"),
        _attention_sample(1, gate="exact_frame_asd_not_positive"),
        _attention_sample(2, gate="exact_frame_asd_not_positive"),
        _attention_sample(3),
    ]
    labels = smoother.smooth_samples(samples, ["person", "person", "person", "patient"])

    # Three excluded "person" frames would carry the mode if they counted.
    assert list(labels)[3] == "patient"


def test_smoothing_still_uses_gate_positive_neighbours():
    smoother = FixedCausalRollingMode()
    samples = [_attention_sample(i) for i in range(4)]
    labels = smoother.smooth_samples(samples, ["person", "person", "person", "patient"])

    # Contiguous admitted neighbours are exactly what the rolling mode is for.
    assert list(labels)[3] == "person"
