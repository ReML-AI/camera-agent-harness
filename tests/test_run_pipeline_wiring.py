from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import threading
import time
from datetime import datetime

import pytest

from scripts import run_pipeline as pipeline
from scripts.analytics.compute_paper_metrics import COHORT_QUANTITY_IDS, SESSION_QUANTITY_IDS
from scripts.run_pipeline import COHORT_METRICS_STAGE, STAGES
from scripts.run_manifest import RunManifest


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def test_master_graph_wires_producers_in_dependency_order():
    names = [stage[0] for stage in STAGES]
    assert names.index("2_person_tracking") < names.index("2_cross_camera_identity")
    assert names.index("4_asd") < names.index("4_asd_artifact")
    assert names.index("4_asd_artifact") < names.index("8_speaker_link_multi")
    assert names.index("5_clip_scenes") < names.index("7_clip_urgency_scoring")
    assert names.index("7_clip_urgency_scoring") < names.index("7_flag_production")
    assert names.index("7_flag_production") < names.index("13_multimodal_context")
    assert names.index("14_moment_detection") < names.index("18_paper_metrics")
    assert COHORT_METRICS_STAGE == "19_aggregate_paper_metrics"
    commands = {
        name: template for name, _gpu, template in STAGES if isinstance(template, list)
    }
    assert "scripts/reid/match_cameras.py" in commands["2_cross_camera_identity"]
    assert "scripts/focal/pipeline_stages.py" in commands["7_flag_production"]
    assert "scripts/focal/pipeline_stages.py" in commands["14_moment_detection"]
    assert "scripts/analytics/compute_paper_metrics.py" in commands["18_paper_metrics"]
    assert all("scripts/analytics/detect_moments_llm.py" not in command for command in commands.values())

    stage18_inputs = pipeline._stage_inputs("synthetic-session", "18_paper_metrics", object())
    assert sum(path.name == "faces.pckl" for path in stage18_inputs) == 3
    assert {
        path.parent.parent.name for path in stage18_inputs if path.name == "faces.pckl"
    } == {"asd_cam1", "asd_cam2", "asd_cam3"}
    assert any(path.name == "gaze_tracks.json" for path in stage18_inputs)
    stage4_outputs = pipeline._stage_outputs("synthetic-session", "4_asd")
    assert sum(path.name == "faces.pckl" for path in stage4_outputs) == 3


