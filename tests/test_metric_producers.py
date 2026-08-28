import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.analytics.aggregate_paper_metrics import (
    MetricsValidationError,
    aggregate_paper_metrics,
)
from scripts.analytics.assemble_multimodal_windows import assemble_window
from scripts.analytics.compute_paper_metrics import (
    SOURCE_KEYS,
    _face_presence,
    compute_session_paper_metrics,
)
from scripts.focal.evidence import validate_citations
from scripts.run_manifest import RunManifest
from scripts.run_pipeline import _cohort_quantity_lineage


ROOT = Path(__file__).resolve().parents[1]


def _asd():
    return {
        "cam1": {"tracks": [{"track_id": "track:cam1:1", "samples": [
            {"aligned_timestamp_seconds": 0.2, "score": 0.4},
            {"aligned_timestamp_seconds": 1.2, "score": -0.1},
        ]}]},
        "cam2": {"tracks": [{"track_id": "track:cam2:2", "samples": [
            {"aligned_timestamp_seconds": 0.4, "score": 0.2},
            {"aligned_timestamp_seconds": 2.2, "score": 0.5},
        ]}]},
        "cam3": {"tracks": [{"track_id": "track:cam3:3", "samples": [
            {"aligned_timestamp_seconds": 1.4, "score": 0.3},
        ]}]},
    }


def _best_angles(session_id="session-new"):
    return {
        "session_id": session_id,
        "camera_status": {"cam1": "complete", "cam2": "complete", "cam3": "complete"},
        "segments": [
            {
                "transcript_segment_id": "segment-a",
                "speaker_id": "speaker-a",
                "start_seconds": 0.0,
                "end_seconds": 2.0,
                "selected_camera_id": "cam1",
                "selected_track_id": "track:cam1:1",
            },
            {
                "transcript_segment_id": "segment-b",
                "speaker_id": "speaker-b",
                "start_seconds": 2.0,
                "end_seconds": 3.0,
                "selected_camera_id": "cam2",
                "selected_track_id": "track:cam2:2",
            },
        ],
    }


def _head_pose():
    return {
        "cam1": {"metadata": {"fps": 2.0}, "tracks": {
            "track:cam1:1": {"poses": [
                {"frame": 1, "yaw": 1, "pitch": 2, "roll": 3},
                {"frame": 3, "yaw": 4, "pitch": 5, "roll": 6},
            ]}
        }},
        "cam2": {"tracks": {
            "track:cam2:2": {"poses": [
                {"aligned_timestamp_seconds": 2.2, "yaw": 7, "pitch": 8, "roll": 9},
            ]}
        }},
        "cam3": {"tracks": {
            "track:cam3:3": {"poses": [
                {"aligned_timestamp_seconds": 3.1, "yaw": 10, "pitch": 11, "roll": 12},
            ]}
        }},
    }


def _faces():
    by_camera = {}
    for camera, frame_ids in {
        "cam1": (5, 30),
        "cam2": (10, 55),
        "cam3": (35,),
    }.items():
        frames = [[] for _ in range(80)]
        for frame_id in frame_ids:
            frames[frame_id] = [{
                "frame": frame_id, "bbox": [1.0, 2.0, 3.0, 4.0], "conf": 0.95,
            }]
        by_camera[camera] = frames
    return by_camera


def _gaze(session_id="session-new"):
    return {
        "session_id": session_id,
        "attention": [
            {
                "evidence_id": f"{session_id}-attention-a",
                "camera_id": "cam1", "track_id": "track:cam1:1",
                "aligned_timestamp_seconds": 0.4, "label": "patient",
            },
            {
                "evidence_id": f"{session_id}-attention-b",
                "camera_id": "cam2", "track_id": "track:cam2:2",
                "aligned_timestamp_seconds": 2.7, "label": "person",
            },
        ],
    }


