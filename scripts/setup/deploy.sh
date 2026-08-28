#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# Require an explicit deployment target so a run cannot silently use a stale local copy.
TARGET="${1:-${DEPLOY_TARGET:-}}"
if [[ -z "$TARGET" ]]; then
    cat >&2 <<'USAGE'
Refusing deployment: no target given.

    bash scripts/setup/deploy.sh <target>
    DEPLOY_TARGET=<target> bash scripts/setup/deploy.sh

Example:
    bash scripts/setup/deploy.sh compute-host:/srv/expert-vision-agent-harness/
USAGE
    exit 4
fi
# Record the source commit: the deployed copy has no .git (excluded below), but the
# run manifest still requires provenance. Fail loudly rather than deploy an untraceable
# tree.
COMMIT="$(git -C "$PROJECT_ROOT" rev-parse HEAD 2>/dev/null || true)"
if [[ -z "$COMMIT" ]]; then
    echo "Refusing deployment: source is not a git checkout, so the deployed tree could not be traced to a commit" >&2
    exit 3
fi
# Mark an uncommitted source tree so the run manifest cannot imply that the deployed
# code exactly equals the recorded commit.
if [[ -n "$(git -C "$PROJECT_ROOT" status --porcelain 2>/dev/null)" ]]; then
    COMMIT="${COMMIT}-dirty"
fi
printf '%s\n' "$COMMIT" > "$PROJECT_ROOT/DEPLOYED_COMMIT"

# This is intentionally additive and never copies local weights.
rsync -a --human-readable --exclude='.venv/' --exclude='__pycache__/' --exclude='.git/' --exclude='data/sessions/' --exclude='models/' --exclude='node_modules/' --exclude='*.bak-*' "$PROJECT_ROOT/" "$TARGET"
