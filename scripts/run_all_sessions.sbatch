#!/bin/bash
# Submit and run the nine-session study as a bounded Slurm array.
#
# Submit all nine (default concurrency is one GPU job at a time):
#   bash scripts/run_all_sessions.sbatch submit
#
# Increase concurrency only when cluster capacity permits:
#   MAX_CONCURRENT=2 bash scripts/run_all_sessions.sbatch submit
#
# Resume one session using its existing per-session manifest. BATCH_ID is printed
# by the initial submission and is also the data/runs/<BATCH_ID> directory name:
#   BATCH_ID=batch-12345 SESSIONS=session_008 \
#     bash scripts/run_all_sessions.sbatch submit
#
# Resume from one failed stage (the named stage and all later stages are run;
# earlier passed stages remain recorded in the same manifest):
#   BATCH_ID=batch-12345 SESSIONS=session_008 FROM_STAGE=14_moment_detection \
#     bash scripts/run_all_sessions.sbatch submit
#
# SESSIONS is a comma-separated subset of session_001 through session_009.
# Every submission creates one Slurm log per selected session and an afterany
# summary job. The summary prints all nine sessions, including failures and their
# recorded stage exit status. The login-node command only submits jobs; pipeline
# work runs inside the Slurm allocations.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO="${CLINICAL_SIM_REPO:-$(cd "$SCRIPT_DIR/.." && pwd)}"
SCRIPT_PATH="$REPO/scripts/run_all_sessions.sbatch"
SLURM_PARTITION="${CLINICAL_SIM_SLURM_PARTITION:-}"
SLURM_NODELIST="${CLINICAL_SIM_SLURM_NODELIST:-}"
ALL_SESSIONS="session_001,session_002,session_003,session_004,session_005,session_006,session_007,session_008,session_009"
VALID_STAGES="1_diarization 2_person_tracking 2_cross_camera_identity 4_asd 4_asd_artifact 3_head_pose 5_clip_scenes 6_monitor_ocr 7_clip_urgency_scoring 7_flag_production 8_speaker_link_multi 9_gaze_classification 10_speaker_dynamics 11_gaze_events 12_interaction_analytics 13_multimodal_context 14_moment_detection 15_moment_context 16_moment_narratives 17_video_overlay 18_paper_metrics"

fail() {
    echo "ERROR: $*" >&2
    exit 2
}

session_for_task() {
    case "$1" in
        1) echo session_001 ;;
        2) echo session_002 ;;
        3) echo session_003 ;;
        4) echo session_004 ;;
        5) echo session_005 ;;
        6) echo session_006 ;;
        7) echo session_007 ;;
        8) echo session_008 ;;
        9) echo session_009 ;;
        *) fail "array task must be in 1..9 (got $1)" ;;
    esac
}

task_for_session() {
    case "$1" in
        session_001) echo 1 ;;
        session_002) echo 2 ;;
        session_003) echo 3 ;;
        session_004) echo 4 ;;
        session_005) echo 5 ;;
        session_006) echo 6 ;;
        session_007) echo 7 ;;
        session_008) echo 8 ;;
        session_009) echo 9 ;;
        *) fail "unknown session '$1'; expected session_001 through session_009" ;;
    esac
}

validate_stage() {
    local requested="$1"
    local candidate
    [ -z "$requested" ] && return 0
    for candidate in $VALID_STAGES; do
        [ "$candidate" = "$requested" ] && return 0
    done
    fail "unknown FROM_STAGE '$requested'"
}

