import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.core.errors import AlignmentDriftError, StaleArtifactError, TimingProbeError
from scripts.core.records import CameraTimingProbe
from scripts.run_manifest import (
    RunManifest,
    build_alignment_records,
    probe_video,
    select_transcript_timestamps,
    validate_alignment_records,
)
from scripts import run_pipeline


def _manifest(tmp_path: Path) -> RunManifest:
    return RunManifest.create(
        tmp_path / "run_manifest.json",
        tmp_path,
        run_id="run-current",
        alignment_tolerance_seconds=0.05,
        project={"measurement": "capture_at_run"},
        environment={"measurement": "capture_at_run"},
        third_party={"measurement": "capture_at_run"},
    )


def test_stale_artifact_guard_names_unlisted_and_changed_artifacts(tmp_path):
    manifest = _manifest(tmp_path)
    artifact = tmp_path / "raw" / "upstream.json"
    artifact.parent.mkdir()
    artifact.write_text('{"value": 1}\n', encoding="utf-8")

    with pytest.raises(StaleArtifactError) as unlisted:
        manifest.verify_artifact(artifact)
    assert unlisted.value.artifact_path == "raw/upstream.json"

    registered = manifest.register_artifact(
        artifact, session_id="session-1", producer_stage="upstream"
    )
    artifact.write_text('{"value": 2}\n', encoding="utf-8")

    with pytest.raises(StaleArtifactError) as changed:
        manifest.verify_artifact(artifact)
    assert changed.value.artifact_path == "raw/upstream.json"
    assert changed.value.expected_sha256 == registered["sha256"]
    assert changed.value.actual_sha256 != registered["sha256"]


def test_stale_artifact_guard_rejects_another_run(tmp_path):
    manifest = _manifest(tmp_path)
    artifact = tmp_path / "upstream.json"
    artifact.write_text("{}\n", encoding="utf-8")
    record = manifest.register_artifact(
        artifact, session_id="session-1", producer_stage="upstream"
    )
    record["run_id"] = "run-older"
    manifest.document["artifacts"]["upstream.json"] = record

    with pytest.raises(StaleArtifactError, match="run-older") as caught:
        manifest.verify_artifact(artifact)
    assert caught.value.artifact_path == "upstream.json"


def test_stage_guard_fails_before_launching_consumer(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path)
    transcript = tmp_path / "raw" / "diarized_transcript_full.json"
    transcript.parent.mkdir()
    transcript.write_text('{"segments": []}\n', encoding="utf-8")
    manifest.register_artifact(
        transcript, session_id="session-1", producer_stage="1_diarization"
    )
    transcript.write_text('{"segments": [{"start": 0}]}\n', encoding="utf-8")
    monkeypatch.setattr(run_pipeline, "raw_dir", lambda _sid: tmp_path / "raw")
    monkeypatch.setattr(run_pipeline, "processed_dir", lambda _sid: tmp_path / "processed")
    launched = []
    monkeypatch.setattr(
        run_pipeline,
        "_run_command",
        lambda *args, **kwargs: launched.append(args) or 0,
    )

    passed = run_pipeline.run_stage(
        "10_speaker_dynamics",
        False,
        ["true"],
        "session-1",
        manifest,
        local=True,
    )

    assert not passed
    assert launched == []
    stage = manifest.document["sessions"]["session-1"]["stages"]["10_speaker_dynamics"]
    assert stage["status"] == "failed"
    assert "raw/diarized_transcript_full.json" in stage["failure_reason"]


def _camera_probe() -> CameraTimingProbe:
    return CameraTimingProbe(
        camera_id="cam1",
        video_path="/captured/session/cam1.mp4",
        fps_numerator=30000,
        fps_denominator=1001,
        duration_seconds=1200.0,
        decoded_frame_count=35964,
        fps_probe_field="stream.avg_frame_rate",
        duration_probe_field="stream.duration",
        captured_at="2026-08-13T12:00:00+00:00",
    )


def test_drift_check_spans_elapsed_time_and_catches_end_drift():
    probe = _camera_probe()
    samples = [("beginning", 1.0), ("middle", 600.0), ("end", 1199.0)]
    indexes = [30, 17982, 35934]
    decoded = {
        indexes[0]: 1.01,
        indexes[1]: 600.02,
        indexes[2]: 1199.20,
    }
    records = build_alignment_records(
        session_id="session-1",
        probe=probe,
        samples=samples,
        decoded_timestamps=decoded,
        tolerance_seconds=0.05,
    )

    assert [record.sample_position for record in records] == ["beginning", "middle", "end"]
    assert records[-1].transcript_timestamp_seconds == 1199.0
    assert records[-1].difference_seconds == pytest.approx(0.2)
    assert not records[-1].within_tolerance
    with pytest.raises(AlignmentDriftError) as caught:
        validate_alignment_records(records)
    assert caught.value.camera_id == "cam1"
    assert caught.value.frame_index == indexes[-1]


def test_short_transcript_cannot_stand_in_for_full_session_alignment():
    transcript = {
        "segments": [
            {"start": 0.5, "end": 1.0},
            {"start": 10.0, "end": 20.0},
        ]
    }
    with pytest.raises(TimingProbeError, match="full session"):
        select_transcript_timestamps(transcript, duration_seconds=1200.0)


def test_video_probe_has_no_fps_fallback(tmp_path):
    result = SimpleNamespace(
        returncode=0,
        stdout=json.dumps({"streams": [{"duration": "12.0", "nb_read_frames": "360"}], "format": {"duration": "12.0"}}),
        stderr="",
    )
    with pytest.raises(TimingProbeError, match="no measured avg_frame_rate"):
        probe_video(tmp_path / "cam1.mp4", "cam1", runner=lambda *args, **kwargs: result)


