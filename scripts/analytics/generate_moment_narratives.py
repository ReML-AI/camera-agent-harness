#!/usr/bin/env python3
"""
Stage 2: LLM Narrative Generation for Moment Contexts.

Reads moment_contexts.json, calls LLM API to generate:
- Behavioral narrative (2-3 sentences, student-specific framing)
- Light tags (from predefined set)
- Discussion prompt for facilitator

Uses a local LLM (Qwen 7B) via the OpenAI-compatible endpoint configured by
scripts/utils/llm_client.py (LLM_BASE_URL, LLM_MODEL env vars).

Outputs: data/processed/moment_narratives.json
"""

import json
import os
import re
import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.llm_client import chat, get_model

# Legacy defaults (backward compat when no --session-id)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_LEGACY_DATA_DIR = _PROJECT_ROOT / "data" / "processed"
ENV_PATH = _PROJECT_ROOT / ".env"

def _get_paths(session_id: str = None) -> dict:
    """Return dict of paths, using session_paths when session_id is provided."""
    if session_id is not None:
        from scripts.utils.session_paths import processed_dir
        _processed = processed_dir(session_id)
        return {
            "moment_contexts": _processed / "moment_contexts.json",
            "output_moment_narratives": _processed / "moment_narratives.json",
        }
    # Legacy paths
    return {
        "moment_contexts": _LEGACY_DATA_DIR / "moment_contexts.json",
        "output_moment_narratives": _LEGACY_DATA_DIR / "moment_narratives.json",
    }

TAG_OPTIONS = [
    # Communication patterns
    "closed_loop_present",          # Directive confirmed: order given AND acknowledged
    "closed_loop_absent",           # Order/request given without confirmation
    "directive_given",              # Clear clinical order issued
    "question_unanswered",          # Question asked but no response in window
    "team_discussion",              # 2+ speakers actively exchanging
    "monologue",                    # Extended single-speaker segment with no team input

    # Clinical actions
    "medication_verification",      # Drug name, dose, or route explicitly stated
    "patient_assessment",           # Direct patient check (vitals, responsiveness, etc.)
    "escalation_trigger",           # Recognition of worsening condition
    "task_delegation",              # Explicit assignment of task to team member

    # Attention patterns
    "attention_on_patient",         # Team visual focus on patient
    "attention_away_from_patient",  # Team visual focus elsewhere during critical action
    "monitor_focused",              # Team watching monitor (may be appropriate)

    # Concerns
    "role_confusion",               # Unclear who is responsible
    "information_gap",              # Missing or incomplete clinical information shared
]


def load_env():
    """Load .env file if it exists."""
    if ENV_PATH.exists():
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    if key and value:
                        os.environ.setdefault(key, value)