submit_batch() {
    local requested_sessions="${SESSIONS:-$ALL_SESSIONS}"
    local max_concurrent="${MAX_CONCURRENT:-1}"
    local from_stage="${FROM_STAGE:-}"
    local requested_batch_id="${BATCH_ID:-}"
    local task_spec=""
    local selected_tasks=""
    local array_export="ALL"
    local sid task array_submission array_job_id batch_id summary_submission

    [[ "$max_concurrent" =~ ^[1-9][0-9]*$ ]] || fail "MAX_CONCURRENT must be a positive integer"
    validate_stage "$from_stage"
    if [ -n "$requested_batch_id" ]; then
        [[ "$requested_batch_id" =~ ^[A-Za-z0-9_.-]+$ ]] || \
            fail "BATCH_ID may contain only letters, digits, dot, underscore, and hyphen"
        array_export="$array_export,BATCH_ID=$requested_batch_id"
    fi
    [ -z "$from_stage" ] || array_export="$array_export,FROM_STAGE=$from_stage"

    IFS=',' read -r -a session_list <<< "$requested_sessions"
    [ "${#session_list[@]}" -gt 0 ] || fail "SESSIONS must not be empty"
    for sid in "${session_list[@]}"; do
        task=$(task_for_session "$sid")
        case ",$task_spec," in
            *,$task,*) fail "duplicate session '$sid'" ;;
        esac
        task_spec="${task_spec:+$task_spec,}$task"
        selected_tasks="${selected_tasks:+$selected_tasks:}$task"
    done

    # Every session gets the same allocation so thread counts stay comparable.
    # Optional: chain this submission behind a still-running job, so a rerun can be queued
    # now and start by itself. DEPENDENCY=afterany:237628_8
    local dep_args=()
    [ -n "${DEPENDENCY:-}" ] && dep_args=(--dependency="$DEPENDENCY")
    local cluster_args=()
    [ -n "$SLURM_PARTITION" ] && cluster_args+=(--partition="$SLURM_PARTITION")
    [ -n "$SLURM_NODELIST" ] && cluster_args+=(--nodelist="$SLURM_NODELIST")

    mkdir -p "$REPO/tmp"
    array_submission=$(sbatch --parsable \
        "${dep_args[@]}" \
        "${cluster_args[@]}" \
        --job-name=csr_sessions \
        --ntasks=1 \
        --cpus-per-task="${CPUS_PER_TASK:-12}" \
        --gres=gpu:1 \
        --time=12:00:00 \
        --array="${task_spec}%${max_concurrent}" \
        --output="$REPO/tmp/batch_%A_session_%a.log" \
        --export="$array_export" \
        "$SCRIPT_PATH" run) || fail "array submission failed"
    array_job_id="${array_submission%%;*}"
    [ -n "$array_job_id" ] || fail "sbatch returned no array job ID"
    batch_id="${requested_batch_id:-batch-$array_job_id}"

    summary_submission=$(sbatch --parsable \
        "${cluster_args[@]}" \
        --job-name=csr_summary \
        --ntasks=1 \
        --dependency="afterany:$array_job_id" \
        --output="$REPO/tmp/${batch_id}_summary_%j.log" \
        --export="ALL,BATCH_ID=$batch_id,SELECTED_TASKS=$selected_tasks,ARRAY_JOB_ID=$array_job_id" \
        "$SCRIPT_PATH" summarize) || fail "array $array_job_id was submitted, but summary submission failed"

    echo "Submitted array job: $array_job_id"
    echo "Submitted summary job: ${summary_submission%%;*} (afterany:$array_job_id)"
    echo "Batch ID: $batch_id"
    echo "Sessions: $requested_sessions"
    echo "Concurrency: $max_concurrent"
    echo "Manifests: $REPO/data/runs/$batch_id/<session>/run_manifest.json"
    echo "Session logs: $REPO/tmp/batch_${array_job_id}_session_<task>.log"
    echo "Summary log: $REPO/tmp/${batch_id}_summary_<job>.log"
}

