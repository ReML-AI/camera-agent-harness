import json
import os
from pathlib import Path
import subprocess

from scripts.run_pipeline import STAGES


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_all_sessions.sbatch"


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        ["/bin/bash", str(SCRIPT), *args],
        cwd=ROOT,
        env=merged_env,
        text=True,
        capture_output=True,
    )


def test_batch_script_has_valid_shell_syntax_and_exact_model_contract():
    syntax = subprocess.run(["bash", "-n", str(SCRIPT)], text=True, capture_output=True)
    assert syntax.returncode == 0, syntax.stderr

    source = SCRIPT.read_text(encoding="utf-8")
    required_fragments = (
        "export HF_HUB_OFFLINE=1",
        "export TRANSFORMERS_OFFLINE=1",
        "--alignment-tolerance-seconds 0.1",
        "--monitor-config configs/monitor_ocr_1920x1080.json",
        "--monitor-sample-rate 1.0",
        "--per-camera-workers 3",
        '--asr-model-path "$REPO/models/faster-whisper-large-v2"',
        "--alignment-model-name WAV2VEC2_ASR_BASE_960H",
        '--alignment-model-path "$TORCH_HOME/hub/checkpoints/wav2vec2_fairseq_base_ls960_asr_ls960.pth"',
        '--alignment-cache-path "$TORCH_HOME"',
        "--diarization-model-name pyannote/speaker-diarization-3.1",
        '--diarization-cache-path "$HF_HUB_CACHE"',
        "--head-pose-repository-path third_party/6DRepNet360",
        '--focal-runtime-config "$REPO/configs/focal_runtime_qwen2_5_7b_ollama_q4km.json"',
        "--query-gpu=timestamp,index,name,memory.used,memory.total,utilization.gpu,utilization.memory",
    )
    for fragment in required_fragments:
        assert fragment in source


def test_batch_resume_stage_allowlist_matches_the_master_graph():
    source = SCRIPT.read_text(encoding="utf-8")
    line = next(item for item in source.splitlines() if item.startswith("VALID_STAGES="))
    declared = line.split("=", 1)[1].strip().strip('"').split()
    assert declared == [stage[0] for stage in STAGES]


def test_submit_creates_bounded_array_and_afterany_summary(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = tmp_path / "calls"
    state = tmp_path / "state"
    fake_sbatch = fake_bin / "sbatch"
    fake_sbatch.write_text(
        "#!/bin/bash\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_SBATCH_CALLS\"\n"
        "if [ ! -e \"$FAKE_SBATCH_STATE\" ]; then\n"
        "  : > \"$FAKE_SBATCH_STATE\"\n"
        "  echo '41001;cluster'\n"
        "else\n"
        "  echo '41002;cluster'\n"
        "fi\n",
        encoding="utf-8",
    )
    fake_sbatch.chmod(0o755)

    result = _run(
        "submit",
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "FAKE_SBATCH_CALLS": str(calls),
            "FAKE_SBATCH_STATE": str(state),
            "SESSIONS": "session_003,session_008",
            "MAX_CONCURRENT": "2",
            "FROM_STAGE": "14_moment_detection",
            "BATCH_ID": "batch-resume",
        },
    )

    assert result.returncode == 0, result.stderr
    submitted = calls.read_text(encoding="utf-8").splitlines()
    assert len(submitted) == 2
    assert "--array=3,8%2" in submitted[0]
    assert "--gres=gpu:1" in submitted[0]
    assert "--cpus-per-task=12" in submitted[0]
    assert "BATCH_ID=batch-resume,FROM_STAGE=14_moment_detection" in submitted[0]
    assert "--dependency=afterany:41001" in submitted[1]
    assert "BATCH_ID=batch-resume,SELECTED_TASKS=3:8,ARRAY_JOB_ID=41001" in submitted[1]
    assert "Batch ID: batch-resume" in result.stdout


def test_submit_rejects_unknown_session_before_calling_sbatch(tmp_path):
    result = _run(
        "submit",
        env={
            "PATH": str(tmp_path),
            "SESSIONS": "session_010",
        },
    )

    assert result.returncode == 2
    assert "unknown session 'session_010'" in result.stderr


def test_summary_reports_failed_stage_and_exit_status(tmp_path):
    batch_id = "batch-test"
    failed_root = tmp_path / "data" / "runs" / batch_id / "session_008"
    failed_root.mkdir(parents=True)
    (failed_root / "array_result.tsv").write_text(
        "session_008\t7\t41001\t41001_8\t14_moment_detection\t14_moment_detection\n",
        encoding="utf-8",
    )
    (failed_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "sessions": {
                    "session_008": {
                        "status": "failed",
                        "stages": {
                            "13_multimodal_context": {"status": "passed", "exit_status": 0},
                            "14_moment_detection": {"status": "failed", "exit_status": 7},
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = _run(
        "summarize",
        env={
            "CLINICAL_SIM_REPO": str(tmp_path),
            "BATCH_ID": batch_id,
            "SELECTED_TASKS": "8",
            "ARRAY_JOB_ID": "41001",
        },
    )

    assert result.returncode == 1
    assert "session_008  FAILED" in result.stdout
    failed_line = next(
        line for line in result.stdout.splitlines() if line.startswith("session_008")
    )
    assert "14_moment_detection" in failed_line
    assert failed_line.rstrip().endswith("7")
    assert "session_001  NOT_SUBMITTED" in result.stdout


def test_batch_summary_runs_the_cohort_aggregation():
    """The batch runs each session as its own array task, so run_pipeline never sees
    --session-id all and would never invoke the cohort stage. Without this, a nine-session
    batch finishes green having produced no cohort metrics -- and every "mean across nine
    sessions" figure in the paper comes from exactly that stage.
    """
    script = Path("scripts/run_all_sessions.sbatch").read_text(encoding="utf-8")

    assert "aggregate_paper_metrics.py" in script
    assert "--expected-session-count" in script
    assert "--expected-session-id" in script


def test_cohort_aggregation_is_refused_when_a_session_failed():
    """A partial cohort would silently shrink the denominator behind study-wide figures."""
    script = Path("scripts/run_all_sessions.sbatch").read_text(encoding="utf-8")

    marker = script.index("Cohort aggregation skipped: not every session passed")
    guard = script.rindex("if failed:", 0, marker)
    assert "aggregate_paper_metrics.py" not in script[guard:marker]