@pytest.mark.parametrize(
    "arguments",
    [
        [
            "scripts/reid/match_cameras.py",
            "--input", "cam1={missing}/cam1.json",
            "--input", "cam2={missing}/cam2.json",
            "--input", "cam3={missing}/cam3.json",
            "--output", "{output}",
        ],
        [
            "scripts/focal/pipeline_stages.py", "assemble-asd",
            "--input", "cam1={missing}/asd1",
            "--input", "cam2={missing}/asd2",
            "--input", "cam3={missing}/asd3",
            "--fps", "cam1=25", "--fps", "cam2=25", "--fps", "cam3=25",
            "--output", "{output}",
        ],
        [
            "scripts/focal/pipeline_stages.py", "score-clip",
            "--session-id", "synthetic-session",
            "--session-manifest", "{missing}/session.json",
            "--video", "cam1={missing}/cam1.mp4",
            "--video", "cam2={missing}/cam2.mp4",
            "--video", "cam3={missing}/cam3.mp4",
            "--model-path", "{missing}/clip-model",
            "--output", "{output}",
        ],
        [
            "scripts/focal/pipeline_stages.py", "produce-flags",
            "--session-id", "synthetic-session",
            "--transcript", "{missing}/transcript.json",
            "--clip-records", "{missing}/clip.json",
            "--monitor-vitals", "{missing}/vitals.json",
            "--monitor-config", "{missing}/monitor.json",
            "--output-dir", "{output_dir}",
        ],
        [
            "scripts/analytics/assemble_multimodal_windows.py",
            "--session-id", "synthetic-session",
            "--session-manifest", "{missing}/session.json",
            "--transcript", "{missing}/transcript.json",
            "--speaker-dynamics", "{missing}/dynamics.json",
            "--visual-scene", "{missing}/scene.json",
            "--attention", "{missing}/attention.json",
            "--attention-events", "{missing}/events.json",
            "--fused-flags", "{missing}/flags.json",
            "--output", "{output}",
        ],
        [
            "scripts/focal/pipeline_stages.py", "run-focal",
            "--session-id", "synthetic-session",
            "--transcript", "{missing}/transcript.json",
            "--windows", "{missing}/windows.json",
            "--runtime-config", "{missing}/runtime.json",
            "--base-url", "http://127.0.0.1:1/v1", "--api-key", "synthetic",
            "--output", "{output}",
        ],
        [
            "scripts/analytics/compute_paper_metrics.py",
            "--session-id", "synthetic-session",
            "--run-manifest", "{missing}/run.json",
            "--output", "{output}",
        ],
        [
            "scripts/analytics/aggregate_paper_metrics.py",
            "--input", "{missing}/session-metrics.json",
            "--expected-session-count", "1",
            "--expected-session-id", "synthetic-session",
            "--output", "{output}",
        ],
    ],
    ids=(
        "cross-camera", "asd-assembly", "clip-urgency", "flags", "context", "focal",
        "paper-metrics",
        "aggregate-paper-metrics",
    ),
)
def test_each_newly_wired_cli_fails_closed_on_missing_upstream(
    tmp_path: Path, arguments: list[str]
):
    missing = tmp_path / "missing"
    output = tmp_path / "must-not-exist.json"
    output_dir = tmp_path / "must-not-exist-dir"
    command = [
        PYTHON,
        *[
            value.format(missing=missing, output=output, output_dir=output_dir)
            for value in arguments
        ],
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode != 0
    assert not output.exists()
    assert not output_dir.exists()


class _ManifestDouble:
    run_id = "synthetic-run"

    def __init__(self):
        self.finished = None
        self.skipped = []

    def skip_stage(self, sid, stage_name, *, reason):
        self.skipped.append((sid, stage_name, reason))

    def finish_session(self, sid, *, passed):
        self.finished = (sid, passed)


def test_partial_or_unknown_stage_selection_cannot_report_pipeline_success(monkeypatch):
    monkeypatch.setattr(pipeline, "_register_session_sources", lambda manifest, sid: None)
    monkeypatch.setattr(pipeline, "run_stage", lambda *args, **kwargs: True)
    monkeypatch.setattr(pipeline, "_validate_session_alignment", lambda manifest, sid: True)

    partial = _ManifestDouble()
    assert pipeline.run_pipeline("synthetic", partial, gpu_only=True) is False
    assert partial.finished == ("synthetic", False)
    assert partial.skipped

    unknown = _ManifestDouble()
    assert pipeline.run_pipeline(
        "synthetic", unknown, skip_stages={"not-a-real-stage"}
    ) is False
    assert unknown.finished == ("synthetic", False)


def test_metric_artifacts_reach_run_manifest_reported_quantity_lineage(tmp_path):
    session_lineage = pipeline._quantity_lineage(("session-a",))
    cohort_path = tmp_path / "paper_metrics.json"
    cohort_lineage = pipeline._cohort_quantity_lineage(cohort_path)

    assert all(
        session_lineage[f"{quantity_id}[session-a]"]
        == [pipeline.metrics_dir("session-a") / "paper_metrics.json"]
        for quantity_id in SESSION_QUANTITY_IDS
    )
    assert all(
        cohort_lineage[f"{quantity_id}[cohort]"] == [cohort_path]
        for quantity_id in COHORT_QUANTITY_IDS
    )


def test_per_camera_commands_overlap_but_manifest_writes_stay_on_parent(
    tmp_path, monkeypatch
):
    manifest = RunManifest.create(
        tmp_path / "run_manifest.json",
        tmp_path,
        run_id="parallel-test",
        alignment_tolerance_seconds=0.05,
        project={},
        environment={},
        third_party={},
    )
    outputs = [tmp_path / f"cam{index}.json" for index in range(1, 4)]
    commands = [["fake-camera", str(path)] for path in outputs]
    monkeypatch.setattr(pipeline, "_commands_for_stage", lambda *_args: commands)
    monkeypatch.setattr(pipeline, "_stage_inputs", lambda *_args: [])
    monkeypatch.setattr(pipeline, "_stage_outputs", lambda *_args: outputs)
    monkeypatch.setattr(pipeline, "_allocated_cpu_count", lambda: 36)

    barrier = threading.Barrier(3)
    worker_threads = set()

    def fake_run(command, **_kwargs):
        worker_threads.add(threading.get_ident())
        barrier.wait(timeout=2)
        time.sleep(0.02)
        Path(command[1]).write_text("{}\n", encoding="utf-8")
        return 0

    monkeypatch.setattr(pipeline, "_run_command", fake_run)
    parent_thread = threading.get_ident()
    manifest_save = manifest.save
    save_threads = []

    def recorded_save():
        save_threads.append(threading.get_ident())
        manifest_save()

    monkeypatch.setattr(manifest, "save", recorded_save)

    assert pipeline.run_stage(
        "4_asd",
        True,
        "PER_CAMERA",
        "session-1",
        manifest,
        local=True,
        per_camera_workers=3,
    )

    stage = manifest.document["sessions"]["session-1"]["stages"]["4_asd"]
    assert stage["command_execution"] == {
        "mode": "parallel",
        "worker_count": 3,
        "allocated_cpu_count": 36,
        "cpu_threads_per_command": 12,
    }
    assert len(stage["command_results"]) == 3
    assert len(worker_threads) == 3
    assert save_threads and set(save_threads) == {parent_thread}
    assert len(stage["outputs"]) == 3
    started = datetime.fromisoformat(stage["started_at"])
    ended = datetime.fromisoformat(stage["ended_at"])
    command_starts = [
        datetime.fromisoformat(result["started_at"])
        for result in stage["command_results"]
    ]
    command_ends = [
        datetime.fromisoformat(result["ended_at"])
        for result in stage["command_results"]
    ]
    artifact_captures = [
        datetime.fromisoformat(manifest.document["artifacts"][path]["captured_at"])
        for path in stage["outputs"]
    ]
    assert started <= min(command_starts)
    assert max(command_ends) <= min(artifact_captures)
    assert max(artifact_captures) <= ended


def test_every_checked_in_run_input_exists_and_is_declared_by_a_stage():
    """A stage input that no stage produces must be hashed at run creation.

    Declaring it without registering it makes the stage fail its own staleness check;
    registering it without declaring it means editing the file leaves stale results
    looking fresh. The patient zones decide every attention label, so both matter.
    """
    from scripts.run_pipeline import CHECKED_IN_RUN_INPUTS, _stage_inputs

    from scripts.run_pipeline import STAGES

    declared = set()
    for stage_name, _needs_gpu, _template in STAGES:
        try:
            inputs = _stage_inputs("session_001", stage_name, None)
        except Exception:
            continue
        declared.update(Path(item).resolve() for item in inputs)

    for path in CHECKED_IN_RUN_INPUTS:
        assert path.is_file(), f"checked-in run input is missing: {path}"
        assert path.resolve() in declared, f"registered but no stage declares it: {path}"


def test_stage_8_does_not_declare_an_artifact_it_never_reads():
    """Stage 8 links speakers from ASD scores; it never opens the cross-camera artifact.

    Declaring global_visual_identities.json as an input asserted a dependency that does
    not exist, implying changes to it could affect identity_map or best_angles.
    """
    from scripts.run_pipeline import _stage_inputs

    declared = {Path(item).name for item in _stage_inputs("session_001", "8_speaker_link_multi", None)}

    assert "global_visual_identities.json" not in declared
    assert {"diarized_transcript_full.json", "asd_tracks.json"} <= declared