run_session() {
    [ -n "${SLURM_ARRAY_TASK_ID:-}" ] || fail "run mode requires a Slurm array task"
    [ -n "${SLURM_ARRAY_JOB_ID:-}" ] || fail "SLURM_ARRAY_JOB_ID is not set"

    local sid batch_id manifest_dir manifest_path result_tmp result_path attempt_log
    local pipeline_exit failing_stage
    local -a resume_args=()
    sid=$(session_for_task "$SLURM_ARRAY_TASK_ID")
    batch_id="${BATCH_ID:-batch-$SLURM_ARRAY_JOB_ID}"
    validate_stage "${FROM_STAGE:-}"
    manifest_dir="$REPO/data/runs/$batch_id/$sid"
    manifest_path="$manifest_dir/run_manifest.json"
    result_path="$manifest_dir/array_result.tsv"
    result_tmp="$manifest_dir/.array_result.${SLURM_JOB_ID:-$$}.tmp"
    attempt_log="$manifest_dir/pipeline_${SLURM_JOB_ID:-$$}.log"
    mkdir -p "$manifest_dir" || fail "cannot create manifest directory $manifest_dir"
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$sid" "NOT_RECORDED" "$SLURM_ARRAY_JOB_ID" "${SLURM_JOB_ID:-UNKNOWN}" "${FROM_STAGE:-AUTO_RESUME}" "NOT_RECORDED" > "$result_tmp"
    mv "$result_tmp" "$result_path"

    cd "$REPO" || fail "cannot enter repository $REPO"
    # shellcheck disable=SC1091
    source .venv/bin/activate
    export PYTHONPATH="$REPO:${PYTHONPATH:-}"
    export OLLAMA_MODELS="${OLLAMA_MODELS:-$REPO/models/ollama}"
    export OLLAMA_CONTEXT_LENGTH=32768
    export TORCH_HOME="${TORCH_HOME:-$REPO/models/torch-cache}"
    export HF_HUB_CACHE="$REPO/models/hf-cache"
    export PYANNOTE_CACHE="$HF_HUB_CACHE"
    export HF_HUB_OFFLINE=1
    export TRANSFORMERS_OFFLINE=1
    export PATH="$REPO/.venv/bin:$PATH"

    local ffmpeg_dir ollama_bin
    ffmpeg_dir=$(python3 -c "import imageio_ffmpeg,os;print(os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe()))" 2>/dev/null || true)
    [ -n "$ffmpeg_dir" ] && export PATH="$ffmpeg_dir:$PATH"

    # This is the production wrapper and it ran concurrent sessions on the default port:
    # the second server fails to bind, dies, and its health check then succeeds against the
    # FIRST job's server, so a session silently runs its focal inference in another job's
    # process, with that job's context length, and loses the model when that job ends.
    # Isolate the per-job Ollama endpoint so concurrent jobs cannot share a server.
    ollama_bin="${OLLAMA_BIN:-$(command -v ollama || true)}"
    # Within an array the concurrently running tasks are distinguished by their task
    # index, so derive the port from it when present. Distinctness among the tasks
    # that actually run at the same time is the property that matters.
    if [ -n "${SLURM_ARRAY_TASK_ID:-}" ]; then
        ollama_port=$((11500 + SLURM_ARRAY_TASK_ID % 400))
    else
        ollama_port=$((11500 + ${SLURM_JOB_ID:-0} % 400))
    fi
    export OLLAMA_HOST="127.0.0.1:${ollama_port}"
    ollama_url="http://127.0.0.1:${ollama_port}"
    if [ ! -x "$ollama_bin" ]; then
        echo "ERROR: no ollama binary at $ollama_bin; the focal stage cannot run" >&2
        exit 1
    fi
    if curl -sf "${ollama_url}/api/tags" >/dev/null 2>&1; then
        echo "ERROR: port ${ollama_port} is already serving before this job started it" >&2
        exit 1
    fi
    "$ollama_bin" serve &>"/tmp/ollama_${SLURM_JOB_ID}.log" &
    ollama_pid=$!
    for _ in $(seq 1 30); do
        curl -sf "${ollama_url}/api/tags" >/dev/null 2>&1 && break
        sleep 1
    done
    if ! kill -0 "$ollama_pid" 2>/dev/null; then
        echo "ERROR: this job's ollama died; refusing to use another job's server" >&2
        exit 1
    fi
    if ! curl -sf "${ollama_url}/api/tags" >/dev/null 2>&1; then
        echo "ERROR: ollama did not become healthy on ${ollama_port}; refusing to run" >&2
        exit 1
    fi
    server_version=$(curl -fsS "${ollama_url}/api/version" | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])')
    expected_version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["backend_version"])' "$REPO/configs/focal_runtime_qwen2_5_7b_ollama_q4km.json")
    if [ "$server_version" != "$expected_version" ]; then
        echo "ERROR: ollama $server_version does not match focal runtime config $expected_version" >&2
        exit 1
    fi
    echo "Ollama ready on ${ollama_port} (server version $server_version)"
    export LLM_BASE_URL="${ollama_url}/v1"
    export LLM_API_KEY=ollama-local
    export LLM_MODEL=qwen2.5:7b

    if [ -n "${FROM_STAGE:-}" ]; then
        resume_args=(--from-stage "$FROM_STAGE")
    fi

    echo "================================================================"
    echo "RUN  batch=$batch_id  session=$sid  node=$(hostname)  gpu=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)"
    echo "commit=$(cat "$REPO/DEPLOYED_COMMIT" 2>/dev/null || echo UNKNOWN)"
    echo "manifest=$manifest_path"
    echo "from_stage=${FROM_STAGE:-AUTO_RESUME}"
    echo "================================================================"

    local resource_log resource_sampler_pid
    resource_log="$REPO/tmp/resources_${SLURM_JOB_ID}.csv"
    nvidia-smi \
        --query-gpu=timestamp,index,name,memory.used,memory.total,utilization.gpu,utilization.memory \
        --format=csv --loop=1 >"$resource_log" 2>&1 &
    resource_sampler_pid=$!
    trap "kill $resource_sampler_pid 2>/dev/null || true" EXIT
    echo "resource_log=$resource_log"

    set +e
    python3 -u scripts/run_pipeline.py --session-id "$sid" --local \
        --per-camera-workers 3 \
        --run-manifest "$manifest_path" \
        --alignment-tolerance-seconds 0.1 \
        --monitor-config configs/monitor_ocr_1920x1080.json \
        --monitor-sample-rate 1.0 \
        --asr-model-path "$REPO/models/faster-whisper-large-v2" \
        --alignment-model-name WAV2VEC2_ASR_BASE_960H \
        --alignment-model-path "$TORCH_HOME/hub/checkpoints/wav2vec2_fairseq_base_ls960_asr_ls960.pth" \
        --alignment-cache-path "$TORCH_HOME" \
        --diarization-model-name pyannote/speaker-diarization-3.1 \
        --diarization-cache-path "$HF_HUB_CACHE" \
        --head-pose-repository-path third_party/6DRepNet360 \
        --focal-runtime-config "$REPO/configs/focal_runtime_qwen2_5_7b_ollama_q4km.json" \
        "${resume_args[@]}" 2>&1 | tee "$attempt_log"
    pipeline_exit=${PIPESTATUS[0]}
    kill "$resource_sampler_pid" 2>/dev/null || true
    wait "$resource_sampler_pid" 2>/dev/null || true
    set -e

    failing_stage=$(sed -n \
        -e 's/^  FAIL source capture:.*/source_capture/p' \
        -e 's/^  FAIL \([^ :]*\).*/\1/p' \
        "$attempt_log" | tail -1)
    [ -n "$failing_stage" ] || failing_stage="pipeline_startup"
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$sid" "$pipeline_exit" "$SLURM_ARRAY_JOB_ID" "${SLURM_JOB_ID:-UNKNOWN}" "${FROM_STAGE:-AUTO_RESUME}" "$failing_stage" > "$result_tmp"
    mv "$result_tmp" "$result_path"
    echo "PIPELINE_EXIT=$pipeline_exit"
    echo "Done at $(date)"
    exit "$pipeline_exit"
}

