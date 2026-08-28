#!/usr/bin/env python3
"""Diagnostic: does the focal model use visual evidence when transcript cannot dominate?

Runs three conditions over the SAME delivered windows:
  T  transcript only          (the paper's reduced harness)
  V  visual only              (diagnostic; not a paper condition)
  M  both                     (the paper's full harness)

This does not modify the pipeline or its T/M contract. It answers one question: are the
visual records usable by this model at all, or only ignored when transcript is present.
"""
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.analytics.assemble_multimodal_windows import (  # noqa: E402
    SEMANTIC_FIELDS,
    _canonical,
    _prompt_attention,
    _prompt_coverage,
    _prompt_transcript,
    _thin_attention_records,
    PROMPT_ATTENTION_RECORDS_PER_SECOND,
)
from scripts.focal.prompt import PromptArtifacts  # noqa: E402
from scripts.focal.runtime import FocalRequest  # noqa: E402
from scripts.focal.pipeline_stages import OpenAICompatibleEndpoint, _runtime  # noqa: E402

VISUAL = ("visual_scene", "visual_attention")
HEADINGS = {
    "transcript": "Transcript",
    "speaker_dynamics": "Speaker dynamics",
    "visual_scene": "Visual scene",
    "visual_attention": "Visual attention",
    "modality_coverage": "Modality coverage",
}




# Candidate field orders for the field-order sensitivity diagnostic. modality_coverage
# is last in every candidate because it describes the other fields rather than being
# evidence about the session.
CANDIDATE_ORDERS = {
    "transcript_first": (
        "transcript", "speaker_dynamics", "visual_scene", "visual_attention",
        "modality_coverage",
    ),
    "visual_first": (
        "visual_scene", "visual_attention", "transcript",
        "speaker_dynamics", "modality_coverage",
    ),
    "interleaved": (
        "transcript", "visual_scene", "speaker_dynamics", "visual_attention",
        "modality_coverage",
    ),
    "attention_first": (
        "visual_attention", "visual_scene", "transcript",
        "speaker_dynamics", "modality_coverage",
    ),
    "speech_last": (
        "visual_scene", "visual_attention", "speaker_dynamics",
        "transcript", "modality_coverage",
    ),
}

# Which modality an evidence id belongs to, by its declared prefix.
ID_MODALITY = {
    "segment": "transcript",
    "scene": "visual_scene",
    "attention": "visual_attention",
}
SCORED_MODALITIES = ("transcript", "visual_scene", "visual_attention")


def _normalise(counts):
    total = sum(counts.get(m, 0) for m in SCORED_MODALITIES)
    if total == 0:
        return {m: 0.0 for m in SCORED_MODALITIES}
    return {m: counts.get(m, 0) / total for m in SCORED_MODALITIES}


def _l1(left, right):
    return sum(abs(left[m] - right[m]) for m in SCORED_MODALITIES)


def delivered_distribution(windows):
    """Share of delivered evidence ids per modality, over the windows actually sent."""
    counts = Counter()
    for window in windows:
        context = window["context"]
        for item in context.get("transcript") or []:
            if isinstance(item, dict) and item.get("evidence_id"):
                counts["transcript"] += 1
        scene = context.get("visual_scene")
        if isinstance(scene, dict) and scene.get("evidence_id"):
            counts["visual_scene"] += 1
        attention = context.get("visual_attention")
        if isinstance(attention, dict):
            counts["visual_attention"] += len(attention.get("records") or [])
    return _normalise(counts)


def cited_distribution(raw):
    counts = Counter()
    for cited in re.findall(r'"((?:segment|scene|attention)-[A-Za-z0-9_.-]+)"', raw):
        counts[ID_MODALITY[cited.split("-")[0]]] += 1
    return _normalise(counts), counts


def _compact_transcript(segments):
    """One line per segment instead of JSON objects.

    Identical content and identical evidence ids; only the field-name scaffolding is
    dropped. JSON repeats "evidence_id"/"speaker_id"/"start_seconds"/"end_seconds"/"text"
    on every segment, which is most of the transcript's characters.
    """
    if not isinstance(segments, list):
        return _canonical(segments)
    lines = []
    for item in segments:
        if not isinstance(item, dict):
            return _canonical(segments)
        lines.append(
            f"{item.get('evidence_id')} {item.get('speaker_id')} "
            f"[{item.get('start_seconds')},{item.get('end_seconds')}] "
            f"{item.get('text', '').strip()}"
        )
    return " | ".join(lines)