def build_prompt(moment: dict, speaker_roles: dict) -> str:
    """Build the LLM prompt for a single moment."""
    ts = moment["timestamp"]
    te = moment["end_timestamp"]
    time_str = f"{int(ts//60):02d}:{int(ts%60):02d} - {int(te//60):02d}:{int(te%60):02d}"

    # Build categories string from deduplicated categories array if present
    categories_list = moment.get("categories", [])
    if categories_list:
        cat_names = [c["category"] for c in categories_list]
        categories_str = ", ".join(cat_names)
    else:
        categories_str = moment["category"]

    # Speech summary
    speech_lines = []
    for spk, data in moment["speech"]["per_speaker"].items():
        role = speaker_roles.get(spk, spk)
        speech_lines.append(
            f"  {role}: {data['talk_time_pct']}% talk time, "
            f"{len(data['utterances'])} utterance(s)"
            + (", spoke first" if data["spoke_first"] else "")
        )
        # Include ALL utterances (up to 5) so the LLM sees specific clinical language
        for utt in data["utterances"][:5]:
            speech_lines.append(f'    > "{utt[:150]}"')

    if not speech_lines:
        speech_lines = ["  No speech detected in this window."]

    # Gaze summary — team-level from all tracks + per-speaker if available
    gaze_lines = []
    team_gaze = moment["gaze"].get("team_gaze", {})
    if team_gaze:
        gaze_parts = [f"{target}: {pct}%" for target, pct in team_gaze.items()]
        gaze_lines.append(f"  Team gaze (all visible people): {', '.join(gaze_parts)} ({moment['gaze'].get('team_gaze_samples', 0)} samples)")

    for spk, data in moment["gaze"]["per_speaker"].items():
        role = speaker_roles.get(spk, spk)
        targets = {k: v for k, v in data.items() if k not in ("samples",)}
        gaze_lines.append(f"  {role}: {targets} ({data['samples']} samples)")

    if not gaze_lines:
        gaze_lines = ["  No gaze data available for this window."]

    # Gaze interpretation hint for the LLM
    patient_attn = moment["gaze"]["team_patient_attention_pct"]
    if patient_attn == 0:
        gaze_hint = "No gaze data was recorded for this window."
    elif patient_attn < 20:
        gaze_hint = f"Low patient attention ({patient_attn}%) — team may have been focused elsewhere."
    elif patient_attn > 60:
        gaze_hint = f"High patient attention ({patient_attn}%) — team was visually engaged with the patient."
    else:
        gaze_hint = f"Moderate patient attention ({patient_attn}%)."

    # Vitals summary — skip entirely if no data to save tokens
    vitals = moment["vitals"]
    vitals_lines = []
    has_vitals = vitals["readings_in_window"] > 0
    if has_vitals:
        for key, label in [("spo2", "SpO2"), ("heart_rate", "HR"), ("blood_pressure", "BP")]:
            v = vitals.get(key)
            if v:
                vitals_lines.append(f"  {label}: {v['start']} → {v['end']} ({v['trend']})")
        if not vitals_lines:
            has_vitals = False  # readings exist but all individual vitals are null

    # Dynamics
    dyn = moment["dynamics"]
    dyn_lines = [
        f"  Closed-loop communication: {'Yes' if dyn['closed_loop_detected'] else 'No'}",
        f"  Speaker transitions: {moment['speech']['speaker_transitions']}",
    ]
    if dyn["silence_gaps"]:
        dyn_lines.append(f"  Silence gaps: {len(dyn['silence_gaps'])} (>{dyn['silence_gaps'][0]['duration']:.0f}s)")

    vitals_section = ""
    if has_vitals:
        vitals_section = f"""
VITAL SIGNS:
{chr(10).join(vitals_lines)}
"""

    # Build tag definitions string for the prompt
    tag_definitions = """
TAG DEFINITIONS (use 1-3 that best fit this moment):
  Communication patterns:
    closed_loop_present     — Directive confirmed: order given AND acknowledged by another team member
    closed_loop_absent      — Order/request given without confirmation from the team
    directive_given         — Clear clinical order issued (e.g., "give 0.5mg adrenaline")
    question_unanswered     — Question asked but no response in the window
    team_discussion         — 2+ speakers actively exchanging information
    monologue              — Extended single-speaker segment with no team input
  Clinical actions:
    medication_verification — Drug name, dose, or route explicitly stated aloud
    patient_assessment      — Direct patient check (vitals, responsiveness, airway, etc.)
    escalation_trigger      — Recognition of worsening condition or call for help
    task_delegation         — Explicit assignment of task to a team member
  Attention patterns:
    attention_on_patient          — Team visual focus on patient (gaze data supports)
    attention_away_from_patient   — Team visual focus elsewhere during critical action
    monitor_focused               — Team watching monitor (may be appropriate or not)
  Concerns:
    role_confusion    — Unclear who is responsible for the current task
    information_gap   — Missing or incomplete clinical information shared"""

    prompt = f"""You are a clinical simulation debrief analyst. Your job is to write a specific, scenario-grounded observation for a debrief facilitator.

SCENARIO CONTEXT:
  Patient: George, 74 years old
  Situation: Transferred from ED to ward, anaphylaxis progressing to cardiac arrest
  Team: Student nurses and supervising doctors in a clinical simulation

CLINICAL EVENT:
  Clinical Categories: {categories_str}
  Time: {time_str} ({moment['duration']:.0f}s)
  Trigger utterance: "{moment['original_text'][:200]}"
  Importance: {moment['importance']}

TEAM SPEECH:
{chr(10).join(speech_lines)}
  Silence: {moment['speech']['silence_seconds']}s

VISUAL ATTENTION:
{chr(10).join(gaze_lines)}
  Summary: {gaze_hint}
{vitals_section}
TEAM DYNAMICS:
{chr(10).join(dyn_lines)}
{tag_definitions}

Respond in this exact JSON format:
{{
  "narrative": "<2-3 sentence observation>",
  "tags": ["tag1", "tag2"],
  "discussion_prompt": "<specific debrief question>"
}}

FIELD INSTRUCTIONS:

1. narrative: A 2-3 sentence observation that:
   - Describes the specific clinical action happening (not just "initiated communication")
   - References the patient (George) when relevant
   - Notes whether the team interaction was effective or had gaps
   - If gaze data shows something notable (e.g., <20% patient attention, or high patient attention), mention it

2. tags: 1-3 tags from the TAG DEFINITIONS above. Choose only tags supported by the evidence.

3. discussion_prompt: A specific debrief question that:
   - References the exact clinical action observed (e.g., drug name, assessment step, escalation decision)
   - Names the role(s) involved (e.g., "the Primary Nurse", "the Supervising Doctor")
   - Points to what the behavioral evidence shows (e.g., "while the team's attention was on the monitor")
   - Can be read aloud by a facilitator without modification
   DO NOT write generic questions like "How can we improve communication?" or "How could the team improve engagement?"
   Each question must be unique to THIS specific moment.

IMPORTANT: Avoid these generic patterns:
- "How can we improve communication..."
- "How could the team better engage..."
- "What strategies can we implement..."
Instead, ask about the SPECIFIC clinical action, drug, assessment, or decision in this moment.

Return ONLY the JSON object, no other text."""

    return prompt


