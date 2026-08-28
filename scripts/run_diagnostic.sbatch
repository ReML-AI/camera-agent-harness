#!/bin/bash
# Run a short CPU-only diagnostic through the scheduler instead of on the login node.
#
#   sbatch scripts/run_diagnostic.sbatch scripts/diagnostics/readiness_gate.py session_001
#
# The pipeline itself has run_session.sbatch. This exists because the probes around it --
# readiness gate, gate re-classification, window assembly -- are real compute, and running
# them over an ssh session puts them on the login node that everyone else shares.
#SBATCH --job-name=csr_diag
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --time=00:30:00
#SBATCH --output=slurm-csr-diag-%j.out

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO="${CLINICAL_SIM_REPO:-$(cd "$SCRIPT_DIR/.." && pwd)}"
cd "$REPO" || exit 1
source .venv/bin/activate
export PYTHONPATH="$REPO:$PYTHONPATH"

python3 -u "$@"
DIAG_EXIT=$?
echo "DIAG_EXIT=$DIAG_EXIT"
exit "$DIAG_EXIT"
