"""K/T/M execution with symmetric T/M controls and strict JSON responses."""

from __future__ import annotations

import json
from typing import Mapping, Sequence

from scripts.core.errors import ContractError
from scripts.core.records import sha256_json
from scripts.core.schema import validate_record
from scripts.flags.keyword import KBaseline

from .evidence import validate_citations
from .prompt import PromptArtifacts, render_prompt
from .runtime import FocalEndpoint, FocalRequest, FocalRuntime


def _parse_response(raw: str, categories: set[str]) -> list[dict]:
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ContractError("focal endpoint returned invalid JSON") from exc
    if set(document) != {"moments"} or not isinstance(document["moments"], list):
        raise ContractError("focal response must contain exactly one moments array")
    moments = document["moments"]
    required = {
        "moment_id", "start_seconds", "end_seconds", "description",
        "clinical_significance", "category", "evidence_ids", "cross_modal_observations",
    }
    for moment in moments:
        if set(moment) != required:
            # Name offending fields so prompt and schema failures remain distinguishable.
            missing = sorted(required - set(moment))
            unsupported = sorted(set(moment) - required)
            raise ContractError(
                "focal moment has missing or unsupported fields: "
                f"missing={missing}, unsupported={unsupported}"
            )
        # Model-generated moment IDs may be quoted or numeric; normalize both forms.
        if isinstance(moment["moment_id"], (int, float)) and not isinstance(
            moment["moment_id"], bool
        ):
            moment["moment_id"] = str(moment["moment_id"])
        if not isinstance(moment["moment_id"], str) or not moment["moment_id"]:
            raise ContractError("focal moment_id must be a non-empty string or number")
        if moment["category"] not in categories:
            raise ContractError("focal moment category is outside the configured taxonomy")
        if moment["start_seconds"] < 0 or moment["end_seconds"] <= moment["start_seconds"]:
            raise ContractError("focal moment interval is invalid")
    return moments


def _counterbalanced_order(session_id: str, base_order):
    """Which condition is measured first, decided by session and fixed in advance.

    Deterministic in the session id so the assignment is reproducible and pre-declared
    rather than chosen per run, and so roughly half the cohort measures each condition
    first. Position therefore does not track condition across sessions.
    """
    from hashlib import sha256

    digest = sha256(session_id.encode("utf-8")).digest()[0]
    order = tuple(base_order)
    return order if digest % 2 == 0 else tuple(reversed(order))


def run_ktm(
    *,
    session_id: str,
    transcript: Sequence[Mapping],
    windows: Sequence[Mapping],
    session_duration_seconds: float,
    speakers: Sequence[Mapping],
    k_baseline: KBaseline,
    runtime: FocalRuntime,
    endpoint: FocalEndpoint,
    category_taxonomy: Sequence[str],
    prompt_artifacts: PromptArtifacts | None = None,
    delivered_artifact_sha256: str | None = None,
    paper_mode: bool = True,
) -> dict:
    if len(category_taxonomy) != 7 or len(set(category_taxonomy)) != 7:
        raise ContractError("focal category taxonomy must contain exactly seven unique labels")
    ordered_ids = [window["window_id"] for window in windows]
    if len(set(ordered_ids)) != len(ordered_ids):
        raise ContractError("ordered focal windows must have unique IDs")
    artifacts = prompt_artifacts or PromptArtifacts.load()
    k_output = k_baseline.run_artifact(session_id, transcript)
    validate_record("keyword_run", k_output)
    runs = {}
    # A freshly loaded server answers its FIRST request differently from every request
    # after it: measured on session_001, call 0 returns one digest and calls 1-3 return an
    # identical different one, at temperature 0 with a fixed seed.
    #
    # Holding the order fixed at ("T", "M") made that asymmetry CONSTANT, which is
    # reproducible but not attributable: T was always the cold call and M always the warm
    # one, so request position was perfectly confounded with condition and an M-T
    # difference could be a warm-state difference. Two changes remove the confound:
    #
    #   1. a discarded warm-up request, so neither measured call is the server's first;
    #   2. a per-session counterbalanced order, so position does not track condition
    #      across the cohort.
    #
    # The resolved order is recorded in each run's control manifest. Do not parallelise
    # these calls without re-running scripts/diagnostics/determinism_probe.py.
    warmup_prompt = render_prompt(
        artifacts,
        condition=runtime.request_order[0],
        windows=windows,
        session_duration_seconds=session_duration_seconds,
        speakers=speakers,
        category_taxonomy=category_taxonomy,
    )
    endpoint.complete(
        FocalRequest(
            condition=runtime.request_order[0],
            prompt=warmup_prompt,
            runtime=runtime,
            output_schema=artifacts.output_schema,
        )
    )
    measured_order = _counterbalanced_order(session_id, runtime.request_order)
    for condition in measured_order:
        prompt = render_prompt(
            artifacts,
            condition=condition,
            windows=windows,
            session_duration_seconds=session_duration_seconds,
            speakers=speakers,
            category_taxonomy=category_taxonomy,
        )
        raw = endpoint.complete(
            FocalRequest(
                condition=condition,
                prompt=prompt,
                runtime=runtime,
                output_schema=artifacts.output_schema,
            )
        )
        moments = _parse_response(raw, set(category_taxonomy))
        runs[condition] = {
            "schema_version": "1.1.0",
            "session_id": session_id,
            "condition": condition,
            "ordered_window_ids": ordered_ids,
            "control_manifest": {
                "prompt_template_sha256": artifacts.template_sha256,
                "output_schema_sha256": artifacts.output_schema_sha256,
                "runtime_sha256": runtime.sha256,
                "temperature": runtime.temperature,
                "json_mode": runtime.json_mode,
                "declared_request_order": list(runtime.request_order),
                "request_order": list(measured_order),
                "warmup_discarded": True,
            },
            "prompt_sha256": sha256_json({"prompt": prompt}),
            # The span the prompt actually stated. Without it the readiness check that
            # compares prompt span against assembled span has nothing to read and skips
            # silently, which is how a run once told the model 450s for a 960s session.
            "session_duration_seconds": session_duration_seconds,
            "runtime": runtime.to_dict(),
            "raw_response": raw,
            "raw_response_sha256": sha256_json({"response": raw}),
            "moments": validate_citations(
                moments,
                windows=windows,
                condition=condition,
                delivered_artifact_sha256=delivered_artifact_sha256,
            ),
        }
        validate_record("focal_run", runs[condition])
    if runs["T"]["ordered_window_ids"] != runs["M"]["ordered_window_ids"]:
        raise ContractError("T/M ordered window IDs diverged")
    if runs["T"]["control_manifest"] != runs["M"]["control_manifest"]:
        raise ContractError("T/M focal controls diverged")
    return {"session_id": session_id, "K": k_output, "T": runs["T"], "M": runs["M"]}