def parse_llm_response(text: str) -> dict:
    """Parse JSON from LLM response, with fallback extraction."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {
            "narrative": text[:300],
            "tags": [],
            "discussion_prompt": "What happened during this moment?",
        }


NARRATIVE_TIMEOUT_SECONDS = 600.0


def generate_narrative(moment: dict, speaker_roles: dict = None, model: str = None) -> dict:
    """Generate narrative via the configured local LLM."""
    prompt = build_prompt(moment, speaker_roles or {})
    # The client refuses to guess a timeout, and this call never supplied one, so every
    # narrative raised and the stage still reported success with zero narratives written.
    # 600s matches the focal runtime's declared timeout.
    resp = chat(
        prompt=prompt, model=model, max_tokens=500, temperature=0.7,
        timeout_seconds=NARRATIVE_TIMEOUT_SECONDS,
    )
    return parse_llm_response(resp["text"])


def main(session_id: str = None):
    paths = _get_paths(session_id)

    # The public pipeline uses stable speaker IDs. Governed clinical roles can be joined
    # by an authorized downstream application but are never embedded in this artifact.
    narrative_roles = {}

    print("=" * 60)
    print("MOMENT NARRATIVE GENERATION (Stage 2)")
    print("=" * 60)

    # Load .env
    load_env()

    # Load moment contexts
    ctx_path = paths["moment_contexts"]
    if not ctx_path.exists():
        print("ERROR: Run compute_moment_context.py first.")
        return

    with open(ctx_path) as f:
        contexts = json.load(f)

    moments = contexts["moments"]
    print(f"\n{len(moments)} moments to process")

    model_name = get_model()
    print(f"Using local LLM ({model_name} @ {os.environ.get('LLM_BASE_URL', 'http://localhost:11434/v1')})")

    narratives = {}
    for i, moment in enumerate(moments):
        mid = moment["moment_id"]
        print(f"  [{i+1}/{len(moments)}] Moment {mid}: {moment['category']} at {moment['timestamp']:.0f}s...", end=" ")

        try:
            result = generate_narrative(moment, narrative_roles, model=model_name)
            narratives[str(mid)] = {
                **result,
                "generated_at": __import__("datetime").datetime.now().isoformat(),
            }
            print(f"OK ({len(result.get('tags', []))} tags)")
        except Exception as e:
            print(f"ERROR: {e}")
            narratives[str(mid)] = {
                "status": "failed",
                "narrative": None,
                "tags": [],
                "discussion_prompt": None,
                "generated_at": __import__("datetime").datetime.now().isoformat(),
                "error": str(e)[:200],
            }

        # Rate limit
        if (i + 1) % 5 == 0:
            time.sleep(1)

    output = {
        "metadata": {
            "model": model_name,
            "total_narratives": len(narratives),
            "generated_at": __import__("datetime").datetime.now().isoformat(),
        },
        "narratives": narratives,
    }

    output_path = paths["output_moment_narratives"]
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    success = sum(1 for n in narratives.values() if "error" not in n)
    print(f"\nSaved {len(narratives)} narratives ({success} successful)")
    # A partial artifact is retained for diagnosis, but it is not a successful stage.
    # Consumers must never mistake an error placeholder for generated content.
    if success != len(narratives):
        failed = len(narratives) - success
        raise SystemExit(
            f"{failed} of {len(narratives)} narratives failed for "
            f"{session_id or 'session'}; inspect {output_path}"
        )
    print(f"Output: {output_path} ({output_path.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate moment narratives via LLM")
    parser.add_argument("--session-id", default=None, help="Session ID (omit for legacy paths)")
    args = parser.parse_args()
    main(session_id=args.session_id)
