#!/bin/bash
# Run the full pipeline for one session on a GPU compute node.
#
#   sbatch --job-name=s008 scripts/run_session.sbatch session_008
#   sbatch --job-name=all  scripts/run_session.sbatch all
#
# Everything runs in-process on the allocated node; nothing runs on the login node.
# Model paths are passed explicitly because the pipeline has no defaults for them by
# design — an unstated model is a provenance hole.
#SBATCH --job-name=csr_run
#SBATCH --ntasks=1
# Three camera workers split this allocation into 12 threads each.
#SBATCH --cpus-per-task=36
#SBATCH --gres=gpu:1
#SBATCH --time=12:00:00
#SBATCH --output=slurm-csr-run-%x-%j.out

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO="${CLINICAL_SIM_REPO:-$(cd "$SCRIPT_DIR/.." && pwd)}"
cd "$REPO" || exit 1
source .venv/bin/activate
export PYTHONPATH="$REPO:$PYTHONPATH"
export OLLAMA_MODELS="${OLLAMA_MODELS:-$REPO/models/ollama}"
export OLLAMA_CONTEXT_LENGTH=32768
export TORCH_HOME="${TORCH_HOME:-$REPO/models/torch-cache}"
# pyannote resolves through huggingface_hub, which only reads the HF cache. The models are
# staged inside the project so a run does not depend on a directory outside it.
export HF_HUB_CACHE="$REPO/models/hf-cache"
export PYANNOTE_CACHE="$HF_HUB_CACHE"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export PATH="$REPO/.venv/bin:$PATH"

FFMPEG_DIR=$(python3 -c "import imageio_ffmpeg,os;print(os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe()))" 2>/dev/null)
[ -n "$FFMPEG_DIR" ] && export PATH="$FFMPEG_DIR:$PATH"

OLLAMA_BIN="${OLLAMA_BIN:-$(command -v ollama || true)}"
# Give every job an isolated Ollama endpoint so concurrent sessions cannot share state.
OLLAMA_PORT=$((11500 + ${SLURM_JOB_ID:-0} % 400))
export OLLAMA_HOST="127.0.0.1:${OLLAMA_PORT}"
OLLAMA_URL="http://127.0.0.1:${OLLAMA_PORT}"
if curl -sf "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
    echo "ERROR: port ${OLLAMA_PORT} is already serving before this job started it"
    exit 1
fi
if [ -x "$OLLAMA_BIN" ]; then
    "$OLLAMA_BIN" serve &>"/tmp/ollama_${SLURM_JOB_ID}.log" &
    OLLAMA_PID=$!
    for _ in $(seq 1 30); do
        curl -sf "${OLLAMA_URL}/api/tags" >/dev/null 2>&1 && break
        sleep 1
    done
    # Verify that this job owns the endpoint it uses.
    if ! kill -0 "$OLLAMA_PID" 2>/dev/null; then
        echo "ERROR: this job's ollama process died; refusing to use another job's server"
        exit 1
    fi
    if curl -sf "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
        FOCAL_RUNTIME_CONFIG="$REPO/configs/focal_runtime_qwen2_5_7b_ollama_q4km.json"
        OLLAMA_SERVER_VERSION=$(curl -fsS "${OLLAMA_URL}/api/version" | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])')
        EXPECTED_OLLAMA_VERSION=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["backend_version"])' "$FOCAL_RUNTIME_CONFIG")
        if [ "$OLLAMA_SERVER_VERSION" != "$EXPECTED_OLLAMA_VERSION" ]; then
            echo "ERROR: Ollama server version $OLLAMA_SERVER_VERSION does not match focal runtime config $EXPECTED_OLLAMA_VERSION"
            exit 1
        fi
        echo "Ollama ready (server version $OLLAMA_SERVER_VERSION)"
        export LLM_BASE_URL="${OLLAMA_URL}/v1"
        export LLM_API_KEY=ollama-local
        export LLM_MODEL=qwen2.5:7b
    else
        echo "ERROR: Ollama did not become healthy on ${OLLAMA_PORT}; refusing to run"
        exit 1
    fi
else
    echo "ERROR: no ollama binary at $OLLAMA_BIN; the focal stage cannot run"
    exit 1
fi

SID="${1:-session_008}"
echo "================================================================"
echo "RUN  session=$SID  node=$(hostname)  gpu=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)"
echo "commit=$(cat "$REPO/DEPLOYED_COMMIT" 2>/dev/null || echo UNKNOWN)"
echo "================================================================"

RESOURCE_LOG="$REPO/tmp/resources_${SLURM_JOB_ID}.csv"
nvidia-smi \
    --query-gpu=timestamp,index,name,memory.used,memory.total,utilization.gpu,utilization.memory \
    --format=csv --loop=1 >"$RESOURCE_LOG" 2>&1 &
RESOURCE_SAMPLER_PID=$!
stop_resource_sampler() {
    kill "$RESOURCE_SAMPLER_PID" 2>/dev/null || true
    wait "$RESOURCE_SAMPLER_PID" 2>/dev/null || true
}
trap stop_resource_sampler EXIT
echo "resource_log=$RESOURCE_LOG"

python3 -u scripts/run_pipeline.py --session-id "$SID" --local \
    --per-camera-workers 3 \
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
    "${@:2}"
PIPELINE_EXIT=$?
echo "PIPELINE_EXIT=$PIPELINE_EXIT"
echo "Done at $(date)"
exit "$PIPELINE_EXIT"
