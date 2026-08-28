#!/bin/bash
# Second identical focal pass, to measure within-condition repeatability.
#
#   sbatch scripts/run_repeatability.sbatch
#
# The T/M contrast is reported as a 67.4% mean symmetric detection overlap. Without a
# T-vs-T and M-vs-M baseline that number cannot be read: if two identical runs also overlap
# ~67%, the contrast is generation variability rather than an effect of delivered visual
# context. This reruns ONLY stage 14 against the already-assembled windows, so it reuses
# every extraction stage, and writes to a separate artifact so the reported run is untouched.
#SBATCH --job-name=csr_repeat
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --time=04:00:00
#SBATCH --output=slurm-csr-repeat-%j.out

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO="${CLINICAL_SIM_REPO:-$(cd "$SCRIPT_DIR/.." && pwd)}"
cd "$REPO" || exit 1
source .venv/bin/activate
export PYTHONPATH="$REPO:$PYTHONPATH"
export OLLAMA_MODELS="${OLLAMA_MODELS:-$REPO/models/ollama}"
export OLLAMA_CONTEXT_LENGTH=32768
export PATH="$REPO/.venv/bin:$PATH"

OLLAMA_BIN="${OLLAMA_BIN:-$(command -v ollama || true)}"
OLLAMA_PORT=$((11700 + ${SLURM_JOB_ID:-0} % 90))
export OLLAMA_HOST="127.0.0.1:${OLLAMA_PORT}"
URL="http://127.0.0.1:${OLLAMA_PORT}"

[ -x "$OLLAMA_BIN" ] || { echo "ERROR: no ollama binary" >&2; exit 1; }
"$OLLAMA_BIN" serve &>"/tmp/ollama_repeat_${SLURM_JOB_ID}.log" &
PID=$!
for _ in $(seq 1 30); do curl -sf "$URL/api/tags" >/dev/null 2>&1 && break; sleep 1; done
kill -0 "$PID" 2>/dev/null || { echo "ERROR: ollama died" >&2; exit 1; }
curl -sf "$URL/api/tags" >/dev/null 2>&1 || { echo "ERROR: ollama unhealthy" >&2; exit 1; }
echo "Ollama ready on ${OLLAMA_PORT}"

export LLM_BASE_URL="$URL/v1"
export LLM_API_KEY=ollama-local
export LLM_MODEL=qwen2.5:7b

STATUS=0
for i in 1 2 3 4 5 6 7 8 9; do
    SID=$(printf "session_%03d" "$i")
    OUT="data/sessions/$SID/processed/moments_multimodal_repeat.json"
    echo "=== $SID -> $OUT ==="
    python3 -u scripts/focal/pipeline_stages.py run-focal \
        --session-id "$SID" \
        --transcript "data/sessions/$SID/raw/diarized_transcript_full.json" \
        --windows "data/sessions/$SID/processed/multimodal_windows.json" \
        --runtime-config "$REPO/configs/focal_runtime_qwen2_5_7b_ollama_q4km.json" \
        --output "$OUT" || STATUS=1
done
echo "REPEAT_EXIT=$STATUS"
exit "$STATUS"