def _focal_runs(session_id="session-new"):
    control = {"runtime": "synthetic-fixed-control"}
    windows = _windows(session_id)["windows"]

    def evidence(moment_id, start, end, evidence_ids):
        return {
            "moment_id": moment_id, "start_seconds": start, "end_seconds": end,
            "category": "communication", "evidence_ids": evidence_ids,
        }

    t_moments = [
        evidence(f"{session_id}-t", 0, 1, [f"{session_id}-transcript-a"])
    ]
    m_moments = [
        evidence(
            f"{session_id}-m-hit", 0.5, 1.5, [f"{session_id}-transcript-a"]
        ),
        evidence(
            f"{session_id}-m-only", 2.5, 3.0,
            [f"{session_id}-transcript-b", f"{session_id}-attention-b"],
        ),
    ]

    return {
        "session_id": session_id,
        "K": {
            "session_id": session_id, "condition": "K",
            "matches": [{
                "match_id": f"{session_id}-k", "start_seconds": 0.0,
                "end_seconds": 0.5, "category": "communication",
            }],
        },
        "T": {
            "session_id": session_id, "condition": "T", "control_manifest": control,
            "moments": validate_citations(t_moments, windows=windows, condition="T"),
        },
        "M": {
            "session_id": session_id, "condition": "M", "control_manifest": control,
            "moments": validate_citations(m_moments, windows=windows, condition="M"),
        },
    }


def _windows(session_id="session-new"):
    return {
        "session_id": session_id,
        "windows": [assemble_window(
            session_id=session_id,
            window_id=f"{session_id}-window-0",
            start_seconds=0.0,
            end_seconds=3.2,
            flag_ids=[],
            transcript=[
                {
                    "evidence_id": f"{session_id}-transcript-a",
                    "speaker_id": "speaker-a", "start_seconds": 0.0,
                    "end_seconds": 1.0, "text": "synthetic first segment",
                },
                {
                    "evidence_id": f"{session_id}-transcript-b",
                    "speaker_id": "speaker-b", "start_seconds": 2.0,
                    "end_seconds": 3.0, "text": "synthetic second segment",
                },
            ],
            speaker_dynamics=None,
            visual_scene={
                "evidence_id": f"{session_id}-scene-0", "camera_id": "cam1",
            },
            attention_records=_gaze(session_id)["attention"],
            attention_events=[],
            provenance={"source_artifact_sha256": "a" * 64},
        )],
    }


def _sources(session_id="session-new", run_id="run-synthetic"):
    return {
        key: {
            "run_id": run_id, "session_id": session_id,
            "path": f"fixtures/{session_id}/{key}.json", "sha256": "a" * 64,
            "producer_stage": "synthetic_fixture", "measurement": "capture_at_run",
        }
        for key in SOURCE_KEYS
    }


def _metrics(session_id="session-new"):
    return compute_session_paper_metrics(
        session_manifest={"session_id": session_id, "session_end_seconds": 3.2},
        asd_by_camera=_asd(),
        head_pose_by_camera=_head_pose(),
        best_angles=_best_angles(session_id),
        identity_map={
            "session_id": session_id,
            "speakers": [
                {"speaker_id": "speaker-a", "link_status": "fully_linked"},
                {"speaker_id": "speaker-b", "link_status": "partially_linked"},
            ],
        },
        diarized_transcript={"segments": [
            {"transcript_segment_id": "segment-a", "speaker": "speaker-a", "start": 0.0, "end": 2.0},
            {"transcript_segment_id": "segment-b", "speaker": "speaker-b", "start": 2.0, "end": 3.0},
        ]},
        focal_runs=_focal_runs(session_id),
        multimodal_windows=_windows(session_id),
        faces_by_camera=_faces(),
        gaze_tracks=_gaze(session_id),
        run_id="run-synthetic",
        source_artifacts=_sources(session_id),
        run_manifest_path="fixtures/run_manifest.json",
    )


