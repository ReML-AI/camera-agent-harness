"""Exact five-field context assembly and symmetric T/M rendering."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

from scripts.core.errors import ContractError
from scripts.core.records import sha256_file
from scripts.core.schema import validate_record
from scripts.utils.session_paths import prerequisites_dir, processed_dir, raw_dir


SEMANTIC_FIELDS = (
    "transcript",
    "speaker_dynamics",
    "visual_scene",
    "visual_attention",
    "modality_coverage",
)
VISUAL_FIELDS = ("visual_scene", "visual_attention")
ATTENTION_LABELS = ("patient", "person", "other")


def _overlaps(record: Mapping, start: float, end: float) -> bool:
    record_start = record.get("start_seconds", record.get("aligned_timestamp_seconds"))
    record_end = record.get("end_seconds", record_start)
    if record_start is None:
        return False
    if record_end == record_start:
        return start <= record_start < end
    return max(start, record_start) < min(end, record_end)


def _evidence_ids(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        evidence_id = value.get("evidence_id")
        if isinstance(evidence_id, str):
            found.append(evidence_id)
        for child in value.values():
            found.extend(_evidence_ids(child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            found.extend(_evidence_ids(child))
    return list(dict.fromkeys(found))


def _coverage_entry(value: Any, *, delivered: bool = True) -> dict:
    present = value is not None and value != [] and value != {}
    return {
        "present": present,
        "delivered": delivered,
        "evidence_ids": _evidence_ids(value) if delivered else [],
    }


def assemble_window(
    *,
    session_id: str,
    window_id: str,
    start_seconds: float,
    end_seconds: float,
    flag_ids: Sequence[str],
    transcript: Sequence[Mapping],
    speaker_dynamics: Mapping | None,
    visual_scene: Mapping | None,
    attention_records: Sequence[Mapping],
    attention_events: Sequence[Mapping],
    provenance: Mapping,
) -> dict:
    """Build one schema-valid context envelope with exactly five fields."""
    if start_seconds < 0 or end_seconds <= start_seconds:
        raise ContractError("context window must be a non-negative half-open interval")
    transcript_value = [dict(item) for item in transcript if _overlaps(item, start_seconds, end_seconds)]
    attention_value_records = [
        dict(item) for item in attention_records if _overlaps(item, start_seconds, end_seconds)
    ]
    attention_value_events = [
        dict(item) for item in attention_events if _overlaps(item, start_seconds, end_seconds)
    ]
    for event in attention_value_events:
        for field in ("label", "raw_label", "target", "from_target", "to_target"):
            if field in event and event[field] not in ATTENTION_LABELS:
                raise ContractError(
                    f"unsupported attention event {field}: {event[field]}"
                )
    counts = {label: 0 for label in ATTENTION_LABELS}
    for record in attention_value_records:
        label = record.get("label")
        if label not in counts:
            raise ContractError(f"unsupported attention label: {label}")
        counts[label] += 1
    total = sum(counts.values())
    visual_attention = None
    if attention_value_records or attention_value_events:
        visual_attention = {
            "labels": list(ATTENTION_LABELS),
            "distribution": {
                label: (counts[label] / total if total else 0.0) for label in ATTENTION_LABELS
            },
            "records": attention_value_records,
            "events": attention_value_events,
        }
    dynamics_value = dict(speaker_dynamics) if speaker_dynamics is not None else None
    scene_value = dict(visual_scene) if visual_scene is not None else None
    values = {
        "transcript": transcript_value,
        "speaker_dynamics": dynamics_value,
        "visual_scene": scene_value,
        "visual_attention": visual_attention,
    }
    coverage = {
        "evidence_id": f"coverage-{window_id}",
        **{
        name: _coverage_entry(value)
        for name, value in values.items()
        },
    }
    context = {**values, "modality_coverage": coverage}
    if tuple(context) != SEMANTIC_FIELDS:
        raise ContractError("context semantic fields are not in the canonical order")
    envelope = {
        "schema_version": "1.0.0",
        "window_id": window_id,
        "session_id": session_id,
        "start_seconds": start_seconds,
        "end_seconds": end_seconds,
        "flag_ids": list(flag_ids),
        "context": context,
        "provenance": dict(provenance),
    }
    validate_record("context_window", envelope)
    return envelope


def condition_context(window: Mapping, condition: str) -> dict:
    """Return delivered context for T or M without mutating extraction records."""
    if condition not in {"T", "M"}:
        raise ContractError("condition must be T or M")
    # Rendering is a contract boundary too: reject stale or hand-built contexts
    # windows even when they did not pass through ``assemble_window`` in this process.
    validate_record("context_window", dict(window))
    source = window["context"]
    delivered: dict[str, Any] = {}
    for field in SEMANTIC_FIELDS:
        if field == "modality_coverage":
            coverage = json.loads(json.dumps(source[field]))
            if condition == "T":
                for visual in VISUAL_FIELDS:
                    coverage[visual] = {
                        "present": False,
                        "delivered": False,
                        "evidence_ids": [],
                    }
            delivered[field] = coverage
        elif condition == "T" and field in VISUAL_FIELDS:
            delivered[field] = "not available"
        else:
            delivered[field] = source[field] if source[field] is not None else "not available"
    return delivered


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# The fields of a transcript segment the model can actually reason over. WhisperX also
# emits per-word timings and score arrays, and the adapter adds canonical aliases beside
# the original keys; none of that is usable by a language model, but it was 87% of the
# rendered prompt. `evidence_id` is kept because returned moments are validated against it.
PROMPT_TRANSCRIPT_FIELDS = (
    "evidence_id",
    "speaker_id",
    "start_seconds",
    "end_seconds",
    "text",
)


def _prompt_transcript(segments: Any) -> Any:
    """Project transcript segments down to the fields the prompt needs.

    This narrows the PROMPT only — the window artifact keeps every field, so provenance and
    the evidence index are unaffected. Rendering the full segments put an 85,713-token prompt
    in front of a 32,768-token context, and the backend silently truncated it to the tail,
    dropping both the instructions and the earliest windows from what the model ever saw.
    """
    if not isinstance(segments, list):
        return segments
    projected = []
    for segment in segments:
        if not isinstance(segment, Mapping):
            return segments
        projected.append(
            {field: segment[field] for field in PROMPT_TRANSCRIPT_FIELDS if field in segment}
        )
    return projected


# What an attention record offers the model: which target, when, from which view, and an
# id it can cite. The rest of each record is calibration provenance -- assignment
# procedure, calibration session/version, angular distance, raw label -- repeated on every
# sample. On session_001 that made visual_attention 68,751 characters in a single window,
# larger than the whole focal budget, so windows carrying attention crowded out the rest of
# the session: delivery fell from 23 windows to 8 the moment attention started flowing.
PROMPT_ATTENTION_FIELDS = (
    "evidence_id",
    "aligned_timestamp_seconds",
    "label",
    # The identity contract declares attention evidence as (camera_id, track_id), and the
    # claim under test is speaker-anchored attention. Projecting track_id away left the
    # model reading "someone looked at the patient" with no way to say who, and left the
    # delivered record failing the contract its own audit asserts.
    "camera_id",
    "track_id",
)


def _prompt_attention(value: Any) -> Any:
    """Project attention records down to the fields the prompt needs.

    The window artifact keeps every field, so the evidence index and provenance audit are
    unaffected: this narrows only what is rendered into the prompt. The distribution and
    events are already compact and are passed through untouched.
    """
    if not isinstance(value, Mapping) or "records" not in value:
        return value
    records = value.get("records")
    if not isinstance(records, list):
        return value
    projected = []
    for record in records:
        if not isinstance(record, Mapping):
            return value
        projected.append(
            {field: record[field] for field in PROMPT_ATTENTION_FIELDS if field in record}
        )
    return {**value, "records": projected}


# Attention is sampled at the pose rate, giving ~110 records per 30-second window. The
# prompt is given roughly one per second instead: enough to locate when attention was on
# each target and to cite it, without spending most of the context budget on a
# finer-grained trace than the question needs. This is a REDUCTION IN RESOLUTION, not a
# lossless projection like the field narrowing above, so it is applied separately and the
# retained rate is stated here. The distribution is computed over all records upstream and
# is unaffected.
PROMPT_ATTENTION_RECORDS_PER_SECOND = 1.0


def _thin_attention_records(records: list, *, per_second: float) -> list:
    """Keep about `per_second` records per second, preferring the earliest in each bucket."""
    if per_second <= 0:
        return records
    kept, seen = [], set()
    for record in records:
        timestamp = record.get("aligned_timestamp_seconds")
        if not isinstance(timestamp, (int, float)):
            kept.append(record)
            continue
        bucket = int(float(timestamp) * per_second)
        if bucket in seen:
            continue
        seen.add(bucket)
        kept.append(record)
    return kept


def _prompt_coverage(coverage: Any) -> Any:
    """Report which modalities were delivered without re-listing every evidence id.

    Coverage recurses the whole window to collect ids, so it repeated all ~110 attention
    ids that already appear in the records themselves -- 22% of a rendered window for no
    information the model does not already have. The coverage entry's own id is kept so
    the coverage statement itself remains citable.
    """
    if not isinstance(coverage, Mapping):
        return coverage
    reduced = {}
    for key, value in coverage.items():
        if isinstance(value, Mapping) and "evidence_ids" in value:
            reduced[key] = {k: v for k, v in value.items() if k != "evidence_ids"}
        else:
            reduced[key] = value
    return reduced


# Order the five fields are RENDERED to the focal model. Distinct from SEMANTIC_FIELDS,
# which is the artifact's canonical order and a schema contract; only the presentation
# changes here.
#
# Selected by the field-order ablation. Field order proved material: with byte-identical
# prompt content and length, transcript-first produced no visual citations while
# visual-first produced a 0.267 visual share. The selected order is frozen for all nine
# sessions and is not re-selected per session.
PROMPT_FIELD_ORDER = (
    "visual_scene",
    "visual_attention",
    "transcript",
    "speaker_dynamics",
    "modality_coverage",
)


def prompt_delivered_context(window: Mapping, condition: str) -> dict:
    """The context as the focal model actually receives it, projections included.

    This is the single definition of "delivered". Rendering used to apply these
    projections inline while citation validation indexed the unprojected context, so an
    attention record dropped by the one-per-second thinning was absent from the prompt and
    still accepted as a resolved citation. Any consumer asking what reached the model must
    call this, never condition_context, or the two answers diverge again.
    """
    context = condition_context(window, condition)
    if isinstance(context.get("transcript"), list):
        context["transcript"] = _prompt_transcript(context["transcript"])
    if isinstance(context.get("visual_attention"), Mapping):
        attention = _prompt_attention(context["visual_attention"])
        if isinstance(attention.get("records"), list):
            attention = {
                **attention,
                "records": _thin_attention_records(
                    attention["records"],
                    per_second=PROMPT_ATTENTION_RECORDS_PER_SECOND,
                ),
            }
        context["visual_attention"] = attention
    if isinstance(context.get("modality_coverage"), Mapping):
        context["modality_coverage"] = _prompt_coverage(context["modality_coverage"])
    return context


def format_window_text(window: Mapping, *, condition: str) -> str:
    """Render the identical ordered five-heading template for T and M."""
    context = prompt_delivered_context(window, condition)
    lines = [
        f"Window ID: {window['window_id']}",
        f"Interval seconds: [{window['start_seconds']}, {window['end_seconds']})",
    ]
    headings = {
        "transcript": "Transcript",
        "speaker_dynamics": "Speaker dynamics",
        "visual_scene": "Visual scene",
        "visual_attention": "Visual attention",
        "modality_coverage": "Modality coverage",
    }
    for field in PROMPT_FIELD_ORDER:
        value = context[field]
        rendered = value if value == "not available" else _canonical(value)
        lines.append(f"{headings[field]}: {rendered}")
    return "\n".join(lines)


# Window geometry. The slide equals the window length, so windows tile the session
# without overlap. An earlier 15s slide overlapped adjacent windows by half, which
# doubled the transcript delivered to the focal model without adding information: under
# a fixed context budget that halved how much of the session could be shown at all.
# The cost is that a moment straddling a boundary is no longer presented whole to the
# model in one window.
WINDOW_SECONDS = 30.0
WINDOW_SLIDE_SECONDS = 30.0

# What the focal model can be given, expressed in characters so selection is exact and
# needs no tokenizer. The token budget is the model's 32,768-token context minus the
# 4,096 reserved for the completion; the ratio is measured on this pipeline's own
# prompts (227k characters rendered as 85,713 tokens) and rounded down to stay
# conservative. Overshooting is not a soft failure: the backend silently truncates the
# prompt tail, which is the defect this budget exists to prevent.
FOCAL_CONTEXT_TOKENS = 32768
FOCAL_RESERVED_OUTPUT_TOKENS = 4096
# 2.5 is below the 2.65 measured from Ollama running the actual Qwen2.5 tokenizer
# (227k characters reported as 85,713 prompt tokens), which is the only authoritative
# figure here. Do NOT raise this on the strength of a proxy tokenizer: cl100k_base scores
# the same content at 3.4 chars/token, which would suggest a third more room than Qwen
# actually has. Overshooting is not a soft failure -- the backend truncates the prompt
# tail silently, discarding the instructions.
FOCAL_CHARS_PER_TOKEN = 2.5
FOCAL_PROMPT_OVERHEAD_CHARS = 4000


def focal_window_budget_chars() -> int:
    """Characters of window content one focal prompt may carry."""
    usable = FOCAL_CONTEXT_TOKENS - FOCAL_RESERVED_OUTPUT_TOKENS
    return int(usable * FOCAL_CHARS_PER_TOKEN) - FOCAL_PROMPT_OVERHEAD_CHARS


def _window_priority(window: Mapping, flags_by_id: Mapping[str, object]) -> tuple:
    """Rank a window for delivery under a limited budget.

    Ordering, highest first: how many INDEPENDENT flag sources implicate the window,
    then how many of its contributions are critical, then the total contribution count,
    then earliest start. Preferring corroboration across independent sources is the
    harness's own logic -- a window that vitals, speech and vision all implicate is
    better evidence than one flagged many times by a single source, and vitals alone can
    emit hundreds of one-second flags in a deteriorating scenario.

    Start time breaks ties so the selection is deterministic and reproducible.
    """
    sources, criticals, total = set(), 0, 0
    start, end = window["start_seconds"], window["end_seconds"]
    for flag_id in window["flag_ids"]:
        flag = flags_by_id.get(flag_id)
        contributions = getattr(flag, "contributions", ()) if flag is not None else ()
        for contribution in contributions:
            # Fusion merges transitively, so one fused flag can span the whole session and
            # be referenced by every window. Counting all of its contributions everywhere
            # would rank every window identically; only those overlapping THIS window say
            # anything about it.
            first = getattr(contribution, "start_seconds", None)
            last = getattr(contribution, "end_seconds", None)
            if first is not None and last is not None:
                if not (max(float(first), start) < min(float(last), end)):
                    continue
            total += 1
            sources.add(getattr(contribution.source, "value", contribution.source))
            payload = contribution.payload or {}
            if payload.get("severity") == "critical":
                criticals += 1
    return (-len(sources), -criticals, -total, window["start_seconds"])


def select_windows_within_budget(
    windows: Sequence[Mapping],
    fused_flags: Sequence,
    *,
    budget_chars: int | None = None,
) -> tuple[list[dict], dict]:
    """Deliver the highest-priority windows that fit the focal context budget.

    Returns the delivered windows in session order plus an accounting record. Windows
    that do not fit are WITHHELD, not truncated: the backend would otherwise drop the
    prompt tail silently, which discards the instructions rather than the least
    important evidence. The accounting is reported so the funnel can state how much of
    the session reached the model.
    """
    budget = focal_window_budget_chars() if budget_chars is None else budget_chars
    flags_by_id = {flag.flag_id: flag for flag in fused_flags}
    ordered = sorted(windows, key=lambda window: _window_priority(window, flags_by_id))

    delivered, spent = [], 0
    withheld = []
    for window in ordered:
        cost = max(
            len(format_window_text(window, condition=condition)) for condition in ("T", "M")
        )
        if spent + cost <= budget:
            delivered.append(window)
            spent += cost
        else:
            withheld.append(window)

    delivered.sort(key=lambda window: window["start_seconds"])
    withheld.sort(key=lambda window: window["start_seconds"])
    accounting = {
        "policy_id": "FOCAL-WINDOW-BUDGET-001",
        "budget_chars": budget,
        "spent_chars": spent,
        "assembled_window_count": len(windows),
        "delivered_window_count": len(delivered),
        "withheld_window_count": len(withheld),
        "withheld_window_ids": [window["window_id"] for window in withheld],
        "delivered_seconds": sum(
            window["end_seconds"] - window["start_seconds"] for window in delivered
        ),
        "assembled_seconds": sum(
            window["end_seconds"] - window["start_seconds"] for window in windows
        ),
        "ranking": (
            "distinct flag sources, then critical contributions, then total "
            "contributions, then earliest start"
        ),
    }
    return delivered, accounting


def assemble_windows(
    *,
    session_id: str,
    session_end_seconds: float,
    fused_flags: Sequence,
    record_provider,
    provenance: Mapping,
) -> list[dict]:
    """Assemble fixed 30-second windows tiling the session without overlap.

    ``record_provider(start, end)`` supplies the five extracted semantic values.
    Only positive-duration intersections with fused flags are retained.
    """
    windows = []
    start = 0.0
    index = 0
    while start < session_end_seconds:
        end = min(start + WINDOW_SECONDS, session_end_seconds)
        matching = [
            flag.flag_id
            for flag in fused_flags
            if max(start, flag.start_seconds) < min(end, flag.end_seconds)
        ]
        if matching:
            values = record_provider(start, end)
            windows.append(
                assemble_window(
                    session_id=session_id,
                    window_id=f"window-{index:04d}",
                    start_seconds=start,
                    end_seconds=end,
                    flag_ids=matching,
                    provenance=provenance,
                    **values,
                )
            )
        start += WINDOW_SLIDE_SECONDS
        index += 1
    return windows


def _load_json_object(path: Path, description: str) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"required {description} artifact is missing: {path}")
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ContractError(f"{description} artifact must contain a JSON object: {path}")
    return value


def _number(record: Mapping, *names: str) -> float:
    for name in names:
        if record.get(name) is not None:
            return float(record[name])
    raise ContractError(f"record is missing required time field {names[0]}")


def _normalise_transcript(document: Mapping) -> list[dict]:
    segments = document.get("segments")
    if not isinstance(segments, list):
        raise ContractError("transcript artifact requires a segments array")
    output = []
    for index, source in enumerate(segments):
        if not isinstance(source, Mapping):
            raise ContractError("transcript segments must be objects")
        record = dict(source)
        record["start_seconds"] = _number(source, "start_seconds", "start")
        record["end_seconds"] = _number(source, "end_seconds", "end")
        record.setdefault(
            "evidence_id",
            str(source.get("transcript_segment_id") or f"transcript-{index:06d}"),
        )
        # Absent speaker is represented as absent. The previous default invented an
        # "UNKNOWN" speaker id that was delivered to the focal model as though
        # diarization had identified someone, and would be counted as a distinct
        # speaker by anything grouping on this field.
        speaker = source.get("speaker")
        if speaker is not None:
            record.setdefault("speaker_id", str(speaker))
        output.append(record)
    return output


def _normalise_attention(document: Mapping) -> list[dict]:
    if isinstance(document.get("attention"), list):
        candidates = document["attention"]
    else:
        tracks = document.get("tracks")
        if not isinstance(tracks, (dict, list)):
            raise ContractError("attention artifact requires attention records or tracks")
        track_values = tracks.values() if isinstance(tracks, dict) else tracks
        candidates = [
            pose
            for track in track_values
            if isinstance(track, Mapping)
            for pose in track.get("poses", track.get("frames", []))
        ]
    # Only the exact-frame-ASD-gated population is delivered. The declared method
    # propagates a visual signal solely from frames whose selected-view ASD score is
    # strictly positive; the ungated candidates stay in the gaze artifact as a named
    # diagnostic so the coverage the gate costs remains measurable, but they never reach a
    # window, a prompt or a citation. A record must carry an explicit verdict: admitting a
    # missing one is what let the gate ship as a no-op, because stage 9 computed the verdict
    # and dropped it before serialization, so every record arrived here with no field.
    candidates = [
        pose for pose in candidates
        if not isinstance(pose, Mapping)
        or pose.get("exact_frame_gate") == "exact_frame_asd_positive"
    ]
    records = []
    for source in candidates:
        if not isinstance(source, Mapping):
            raise ContractError("attention records must be objects")
        record = dict(source)
        label = record.get("label", record.get("gaze_target", record.get("target")))
        if label not in ATTENTION_LABELS:
            raise ContractError(f"unsupported attention label: {label}")
        record["label"] = label
        record["aligned_timestamp_seconds"] = _number(
            source, "aligned_timestamp_seconds", "timestamp"
        )
        records.append(record)
    return records


def _normalise_events(document: Mapping) -> list[dict]:
    values = document.get("events")
    if not isinstance(values, list):
        raise ContractError("attention-event artifact requires an events array")
    output = []
    for index, source in enumerate(values):
        if not isinstance(source, Mapping):
            raise ContractError("attention events must be objects")
        record = dict(source)
        start = _number(source, "start_seconds", "aligned_timestamp_seconds", "timestamp")
        record["start_seconds"] = start
        record["end_seconds"] = float(
            source.get("end_seconds", start + float(source.get("duration", 0.0)))
        )
        record.setdefault("evidence_id", f"attention-event-{index:06d}")
        output.append(record)
    return output


def _overlap_choice(records: Sequence[Mapping], start: float, end: float) -> dict | None:
    candidates = []
    for record in records:
        record_start = _number(record, "start_seconds", "start")
        record_end = _number(record, "end_seconds", "end")
        overlap = max(0.0, min(end, record_end) - max(start, record_start))
        if overlap > 0:
            candidates.append((overlap, record_start, dict(record)))
    return max(candidates, key=lambda item: (item[0], -item[1]))[2] if candidates else None


def _scene_with_evidence_id(scene: dict | None) -> dict | None:
    """Give the delivered scene a citable id.

    CLIP scene records carried no evidence_id, so modality_coverage reported the scene as
    present with an empty evidence id list: the channel was delivered to the model but
    could never be cited. That silently capped the cross-modal evidence metric, which
    counts moments citing a visual channel, at whatever attention alone could supply.
    The id is derived from the interval the scene describes so it is stable across runs.
    """
    if not isinstance(scene, Mapping) or "evidence_id" in scene:
        return scene
    start = scene.get("start_seconds", scene.get("start"))
    end = scene.get("end_seconds", scene.get("end"))
    if start is None or end is None:
        return scene
    record = {
        **scene,
        "evidence_id": f"scene-{float(start):09.3f}-{float(end):09.3f}".replace(".", "p"),
    }
    # The modality identity contract requires a camera_id for visual_scene. Scene records
    # name the chosen view "best_camera", so resolution read a null and failed validation
    # once these records became citable.
    if "camera_id" not in record and record.get("best_camera"):
        record["camera_id"] = record["best_camera"]
    return record


def assemble_session_windows(
    *,
    session_id: str,
    session_manifest_path: Path,
    transcript_path: Path,
    speaker_dynamics_path: Path,
    visual_scene_path: Path,
    attention_path: Path,
    attention_events_path: Path,
    fused_flags_path: Path,
    output_path: Path,
) -> dict:
    """Load required stage artifacts and write schema-valid selected windows."""
    session_manifest = _load_json_object(session_manifest_path, "session manifest")
    if session_manifest.get("session_id") != session_id:
        raise ContractError("session manifest belongs to a different session")
    session_end = float(session_manifest.get("session_end_seconds", 0))
    if session_end <= 0:
        raise ContractError("session manifest requires a positive session_end_seconds")

    transcript_document = _load_json_object(transcript_path, "transcript")
    dynamics_document = _load_json_object(speaker_dynamics_path, "speaker dynamics")
    scene_document = _load_json_object(visual_scene_path, "visual scene")
    attention_document = _load_json_object(attention_path, "attention")
    events_document = _load_json_object(attention_events_path, "attention events")
    flags_document = _load_json_object(fused_flags_path, "fused flags")
    if flags_document.get("source") != "fused" or flags_document.get("status") not in {
        "success_empty", "success_nonempty"
    }:
        raise ContractError("fused flag artifact is not a successful fused artifact")
    flag_values = flags_document.get("flags")
    if not isinstance(flag_values, list):
        raise ContractError("fused flag artifact requires a flags array")
    fused_flags = []
    for item in flag_values:
        if not isinstance(item, Mapping):
            raise ContractError("fused flags must be objects")
        # Contributions must survive the load. Without them every window scored
        # (0, 0, 0, start) and the ranking degenerated to chronological order while
        # still being described as corroboration-based.
        contributions = []
        for raw in item.get("contributions") or ():
            if not isinstance(raw, Mapping):
                continue
            contributions.append(SimpleNamespace(
                source=raw.get("source"),
                payload=raw.get("payload") or {},
                start_seconds=_number(raw, "start_seconds", "start"),
                end_seconds=_number(raw, "end_seconds", "end"),
            ))
        fused_flags.append(SimpleNamespace(
            flag_id=str(item["flag_id"]),
            start_seconds=float(item["start_seconds"]),
            end_seconds=float(item["end_seconds"]),
            contributions=contributions,
        ))

    transcript = _normalise_transcript(transcript_document)
    attention = _normalise_attention(attention_document)
    events = _normalise_events(events_document)
    dynamics = dynamics_document.get("windows")
    scenes = scene_document.get("scenes")
    if not isinstance(dynamics, list) or not isinstance(scenes, list):
        raise ContractError("speaker dynamics and visual scene artifacts require window arrays")

    source_paths = (
        session_manifest_path, transcript_path, speaker_dynamics_path, visual_scene_path,
        attention_path, attention_events_path, fused_flags_path,
    )
    provenance = {
        "source_artifacts": {
            path.name: sha256_file(path) for path in source_paths
        },
    }

    def provide(start: float, end: float) -> dict:
        return {
            "transcript": transcript,
            "speaker_dynamics": _overlap_choice(dynamics, start, end),
            "visual_scene": _scene_with_evidence_id(_overlap_choice(scenes, start, end)),
            "attention_records": attention,
            "attention_events": events,
        }

    windows = assemble_windows(
        session_id=session_id,
        session_end_seconds=session_end,
        fused_flags=fused_flags,
        record_provider=provide,
        provenance=provenance,
    )
    # Selection happens here, where the flag contributions that rank windows are already
    # loaded. Every assembled window is retained in the artifact; the accounting records
    # which of them the focal call may carry, so what was withheld stays auditable
    # instead of vanishing between stages.
    delivered, delivery = select_windows_within_budget(windows, fused_flags)
    artifact = {
        "schema_version": "1.0.0",
        "session_id": session_id,
        # The session's true synchronized span, from the manifest rather than from the
        # windows. Windows only exist where a flag landed, so a flagless tail makes the
        # assembled maximum shorter than the session and every consumer inherits that.
        "session_end_seconds": session_end,
        "window_duration_seconds": WINDOW_SECONDS,
        "slide_seconds": WINDOW_SLIDE_SECONDS,
        "windows": windows,
        "focal_delivery": {
            **delivery,
            "delivered_window_ids": [window["window_id"] for window in delivered],
        },
        "provenance": provenance,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output_path)
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--session-manifest", type=Path)
    parser.add_argument("--transcript", type=Path)
    parser.add_argument("--speaker-dynamics", type=Path)
    parser.add_argument("--visual-scene", type=Path)
    parser.add_argument("--attention", type=Path)
    parser.add_argument("--attention-events", type=Path)
    parser.add_argument("--fused-flags", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sid = args.session_id
    output = args.output or processed_dir(sid) / "multimodal_windows.json"
    assemble_session_windows(
        session_id=sid,
        session_manifest_path=(
            args.session_manifest or prerequisites_dir(sid) / "session_manifest.json"
        ),
        transcript_path=args.transcript or raw_dir(sid) / "diarized_transcript_full.json",
        speaker_dynamics_path=(
            args.speaker_dynamics or processed_dir(sid) / "speaker_dynamics.json"
        ),
        visual_scene_path=args.visual_scene or raw_dir(sid) / "clip_scene_descriptions.json",
        attention_path=args.attention or raw_dir(sid) / "gaze_tracks.json",
        attention_events_path=(
            args.attention_events or processed_dir(sid) / "gaze_events.json"
        ),
        fused_flags_path=args.fused_flags or processed_dir(sid) / "fused_flags.json",
        output_path=output,
    )
    print(output)
    return 0


__all__ = [
    "ATTENTION_LABELS",
    "SEMANTIC_FIELDS",
    "VISUAL_FIELDS",
    "assemble_window",
    "assemble_session_windows",
    "assemble_windows",
    "condition_context",
    "format_window_text",
]


if __name__ == "__main__":
    raise SystemExit(main())
