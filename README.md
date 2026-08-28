# Expert Vision Agent Harness

Software artifact for **“Expert Vision Agent Harness: Verifiable Multi-View
Evidence for Clinical Simulation Debriefing.”**

The **Expert Vision Agent Harness** combines *expert vision*—the educator's integrated,
evidence-oriented view of who spoke, where attention was directed, what changed in the
scenario, and how participants responded—with the orchestration, context controls, and
provenance mechanisms of an agent harness. It extends expert observation across
multiple cameras, room audio, and monitor data by linking identities, selecting
evidence-bearing views, assembling multimodal context, and verifying the path from
observation to debrief suggestion.

## Artifact status and scope

This implementation powered the paper's nine-session governed-data evaluation. The
public artifact provides the pipeline, configuration, schemas, metric implementations,
provenance contracts, and synthetic validation suite. Participant-protecting governance
keeps clinical recordings, identities, and annotations in the authorized environment,
while the released contracts make the computational method inspectable and reusable.
Clinician assessments provide an independent human evaluation layer.

## What the pipeline does

The master entry point, `scripts/run_pipeline.py`, contains 21 per-session stages plus
one cohort aggregation stage. In outline, it:

1. aligns transcription, person tracks, active-speaker evidence, and camera streams;
2. assembles cross-camera identities and selects one camera per transcript segment;
3. extracts head pose, scene descriptions, monitor vital signs, and three-target
   attention (`patient`, `person`, `other`);
4. produces independent CLIP-urgency, vital-threshold, and transcript-keyword flags;
5. assembles five semantic context fields: `transcript`, `speaker_dynamics`,
   `visual_scene`, `visual_attention`, and `modality_coverage`;
6. runs the fixed K/T/M comparison and validates evidence citations; and
7. emits count-first per-session metrics and a cohort aggregate.

All semantic intervals are half-open `[start, end)` intervals in aligned seconds.
Unavailable extraction is represented explicitly; it is not replaced with guessed or
synthetic evidence.

Versioned interface contracts live in `schemas/v1/` and `prompts/`; metric definitions
and their executable implementations live in `scripts/metrics/definitions.py`.

## Quick validation (no clinical data or model weights)

Python 3.12 is sufficient for the source-only test suite:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-test.lock
.venv/bin/python -m pytest -q
```

In a clean checkout, the optional test that inspects the upstream Light-ASD source is
skipped until that pinned checkout has been staged. All other tests must pass.

The frontend prototype can be checked independently:

```bash
cd frontend
npm ci
npm run build
```

## Interactive demo

Live demo: <https://reml-ai.github.io/expert-vision-agent-harness/>

`demo/` contains a standalone redesign of the educator review experience. It
uses a muted, face-anonymized 15-second excerpt from one authorized simulation
session to demonstrate coordinated views, segment-level camera selection, evidence
tracing, explicit modality availability, educator decisions, and debrief-plan
curation. Participant labels are presentation-only identifiers, and the textual
review moments are illustrative. The demo includes no raw session footage or
audio and does not require the pipeline, a backend, or a build step.

Open `demo/index.html` directly in a browser, or serve the repository locally:

```bash
python3 -m http.server 8080
```

Then visit `http://localhost:8080/demo/`.

The live site is published from `demo/` by `.github/workflows/pages.yml`; nothing
else in this repository is deployed.

## Full runtime setup

The measured GPU environment requires Python 3.10 and CUDA 12.1. The installer keeps
the deliberately ordered Torch, WhisperX, and Ultralytics setup in one place:

```bash
PYTHON_BIN=python3.10 bash scripts/setup/install_env.sh
.venv/bin/python scripts/setup/fetch_models.py --fetch
.venv/bin/python scripts/setup/fetch_models.py --verify
.venv/bin/python scripts/setup/preflight.py
```

`third_party/manifest.yaml` records component versions, source locations, staging
paths, hashes where available, and manual procedures. Model resolution is a setup
operation; runtime stages do not download weights. A source-only checkout is expected
to fail model verification until the declared weights, gated caches, local Ollama
model, and project-trained role classifier have been staged. The command reports the
exact current blockers rather than the documentation maintaining a duplicate list.

The top-level `requirements.txt` is the human-maintained dependency inventory.
`requirements-runtime.lock` and `constraints-gpu.txt` capture the measured runtime
stack used by `install_env.sh`.

## Input layout

Governed inputs stay outside version control under:

```text
data/sessions/<session_id>/
├── videos/
│   ├── cam1.mp4
│   ├── cam2.mp4
│   ├── cam3.mp4
│   └── monitor.mp4
├── raw/
└── processed/
```

Session manifests provide synchronization, acquisition boundaries, and authorized
metadata. Static attention calibration is selected by exact session and camera from
`scripts/gaze/patient_zone_calibrations.json`; a missing calibration is a hard error.

## Running the pipeline

After authorized inputs and every required component are present:

```bash
.venv/bin/python scripts/run_pipeline.py --session-id session_001 --dry-run
.venv/bin/python scripts/run_pipeline.py --session-id session_001
.venv/bin/python scripts/run_pipeline.py --session-id all
.venv/bin/python scripts/run_pipeline.py \
  --session-id session_001 \
  --from-stage 10_speaker_dynamics
```

The run manifest records stage state, source revision, operator inputs, component
configuration, and artifact hashes. Restarting from a stage reuses only artifacts that
remain valid under that manifest.

For Slurm execution, set `CLINICAL_SIM_REPO`, and optionally
`CLINICAL_SIM_SLURM_PARTITION`, `CLINICAL_SIM_SLURM_NODELIST`, `OLLAMA_BIN`,
`OLLAMA_MODELS`, and `TORCH_HOME`; then use `scripts/run_all_sessions.sbatch`.
No institution-specific filesystem path is required by the checked-in wrappers.

## Auxiliary review prototype

`backend/` and `frontend/` provide a companion educator-review prototype for exploring
the moments and evidence produced by the harness. It complements the paper's K/T/M
evaluation with a concrete clinician-in-the-loop review interface. The prototype is
configured for trusted-workstation use and binds to `127.0.0.1`; production deployment
would require an authentication and security layer.

```bash
# terminal 1
cd backend
../.venv/bin/pip install -r requirements.txt
../.venv/bin/python run.py

# terminal 2
cd frontend
npm ci
npm run dev
```

The frontend development server proxies `/api` to `http://localhost:8001`.

## Repository map

```text
backend/                  local-only review API prototype
configs/                  fixed runtime and OCR configuration
frontend/                 local-only React review prototype
demo/                     static interactive research demo (published to GitHub Pages)
prompts/                  focal prompt and output contracts
requirements*.txt         runtime and test dependency specifications
constraints-gpu.txt       validated GPU-stack constraints
schemas/v1/               versioned JSON Schemas
scripts/                  pipeline stages, setup, diagnostics, and metrics
tests/                    synthetic, contract, setup, and backend-boundary tests
third_party/manifest.yaml model/source provenance and staging requirements
```

## Data governance

No raw clinical recording, participant identity, governed label, transcript, run
output, or model weight belongs in this repository. The only recording-derived media
is the short, muted, face-anonymized demo excerpt described above; it is a
presentation artifact, not a reusable dataset. Local outputs inherit the governance
rules of their source data. Possession of this code does not authorize clinical-data
processing; ethics, consent, access, retention, and output-release controls remain
external requirements.

## License

This project's source code is licensed under the GNU Affero General Public License
v3.0 only (`AGPL-3.0-only`). See `LICENSE`. Third-party code, models, and weights retain
their own terms, as recorded in `third_party/manifest.yaml`; model weights are not
redistributed in this repository.