def test_session_producer_uses_shared_grid_stage3_assignment_and_strict_gate():
    result = _metrics()

    assert result["canonical_grid"]["denominator_bins"] == 4
    asd = result["table3"]["asd"]
    assert asd["best_cam"]["camera_id"] == "cam2"
    assert asd["best_cam"]["numerator"] == 2
    assert asd["union"]["covered_bin_ids"] == [0, 1, 2]
    assert asd["selected"]["covered_bin_ids"] == [0, 2]
    assert asd["inter_segment_bin_ids"] == [3]
    assert asd["selected"]["numerator"] <= asd["union"]["numerator"]

    assert result["table3"]["head_pose"]["selected"]["covered_bin_ids"] == [0, 2]
    assert result["table3"]["face"]["union"]["covered_bin_ids"] == [0, 1, 2]
    assert result["table3"]["face"]["detector_provenance"]["confidence_threshold"] == 0.9
    assert result["table3"]["face"]["detector_provenance"]["confidence_operator"] == ">"
    assert set(result["table3"]) == {"asd", "face", "head_pose"}


def test_face_presence_uses_raw_s3fd_frames_on_canonical_grid_not_asd_samples():
    faces = {camera: [[] for _ in range(50)] for camera in ("cam1", "cam2", "cam3")}
    faces["cam2"][26] = [{"frame": 26, "bbox": [0, 0, 1, 1], "conf": 0.91}]

    result = _face_presence(faces, 2.0)

    assert result == {
        "cam1": [False, False],
        "cam2": [False, True],
        "cam3": [False, False],
    }


def test_face_presence_rejects_threshold_equality_because_s3fd_uses_strict_comparison():
    faces = {camera: [[]] for camera in ("cam1", "cam2", "cam3")}
    faces["cam1"][0] = [{"frame": 0, "bbox": [0, 0, 1, 1], "conf": 0.9}]

    with pytest.raises(ValueError, match="does not satisfy >0.9"):
        _face_presence(faces, 1.0)


def test_session_face_producer_lists_out_of_session_resample_tail_instead_of_silent_drop():
    faces = {camera: [[] for _ in range(27)] for camera in ("cam1", "cam2", "cam3")}
    faces["cam1"][25] = [{"frame": 25, "bbox": [0, 0, 1, 1], "conf": 0.91}]
    exclusions = {camera: [] for camera in faces}

    result = _face_presence(
        faces, 1.0, excluded_out_of_session_detection_frame_ids=exclusions
    )

    assert result["cam1"] == [False]
    assert exclusions == {"cam1": [25], "cam2": [], "cam3": []}


def test_captured_light_asd_source_uses_verified_s3fd_threshold_contract():
    root = Path(__file__).resolve().parents[1]
    runner_path = root / "third_party/Light-ASD/Columbia_test.py"
    detector_path = root / "third_party/Light-ASD/model/faceDetector/s3fd/__init__.py"
    if not runner_path.is_file() or not detector_path.is_file():
        pytest.skip(
            "optional Light-ASD checkout is absent; fetch the pinned revision from "
            "third_party/manifest.yaml to inspect its captured S3FD contract"
        )

    runner = runner_path.read_text(encoding="utf-8")
    detector = detector_path.read_text(encoding="utf-8")

    assert "detect_faces(imageNumpy, conf_th=0.9" in runner
    assert "while detections[0, i, j, 0] > conf_th" in detector


def test_speaker_link_uses_diarized_speakers_instead_of_time_bins():
    link = _metrics()["speaker_identity_link"]
    assert link["numerator"] == 1
    assert link["denominator"] == 2
    assert link["diarized_speaker_ids"] == ["speaker-a", "speaker-b"]


