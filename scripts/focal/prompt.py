"""Checked prompt artifacts and symmetric condition rendering."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Mapping, Sequence

from scripts.analytics.assemble_multimodal_windows import format_window_text
from scripts.core.records import sha256_json


PROMPT_ROOT = Path(__file__).resolve().parents[2] / "prompts"


@dataclass(frozen=True)
class PromptArtifacts:
    template: str
    output_schema: dict
    template_sha256: str
    output_schema_sha256: str

    @classmethod
    def load(cls, root: Path = PROMPT_ROOT) -> "PromptArtifacts":
        template = (root / "system_prompt.txt").read_text(encoding="utf-8")
        output_schema = json.loads((root / "output_schema.json").read_text(encoding="utf-8"))
        return cls(
            template=template,
            output_schema=output_schema,
            template_sha256=sha256_json({"template": template}),
            output_schema_sha256=sha256_json(output_schema),
        )


def render_prompt(
    artifacts: PromptArtifacts,
    *,
    condition: str,
    windows: Sequence[Mapping],
    session_duration_seconds: float,
    speakers: Sequence[Mapping],
    category_taxonomy: Sequence[str],
) -> str:
    blocks = "\n\n".join(format_window_text(window, condition=condition) for window in windows)
    return artifacts.template.format(
        duration_seconds=session_duration_seconds,
        speaker_list=json.dumps(list(speakers), sort_keys=True, separators=(",", ":")),
        category_taxonomy=json.dumps(list(category_taxonomy), separators=(",", ":")),
        window_blocks=blocks,
    )