def render(window, condition, *, visual_first=False, compact_transcript=False,
           order=None):
    """Render one window for T, V or M, reusing the pipeline's own projections.

    `visual_first` and `compact_transcript` are the two diagnostic variables. Each is
    varied alone so any change in citation behaviour is attributable.
    """
    source = window["context"]
    lines = [
        f"Window ID: {window['window_id']}",
        f"Interval seconds: [{window['start_seconds']}, {window['end_seconds']})",
    ]
    if order is None:
        order = (
            (*VISUAL, "transcript", "speaker_dynamics", "modality_coverage")
            if visual_first else SEMANTIC_FIELDS
        )
    for field in order:
        value = source[field]
        if field == "modality_coverage":
            coverage = json.loads(json.dumps(value))
            hidden = VISUAL if condition == "T" else (
                ("transcript", "speaker_dynamics") if condition == "V" else ()
            )
            for name in hidden:
                coverage[name] = {"present": False, "delivered": False, "evidence_ids": []}
            rendered = _canonical(_prompt_coverage(coverage))
        elif condition == "T" and field in VISUAL:
            rendered = "not available"
        elif condition == "V" and field in ("transcript", "speaker_dynamics"):
            rendered = "not available"
        elif value is None:
            rendered = "not available"
        elif field == "transcript":
            projected = _prompt_transcript(value)
            rendered = (
                _compact_transcript(projected) if compact_transcript
                else _canonical(projected)
            )
        elif field == "visual_attention":
            projected = _prompt_attention(value)
            if isinstance(projected.get("records"), list):
                projected = {**projected, "records": _thin_attention_records(
                    projected["records"], per_second=PROMPT_ATTENTION_RECORDS_PER_SECOND)}
            rendered = _canonical(projected)
        else:
            rendered = _canonical(value)
        lines.append(f"{HEADINGS[field]}: {rendered}")
    return "\n".join(lines)


def main():
    session = sys.argv[1] if len(sys.argv) > 1 else "session_001"
    root = Path("data/sessions") / session / "processed"
    windows_doc = json.loads((root / "multimodal_windows.json").read_text())
    delivered = set(windows_doc["focal_delivery"]["delivered_window_ids"])
    windows = [w for w in windows_doc["windows"] if w["window_id"] in delivered]

    artifacts = PromptArtifacts.load()
    runtime = _runtime(
        json.loads(Path("configs/focal_runtime_qwen2_5_7b_ollama_q4km.json").read_text())
    )
    endpoint = OpenAICompatibleEndpoint(
        base_url=os.environ.get("LLM_BASE_URL", "http://127.0.0.1:11434/v1"),
        api_key="ollama-local"
    )

    speakers = sorted({
        s.get("speaker_id")
        for w in windows for s in (w["context"].get("transcript") or [])
        if isinstance(s, dict) and s.get("speaker_id")
    })
    duration = max(w["end_seconds"] for w in windows)

    print(f"session {session}: {len(windows)} delivered windows, {len(speakers)} speakers\n")
    delivered = delivered_distribution(windows)
    print("delivered evidence share: " + ", ".join(
        f"{m}={delivered[m]:.3f}" for m in SCORED_MODALITIES) + "\n")

    # Repeats per candidate. temperature is 0 and the seed is fixed, so identical input
    # should give identical output; if it does not, a single measurement per candidate
    # cannot distinguish an ordering effect from run-to-run variation.
    repeats = int(os.environ.get("PROBE_REPEATS", "3"))
    results = []
    for name, order in CANDIDATE_ORDERS.items():
        blocks = "\n\n".join(render(w, "M", order=order) for w in windows)
        prompt = artifacts.template.format(
            duration_seconds=duration,
            speaker_list=json.dumps([{"speaker_id": s} for s in speakers], sort_keys=True),
            category_taxonomy=json.dumps([
                "patient_assessment", "procedural_skill", "communication",
                "team_coordination", "situational_awareness", "clinical_reasoning",
                "safety_behaviour",
            ]),
            window_blocks=blocks,
        )
        runs = []
        for attempt in range(repeats):
            try:
                raw = endpoint.complete(FocalRequest(
                    condition="M", prompt=prompt, runtime=runtime,
                    output_schema=artifacts.output_schema,
                ))
            except Exception as error:
                print(f"{name:18s} run {attempt} FAILED {type(error).__name__}: {str(error)[:90]}")
                continue
            cited, counts = cited_distribution(raw)
            try:
                moments = len(json.loads(raw).get("moments", []))
            except json.JSONDecodeError:
                moments = 0
            visual = cited["visual_scene"] + cited["visual_attention"]
            runs.append((_l1(cited, delivered), visual, moments, dict(counts)))
        if not runs:
            continue
        shares = [r[1] for r in runs]
        distance = sum(r[0] for r in runs) / len(runs)
        visual_share = sum(shares) / len(shares)
        results.append((name, distance, visual_share, runs[0][2], runs[0][3], len(prompt)))
        print(f"{name:18s} chars {len(prompt):6d} mean L1 {distance:.3f} "
              f"visual_share mean {visual_share:.3f} range [{min(shares):.3f},{max(shares):.3f}] "
              f"per-run cited {[r[3] for r in runs]}")

    if not results:
        print("\nno candidate completed")
        return 1

    # Pre-declared rule: smallest L1 between cited and delivered distributions.
    # Ties break by the candidate order declared in the protocol, which favours the
    # status quo; `results` is already in that order.
    best = min(results, key=lambda row: row[1])
    shares = [row[2] for row in results]
    spread = max(shares) - min(shares)
    print(f"\nSELECTED by pre-declared rule: {best[0]} (L1 {best[1]:.3f})")
    print(f"visual-share spread across candidates: {spread:.3f} "
          f"({'report sensitivity' if spread > 0.10 else 'below the 10pp reporting threshold'})")


if __name__ == "__main__":
    raise SystemExit(main())