def test_head_pose_frame_timing_has_no_numeric_fps_fallback():
    head_pose = _head_pose()
    del head_pose["cam1"]["metadata"]
    with pytest.raises(ValueError, match="decoded fps"):
        compute_session_paper_metrics(
            session_manifest={"session_id": "session-new", "session_end_seconds": 3.2},
            asd_by_camera=_asd(), head_pose_by_camera=head_pose,
            best_angles=_best_angles(),
            identity_map={"session_id": "session-new", "speakers": []},
            diarized_transcript={"segments": []},
            focal_runs=_focal_runs(), run_id="run-synthetic",
            multimodal_windows=_windows(),
            faces_by_camera=_faces(), gaze_tracks=_gaze(),
            source_artifacts=_sources(), run_manifest_path="fixtures/run_manifest.json",
        )


def test_aggregate_producer_retains_session_counts_and_unweighted_trace():
    first = _metrics()
    second = _metrics("session-next")
    result = aggregate_paper_metrics([second, first], expected_session_count=2)

    selected = result["table3"]["asd"]["selected"]
    assert selected["aggregation_trace"] == ["session-new", "session-next"]
    assert selected["n"] == 2
    assert [(unit["numerator"], unit["denominator"]) for unit in selected["units"]] == [
        (2, 4), (2, 4)
    ]
    assert selected["mean"] == 0.5
    assert selected["sample_std"] == 0.0
    assert selected["cohort_denominator"] == 8
    assert result["m_only_count"]["total_count"] == 2
    assert result["tm_overlap"]["mean"] == 0.75
    assert result["quantity_artifact_map"]["tm_overlap"]["source_session_count"] == 2
    assert result["validation"]["status"] == "passed"


def test_stage19_stores_all_table3_absolute_gaps_with_exact_lineage():
    result = aggregate_paper_metrics(
        [_metrics("session-new"), _metrics("session-next")], expected_session_count=2
    )
    gaps = result["table3_absolute_percentage_point_gaps"]

    assert gaps["definition_id"] == "METRIC-T3-ABSOLUTE-PP-GAP-001"
    assert gaps["unit"] == "percentage_points"
    expected = {
        "asd": (25.0, 0.0, 25.0),
        "face": (25.0, 0.0, 25.0),
        "head_pose": (50.0, 0.0, 50.0),
    }
    comparisons = (
        "union_minus_best_cam", "selected_minus_best_cam", "union_minus_selected"
    )
    for signal, values in expected.items():
        for comparison, value in zip(comparisons, values):
            record = gaps["signals"][signal][comparison]
            quantity_id = f"table3.{signal}.gap.{comparison}"
            assert record["quantity_id"] == quantity_id
            assert record["status"] == "measured"
            assert record["value_percentage_points"] == value
            assert record["n"] == 2
            assert result["quantity_artifact_map"][quantity_id]["source_session_count"] == 2
            assert result["quantity_artifact_map"][quantity_id]["producer_stage"] == (
                "19_aggregate_paper_metrics"
            )
            assert result["quantity_artifact_map"][f"{quantity_id}[cohort]"][
                "source_session_count"
            ] == 2


def test_aggregate_fails_closed_and_retains_explicit_session_shortfall_report():
    with pytest.raises(MetricsValidationError) as captured:
        aggregate_paper_metrics([_metrics()], expected_session_count=2)
    report = captured.value.report
    assert report["validation"]["status"] == "failed"
    assert report["table3"]["asd"]["selected"]["contributing_session_count"] == 1
    assert report["table3"]["asd"]["selected"]["expected_session_count"] == 2
    assert report["harness_delivery_failure_funnel"]["status"] == "incomplete"
    gap = report["table3_absolute_percentage_point_gaps"]["signals"]["asd"][
        "union_minus_best_cam"
    ]
    assert gap["status"] == "unavailable"
    assert gap["value_percentage_points"] is None
    assert gap["unavailable_reason"]
    assert report["harness_delivery_failure_funnel"]["contributing_session_count"] == 1
    assert any(
        "harness_delivery_failure_funnel: computed from 1/2 sessions" in failure
        for failure in report["validation"]["failures"]
    )