summarize_batch() {
    [ -n "${BATCH_ID:-}" ] || fail "summarize mode requires BATCH_ID"
    python3 - "$REPO" "$BATCH_ID" "${SELECTED_TASKS:-}" "${ARRAY_JOB_ID:-}" <<'PY'
import json
from pathlib import Path
import subprocess
import sys

repo = Path(sys.argv[1])
batch_id = sys.argv[2]
selected = {int(value) for value in sys.argv[3].split(":") if value}
array_job_id = sys.argv[4]
batch_root = repo / "data" / "runs" / batch_id
failed = False

print(f"Batch summary: {batch_id}")
print(f"{'SESSION':<12} {'STATUS':<15} {'FAILING_STAGE':<28} {'EXIT_STATUS'}")
print(f"{'-' * 12} {'-' * 15} {'-' * 28} {'-' * 11}")
for task in range(1, 10):
    sid = f"session_{task:03d}"
    session_root = batch_root / sid
    manifest_path = session_root / "run_manifest.json"
    result_path = session_root / "array_result.tsv"
    wrapper_exit = None
    wrapper_stage = None
    result_array_job_id = None
    if result_path.exists():
        fields = result_path.read_text(encoding="utf-8").strip().split("\t")
        if len(fields) >= 2:
            wrapper_exit = fields[1]
        if len(fields) >= 3:
            result_array_job_id = fields[2]
        if len(fields) >= 6:
            wrapper_stage = fields[5]

    if task in selected and array_job_id and result_array_job_id != array_job_id:
        status, stage, exit_status = "FAILED", "array_task_not_started", "NOT_RECORDED"
        failed = True
        print(f"{sid:<12} {status:<15} {stage:<28} {exit_status}")
        continue

    if not manifest_path.exists():
        if task in selected:
            status, stage, exit_status = "FAILED", "manifest_not_written", wrapper_exit or "NOT_RECORDED"
            failed = True
        else:
            status, stage, exit_status = "NOT_SUBMITTED", "-", "-"
    else:
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
            session = document.get("sessions", {}).get(sid, {})
            stages = session.get("stages", {})
            failing = [
                (name, record)
                for name, record in stages.items()
                if record.get("status") in {"failed", "running"}
            ]
            if session.get("status") == "passed" and wrapper_exit in {None, "0"}:
                status, stage, exit_status = "PASSED", "-", "0"
            else:
                status = "FAILED"
                if failing:
                    stage, record = failing[-1]
                    recorded_exit = record.get("exit_status")
                    exit_status = str(recorded_exit) if recorded_exit is not None else (wrapper_exit or "NOT_RECORDED")
                else:
                    stage = wrapper_stage or ("source_capture" if session.get("status") == "failed" else "pipeline_startup")
                    exit_status = wrapper_exit or "NOT_RECORDED"
                failed = True
        except (OSError, ValueError, TypeError) as error:
            status, stage, exit_status = "FAILED", "invalid_manifest", wrapper_exit or "NOT_RECORDED"
            failed = True
            print(f"WARNING: {manifest_path}: {error}", file=sys.stderr)

    print(f"{sid:<12} {status:<15} {stage:<28} {exit_status}")

print(f"Manifests: {batch_root}/<session>/run_manifest.json")

# Every "mean across N sessions" number the paper reports comes from the cohort stage.
# Running each session as its own array task means run_pipeline never sees
# --session-id all, so nothing else in this batch path would invoke it: the batch
# would finish green having produced no cohort metrics at all.
#
# Gated on every session passing. The aggregator fails closed on a missing session by
# design, and aggregating a partial cohort would quietly shrink the denominator behind
# figures that are read as covering the whole study.
if failed:
    print("Cohort aggregation skipped: not every session passed.")
    raise SystemExit(1)

inputs = []
for task in range(1, 10):
    sid = f"session_{task:03d}"
    metrics = batch_root / sid / "paper_metrics.json"
    if not metrics.is_file():
        metrics = repo / "data" / "sessions" / sid / "metrics" / "paper_metrics.json"
    if not metrics.is_file():
        print(f"Cohort aggregation skipped: {sid} has no paper_metrics.json")
        raise SystemExit(1)
    inputs.append((sid, metrics))

cohort_output = batch_root / "paper_metrics.json"
command = [
    sys.executable,
    str(repo / "scripts" / "analytics" / "aggregate_paper_metrics.py"),
    "--output", str(cohort_output),
    "--expected-session-count", str(len(inputs)),
]
for sid, metrics in inputs:
    command.extend(["--input", str(metrics), "--expected-session-id", sid])

print(f"Aggregating {len(inputs)} sessions -> {cohort_output}")
completed = subprocess.run(command, cwd=str(repo))
if completed.returncode != 0:
    print(f"Cohort aggregation FAILED with exit status {completed.returncode}")
    raise SystemExit(completed.returncode)
print(f"Cohort metrics: {cohort_output}")
raise SystemExit(0)
PY
}

case "${1:-submit}" in
    submit) submit_batch ;;
    run) run_session ;;
    summarize) summarize_batch ;;
    *) fail "usage: $0 [submit|run|summarize]" ;;
esac