def test_missing_input_is_reported_as_missing_not_stale(tmp_path):
    """A never-produced input must not be reported as a stale leftover.

    Both are failures, but they need opposite fixes: stale means "delete it and re-run",
    missing means "its producer did not run". Conflating them misdirected a real
    debugging session.
    """
    from scripts.core.errors import MissingArtifactError

    manifest = _manifest(tmp_path)
    absent = tmp_path / "raw" / "never_produced.json"
    with pytest.raises(MissingArtifactError) as caught:
        manifest.verify_artifact(absent)
    assert caught.value.code == "MISSING_ARTIFACT"
    assert "did not run" in str(caught.value)


def _resume_args(**overrides):
    """A Namespace carrying every operator input, all None unless overridden."""
    from argparse import Namespace
    from scripts import run_pipeline

    fields = run_pipeline._operator_input_values(
        Namespace(**{name: None for name in _OPERATOR_INPUT_NAMES})
    )
    return Namespace(**{**{name: None for name in fields}, **overrides})


_OPERATOR_INPUT_NAMES = (
    "asr_model_path", "alignment_model_name", "alignment_model_path",
    "alignment_cache_path", "diarization_model_name", "diarization_cache_path",
    "head_pose_repository_path", "monitor_config", "monitor_sample_rate",
    "focal_runtime_config",
)


def test_resume_adds_an_operator_input_the_run_never_had(tmp_path):
    """The stage that needs it never ran, so recording it now rewrites no history."""
    from scripts import run_pipeline

    manifest = _manifest(tmp_path)
    manifest.document["operator_inputs"] = {"monitor_config": "/cfg/monitor.json"}

    run_pipeline._merge_resumed_operator_inputs(
        _resume_args(focal_runtime_config=Path("/cfg/focal.json")), manifest
    )

    assert manifest.document["operator_inputs"]["focal_runtime_config"] == "/cfg/focal.json"


def test_resume_refuses_to_change_a_recorded_operator_input(tmp_path):
    """Earlier stages already consumed it; changing it makes the run describe two configs."""
    from scripts.core.errors import RunManifestError
    from scripts import run_pipeline

    manifest = _manifest(tmp_path)
    manifest.document["operator_inputs"] = {"monitor_config": "/cfg/monitor.json"}

    with pytest.raises(RunManifestError, match="cannot change operator input"):
        run_pipeline._merge_resumed_operator_inputs(
            _resume_args(monitor_config=Path("/cfg/other.json")), manifest
        )


def test_resume_accepts_a_recorded_number_resupplied_unchanged(tmp_path):
    """Manifests store JSON, so a rate recorded as 1.0 must still equal a re-parsed 1.0.

    Comparing the raw types rejected a resume that supplied exactly the recorded value,
    which is what blocked the run that this guard was written to protect.
    """
    from scripts import run_pipeline

    manifest = _manifest(tmp_path)
    manifest.document["operator_inputs"] = {"monitor_sample_rate": 1.0}

    run_pipeline._merge_resumed_operator_inputs(_resume_args(monitor_sample_rate=1.0), manifest)

    assert manifest.document["operator_inputs"]["monitor_sample_rate"] == 1.0


def test_resume_registers_the_file_behind_a_newly_added_operator_input(tmp_path):
    """Adding the input is not enough: its file must be hashed or the stage refuses it.

    The registration list covered `*_path` and `monitor_config` only, so a config named
    `focal_runtime_config` was recorded as an input and then rejected by the stage that
    requires it as "not listed in the current run manifest".
    """
    from scripts import run_pipeline

    config = tmp_path / "focal_runtime.json"
    config.write_text('{"model": "qwen2.5:7b"}', encoding="utf-8")
    manifest = _manifest(tmp_path)

    run_pipeline._merge_resumed_operator_inputs(
        _resume_args(focal_runtime_config=config), manifest
    )

    registered = manifest.document["artifacts"]
    assert any(Path(key).name == "focal_runtime.json" for key in registered)


def test_resume_hashes_a_recorded_input_that_was_never_registered(tmp_path):
    """Repair the manifest state where an input is recorded but its file was never hashed.

    An earlier resume could record the input and skip registration, and every later attempt
    then failed the same stage with "not listed in the current run manifest" — the run could
    not be recovered, because the repair was gated on the input being newly added.
    """
    from scripts import run_pipeline

    config = tmp_path / "focal_runtime.json"
    config.write_text('{"model": "qwen2.5:7b"}', encoding="utf-8")
    manifest = _manifest(tmp_path)
    manifest.document["operator_inputs"] = {"focal_runtime_config": str(config)}

    run_pipeline._merge_resumed_operator_inputs(
        _resume_args(focal_runtime_config=config), manifest
    )

    assert manifest.is_registered(config)


def test_resume_does_not_rehash_an_already_registered_input(tmp_path):
    """Re-hashing on resume would bless a config edited between runs."""
    from scripts import run_pipeline

    config = tmp_path / "focal_runtime.json"
    config.write_text('{"model": "qwen2.5:7b"}', encoding="utf-8")
    manifest = _manifest(tmp_path)
    manifest.document["operator_inputs"] = {"focal_runtime_config": str(config)}
    run_pipeline._merge_resumed_operator_inputs(
        _resume_args(focal_runtime_config=config), manifest
    )
    original = dict(manifest.document["artifacts"][manifest._key(config)])

    config.write_text('{"model": "something-else"}', encoding="utf-8")
    run_pipeline._merge_resumed_operator_inputs(
        _resume_args(focal_runtime_config=config), manifest
    )

    assert manifest.document["artifacts"][manifest._key(config)]["sha256"] == original["sha256"]