def test_selected_equal_to_union_is_valid():
    metric = _metrics()
    for signal in ("asd", "face", "head_pose"):
        metric["table3"][signal]["selected"] = dict(metric["table3"][signal]["union"])
    result = aggregate_paper_metrics([metric], expected_session_count=1)
    assert result["validation"]["status"] == "passed"


def test_selected_exceeding_union_is_a_hard_validation_failure():
    metric = _metrics()
    metric["table3"]["asd"]["selected"]["numerator"] = 4
    metric["table3"]["asd"]["selected"]["value"] = 1.0
    with pytest.raises(MetricsValidationError, match="Selected exceeds Union"):
        aggregate_paper_metrics([metric], expected_session_count=1)


def test_session_producer_rejects_incomplete_upstream_lineage():
    sources = _sources()
    del sources["focal_runs"]
    with pytest.raises(ValueError, match="source artifact map mismatch"):
        compute_session_paper_metrics(
            session_manifest={"session_id": "session-new", "session_end_seconds": 3.2},
            asd_by_camera=_asd(), head_pose_by_camera=_head_pose(),
            best_angles=_best_angles(),
            identity_map={"session_id": "session-new", "speakers": []},
            diarized_transcript={"segments": []}, focal_runs=_focal_runs(),
            multimodal_windows=_windows(),
            faces_by_camera=_faces(), gaze_tracks=_gaze(),
            run_id="run-synthetic", source_artifacts=sources,
            run_manifest_path="fixtures/run_manifest.json",
        )


def test_retained_t_m_and_cross_modal_quantities_are_count_first():
    result = _metrics()
    assert result["tm_overlap"]["t_to_m"]["denominator"] == 1
    assert result["tm_overlap"]["m_to_t"]["denominator"] == 2
    assert result["m_only_count"]["count"] == 1
    assert result["m_only_cross_modal_evidence"]["numerator"] == 1
    assert result["m_only_cross_modal_evidence"]["denominator"] == 1
    assert result["aggregate_cross_modal_evidence"]["numerator"] == 1
    assert result["aggregate_cross_modal_evidence"]["denominator"] == 2
    assert "K" not in result


def test_harness_funnel_reaches_session_artifact_with_shared_denominator_and_partition():
    result = _metrics()
    funnel = result["harness_delivery_failure_funnel"]

    assert funnel["status"] == "measured"
    assert funnel["denominator"] == 3
    assert funnel["denominator_bin_ids"] == (0, 1, 2) or funnel["denominator_bin_ids"] == [0, 1, 2]
    assert funnel["signals"]["face"]["eligible_union"]["denominator"] == 3
    assert funnel["signals"]["asd"]["eligible_union"]["numerator"] == 3
    assert funnel["signals"]["asd"]["selected_camera_signal"]["numerator"] == 3
    assert funnel["signals"]["asd"]["strict_asd_gate_passed"]["numerator"] == 2
    assert funnel["signals"]["face"]["selected_camera_signal"]["numerator"] == 3
    assert funnel["signals"]["face"]["strict_asd_gate_passed"]["numerator"] == 2
    assert funnel["withholding_reason_counts"]["asd_score_not_strictly_positive"] == 1
    assert len(funnel["delivered_bin_ids"]) == 2
    assert (
        len(funnel["delivered_bin_ids"])
        + sum(funnel["withholding_reason_counts"].values())
        == funnel["denominator"]
    )
    assert "harness_delivery_failure_funnel" in result["quantity_artifact_map"]


