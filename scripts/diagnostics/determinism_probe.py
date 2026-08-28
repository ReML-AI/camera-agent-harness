#!/usr/bin/env python3
"""Is the focal call deterministic, and does its position in the request sequence matter?

The pipeline issues T then M against one server process. If a call's output depends on
whether it ran first, request_order is a confound in the paper's central T/M comparison:
T would be measured cold and M warm, every time, in every session.

Two controls over one fixed prompt:
  repeat   the same prompt N times in one process
  first    the same prompt N times, each after a different preceding call

Reports whether responses are byte-identical, which temperature 0 with a fixed seed
should give.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.analytics.assemble_multimodal_windows import format_window_text  # noqa: E402
from scripts.focal.pipeline_stages import OpenAICompatibleEndpoint, _runtime  # noqa: E402
from scripts.focal.prompt import PromptArtifacts  # noqa: E402
from scripts.focal.runtime import FocalRequest  # noqa: E402

CATEGORIES = [
    "patient_assessment", "procedural_skill", "communication", "team_coordination",
    "situational_awareness", "clinical_reasoning", "safety_behaviour",
]


def build_prompt(artifacts, windows, condition, duration, speakers):
    blocks = "\n\n".join(format_window_text(w, condition=condition) for w in windows)
    return artifacts.template.format(
        duration_seconds=duration,
        speaker_list=json.dumps([{"speaker_id": s} for s in speakers], sort_keys=True),
        category_taxonomy=json.dumps(CATEGORIES),
        window_blocks=blocks,
    )


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def main():
    session = sys.argv[1] if len(sys.argv) > 1 else "session_001"
    repeats = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    doc = json.loads(
        (Path("data/sessions") / session / "processed" / "multimodal_windows.json").read_text()
    )
    delivered = set(doc["focal_delivery"]["delivered_window_ids"])
    windows = [w for w in doc["windows"] if w["window_id"] in delivered]
    duration = max(w["end_seconds"] for w in doc["windows"])
    speakers = sorted({
        s.get("speaker_id")
        for w in windows for s in (w["context"].get("transcript") or [])
        if isinstance(s, dict) and s.get("speaker_id")
    })

    artifacts = PromptArtifacts.load()
    runtime = _runtime(
        json.loads(Path("configs/focal_runtime_qwen2_5_7b_ollama_q4km.json").read_text())
    )
    endpoint = OpenAICompatibleEndpoint(
        base_url=os.environ.get("LLM_BASE_URL", "http://127.0.0.1:11434/v1"),
        api_key="ollama-local"
    )
    prompt_m = build_prompt(artifacts, windows, "M", duration, speakers)
    prompt_t = build_prompt(artifacts, windows, "T", duration, speakers)

    def call(prompt, condition):
        return endpoint.complete(FocalRequest(
            condition=condition, prompt=prompt, runtime=runtime,
            output_schema=artifacts.output_schema,
        ))

    print(f"{session}: {len(windows)} windows, prompt M {len(prompt_m)} chars\n")

    print(f"CONTROL 1 - same M prompt {repeats}x in sequence")
    seq = [digest(call(prompt_m, "M")) for _ in range(repeats)]
    for index, value in enumerate(seq):
        print(f"   call {index}: {value}")
    print(f"   identical: {len(set(seq)) == 1}   first differs from rest: "
          f"{seq[0] != seq[1] if len(seq) > 1 else 'n/a'}\n")

    print(f"CONTROL 2 - M preceded by T each time, {repeats}x (the pipeline's order)")
    after_t = []
    for _ in range(repeats):
        call(prompt_t, "T")
        after_t.append(digest(call(prompt_m, "M")))
    for index, value in enumerate(after_t):
        print(f"   call {index}: {value}")
    print(f"   identical: {len(set(after_t)) == 1}")

    print(f"\nM-cold digest {seq[0]}  vs  M-after-T digest {after_t[0]}: "
          f"{'SAME' if seq[0] == after_t[0] else 'DIFFERENT — request order affects output'}")


if __name__ == "__main__":
    raise SystemExit(main())
