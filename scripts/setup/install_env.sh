#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_DIR="${1:-$PROJECT_ROOT/.venv}"
BOOTSTRAP_PYTHON="${PYTHON_BIN:-python3}"
PYTORCH_INDEX="https://download.pytorch.org/whl/cu121"

"$BOOTSTRAP_PYTHON" - <<'PY'
import sys
if sys.version_info[:2] != (3, 10):
    raise SystemExit(
        f"Python 3.10 is required for the measured GPU stack; got {sys.version.split()[0]}"
    )
PY

if [[ ! -x "$ENV_DIR/bin/python" ]]; then
    "$BOOTSTRAP_PYTHON" -m venv "$ENV_DIR"
fi

PYTHON="$ENV_DIR/bin/python"
PIP=("$PYTHON" -m pip)

"${PIP[@]}" install --upgrade \
    pip==26.1.2 setuptools==80.9.0 wheel==0.45.1

# Torch 2.5.1 pins nvidia-cudnn-cu12==9.1.0.70, but that yanked artifact is not
# listed by PyPI, NVIDIA's index, or the cu121 index and cannot be relied on for a
# fresh install.  9.1.1.17 is the nearest listed cuDNN 9.1 wheel and passed the
# offline GPU smoke run.
"${PIP[@]}" install --no-deps \
    nvidia-cublas-cu12==12.1.3.1 \
    nvidia-cuda-cupti-cu12==12.1.105 \
    nvidia-cuda-nvrtc-cu12==12.1.105 \
    nvidia-cuda-runtime-cu12==12.1.105 \
    nvidia-cudnn-cu12==9.1.1.17 \
    nvidia-cufft-cu12==11.0.2.54 \
    nvidia-curand-cu12==10.3.2.106 \
    nvidia-cusolver-cu12==11.4.5.107 \
    nvidia-cusparse-cu12==12.1.0.106 \
    nvidia-nccl-cu12==2.21.5 \
    nvidia-nvjitlink-cu12==12.8.93 \
    nvidia-nvtx-cu12==12.1.105 \
    triton==3.1.0

"${PIP[@]}" install --no-deps --index-url "$PYTORCH_INDEX" \
    torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1

# Install the measured non-GPU environment without asking pip to resolve package
# metadata. Any normal resolver traversal through a Torch dependency reopens its
# unavailable cuDNN pin. requirements.txt remains the human-maintained top-level
# inventory; this lock contains its complete measured transitive closure.
"${PIP[@]}" install --no-deps \
    --requirement "$PROJECT_ROOT/requirements-runtime.lock"

# Ultralytics names the GUI OpenCV distribution as a dependency.  The headless
# distribution supplies the same cv2 module and is required on compute nodes.
"${PIP[@]}" install --no-deps ultralytics==8.4.8

# The PyPI WhisperX 3.7.4 wheel declares Torch/Torchaudio 2.8 and Triton >=3.3,
# unlike the validated study stack. Install the wheel itself only after
# all real dependencies are present.
"${PIP[@]}" install --no-deps whisperx==3.7.4

# Reassert packages which must win if a future transitive resolver path changes.
"${PIP[@]}" install --no-deps --constraint "$PROJECT_ROOT/constraints-gpu.txt" \
    numpy==2.0.2 pandas==2.2.3 sympy==1.13.1 \
    huggingface-hub==0.36.0 transformers==4.57.6 \
    lightning==2.6.0 pytorch-lightning==2.6.0 \
    ctranslate2==4.6.3 faster-whisper==1.2.1 av==15.1.0 \
    pyannote.audio==3.4.0 speechbrain==1.0.3 \
    opencv-python-headless==5.0.0.93

"$PYTHON" - <<'PY'
from importlib.metadata import PackageNotFoundError, version
import subprocess
import sys

expected = {
    "torch": "2.5.1+cu121",
    "torchvision": "0.20.1+cu121",
    "torchaudio": "2.5.1+cu121",
    "triton": "3.1.0",
    "nvidia-cudnn-cu12": "9.1.1.17",
    "whisperx": "3.7.4",
    "pyannote.audio": "3.4.0",
    "speechbrain": "1.0.3",
    "huggingface-hub": "0.36.0",
    "transformers": "4.57.6",
    "opencv-python-headless": "5.0.0.93",
    "numpy": "2.0.2",
    "pandas": "2.2.3",
}
errors = []
for package, wanted in expected.items():
    try:
        actual = version(package)
    except PackageNotFoundError:
        actual = "MISSING"
    print(f"{package}=={actual}")
    if actual != wanted:
        errors.append(f"{package}: expected {wanted}, got {actual}")

import torch
import torchaudio
import torchvision
if torch.version.cuda != "12.1":
    errors.append(f"torch CUDA: expected 12.1, got {torch.version.cuda}")

check = subprocess.run(
    [sys.executable, "-m", "pip", "check"], text=True,
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
)
allowed = (
    "ultralytics 8.4.8 requires opencv-python, which is not installed.",
    "torch 2.5.1+cu121 has requirement nvidia-cudnn-cu12==9.1.0.70",
    "whisperx 3.7.4 has requirement torch~=2.8.0",
    "whisperx 3.7.4 has requirement torchaudio~=2.8.0",
    "whisperx 3.7.4 has requirement triton>=3.3.0",
)
unexpected = [
    line for line in check.stdout.splitlines()
    if line and not any(line.startswith(prefix) for prefix in allowed)
]
if unexpected:
    errors.extend(f"unexpected pip check result: {line}" for line in unexpected)
if errors:
    raise SystemExit("Environment verification failed:\n  " + "\n  ".join(errors))
print("Environment verification passed (only documented metadata exceptions remain).")
PY