def test_every_new_session_metric_reaches_artifact_and_quantity_lineage():
    result = _metrics()
    expected = {
        "evidence_distribution", "attention_distribution", "example_silence",
        "harness_delivery_failure_funnel", "provenance_integrity",
    }
    face_quantities = {"table3.face.best_cam", "table3.face.union", "table3.face.selected"}

    assert expected <= result.keys()
    assert expected | face_quantities <= result["quantity_artifact_map"].keys()
    assert {"best_cam", "union", "selected"} <= result["table3"]["face"].keys()
    assert result["evidence_distribution"]["status"] == "measured"
    assert result["attention_distribution"]["status"] == "unavailable"
    assert result["attention_distribution"]["missing_unit_ids"]
    assert result["example_silence"]["status"] == "unavailable"
    assert result["example_silence"]["missing_unit_ids"]
    audit = result["provenance_integrity"]
    assert audit["definition_id"] == "METRIC-T4-PROVENANCE-INTEGRITY-001"
    assert audit["integrity_status"] == "passed"
    assert audit["counts"]["moment_count"] == 3
    assert audit["counts"]["citation_count"] == 4
    assert audit["counts"]["invalid_or_incomplete_moment_count"] == 0
    assert f"provenance_integrity[{result['session_id']}]" in result["quantity_artifact_map"]


def test_every_new_cohort_metric_reaches_artifact_and_quantity_lineage():
    result = aggregate_paper_metrics(
        [_metrics("session-new"), _metrics("session-next")], expected_session_count=2
    )
    expected = {
        "moment_counts",
        "category_diversity",
        "directional_overlap",
        "camera_selection_distribution",
        "transcript_context_coverage",
        "scene_context_coverage",
        "attention_context_coverage",
        "wilcoxon_signed_rank",
        "session_count",
        "scenario_distribution",
        "session_durations",
        "participant_counts",
        "table3_ratio",
        "harness_delivery_failure_funnel",
        "provenance_integrity",
    }
    face_quantities = {"table3.face.best_cam", "table3.face.union", "table3.face.selected"}
    gap_quantities = {
        f"table3.{signal}.gap.{comparison}"
        for signal in ("asd", "face", "head_pose")
        for comparison in (
            "union_minus_best_cam", "selected_minus_best_cam", "union_minus_selected"
        )
    }

    assert expected <= result.keys()
    assert expected | face_quantities | gap_quantities <= result["quantity_artifact_map"].keys()
    assert "table3_absolute_percentage_point_gaps" in result
    assert {"best_cam", "union", "selected"} <= result["table3"]["face"].keys()
    assert all(
        result["quantity_artifact_map"][quantity_id]["source_session_count"] == 2
        for quantity_id in expected | face_quantities | gap_quantities
    )
    assert result["participant_counts"]["status"] == "unavailable"
    audit = result["provenance_integrity"]
    assert audit["status"] == "measured"
    assert audit["counts"]["moment_count"] == 6
    assert audit["counts"]["citation_count"] == 8
    assert audit["counts"]["invalid_or_incomplete_moment_count"] == 0
    assert "provenance_integrity[cohort]" in result["quantity_artifact_map"]


def test_aggregate_fails_closed_when_session_provenance_quantity_is_missing():
    first = _metrics("session-new")
    second = _metrics("session-next")
    del second["provenance_integrity"]

    with pytest.raises(MetricsValidationError) as captured:
        aggregate_paper_metrics([first, second], expected_session_count=2)

    audit = captured.value.report["provenance_integrity"]
    assert audit["status"] == "incomplete"
    assert audit["contributing_session_count"] == 1
    assert audit["noncontributing_session_ids"] == ["session-next"]
    assert any(
        "provenance_integrity: computed from 1/2 sessions" in failure
        for failure in captured.value.report["validation"]["failures"]
    )


def test_stage19_cli_runs_two_sessions_and_writes_fail_closed_artifact(tmp_path):
    first_id = "synthetic-session"
    second_id = "synthetic-session-copy"
    first_path = tmp_path / first_id / "metrics" / "paper_metrics.json"
    second_path = tmp_path / second_id / "metrics" / "paper_metrics.json"
    output = tmp_path / "two_session_cohort" / "paper_metrics.json"
    for path, metric in (
        (first_path, _metrics(first_id)),
        (second_path, _metrics(second_id)),
    ):
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(metric), encoding="utf-8")
    command = [
        sys.executable,
        "scripts/analytics/aggregate_paper_metrics.py",
        "--input", str(first_path),
        "--input", str(second_path),
        "--expected-session-count", "2",
        "--expected-session-id", first_id,
        "--expected-session-id", second_id,
        "--output", str(output),
    ]

    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["producer"] == "aggregate_paper_metrics"
    assert report["artifact_session_count"] == 2
    assert report["validation"]["status"] == "passed"
    assert report["provenance_integrity"]["counts"]["moment_count"] == 6
    assert report["provenance_integrity"]["counts"]["citation_count"] == 8
    assert report["quantity_artifact_map"]["provenance_integrity"][
        "source_session_count"
    ] == 2
    persisted_gap = report["table3_absolute_percentage_point_gaps"]["signals"]["head_pose"][
        "union_minus_best_cam"
    ]
    assert persisted_gap["value_percentage_points"] == 50.0
    assert report["quantity_artifact_map"][
        "table3.head_pose.gap.union_minus_best_cam[cohort]"
    ]["source_session_count"] == 2

    incomplete = _metrics(second_id)
    del incomplete["provenance_integrity"]
    second_path.write_text(json.dumps(incomplete), encoding="utf-8")
    failed_output = tmp_path / "missing_quantity" / "paper_metrics.json"
    failed_command = [
        *command[:-1], str(failed_output),
    ]
    failed = subprocess.run(failed_command, cwd=ROOT, capture_output=True, text=True)

    assert failed.returncode != 0
    failed_report = json.loads(failed_output.read_text(encoding="utf-8"))
    assert failed_report["validation"]["status"] == "failed"
    assert failed_report["provenance_integrity"]["contributing_session_count"] == 1
    assert failed_report["provenance_integrity"]["noncontributing_session_ids"] == [
        second_id
    ]


def test_provenance_quantity_survives_exact_run_manifest_lineage_check(tmp_path):
    session_id = "session-lineage"
    session_artifact = tmp_path / "session_metrics.json"
    cohort_artifact = tmp_path / "cohort_metrics.json"
    session_artifact.write_text(json.dumps(_metrics(session_id)), encoding="utf-8")
    cohort_artifact.write_text(
        json.dumps(aggregate_paper_metrics([_metrics(session_id)], expected_session_count=1)),
        encoding="utf-8",
    )
    manifest = RunManifest.create(
        tmp_path / "run" / "run_manifest.json", tmp_path,
        run_id="lineage-test", alignment_tolerance_seconds=0.05,
        project={}, environment={}, third_party={"components": []},
    )
    manifest.register_artifact(
        session_artifact, session_id=session_id, producer_stage="18_paper_metrics"
    )
    manifest.register_artifact(
        cohort_artifact, session_id="cohort", producer_stage="19_aggregate_paper_metrics"
    )
    session_quantity = f"provenance_integrity[{session_id}]"
    cohort_quantity = "provenance_integrity[cohort]"
    gap_quantity = "table3.asd.gap.union_minus_best_cam[cohort]"

    manifest.set_reported_quantities({
        session_quantity: [session_artifact], cohort_quantity: [cohort_artifact],
        gap_quantity: [cohort_artifact],
    })

    assert manifest.document["reported_quantities"][session_quantity] == [
        "session_metrics.json"
    ]
    assert manifest.document["reported_quantities"][cohort_quantity] == [
        "cohort_metrics.json"
    ]
    assert manifest.document["reported_quantities"][gap_quantity] == [
        "cohort_metrics.json"
    ]


def test_pipeline_declares_stage19_gap_for_reported_quantity_lineage(tmp_path):
    quantity = "table3.face.gap.union_minus_selected[cohort]"

    mapping = _cohort_quantity_lineage(tmp_path / "paper_metrics.json")

    assert mapping[quantity] == [tmp_path / "paper_metrics.json"]
