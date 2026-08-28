"""Resolve and audit focal citations against the exact condition-delivered context."""

from __future__ import annotations

from copy import deepcopy
from math import isfinite
import re
from typing import Any, Mapping, Sequence

from scripts.analytics.assemble_multimodal_windows import (
    SEMANTIC_FIELDS,
    prompt_delivered_context,
)


PROVENANCE_INTEGRITY_DEFINITION_ID = "METRIC-T4-PROVENANCE-INTEGRITY-001"
TEMPORAL_RULE_ID = "PROVENANCE-TEMPORAL-HALF-OPEN-V1"
TEMPORAL_RULE = {
    "rule_id": TEMPORAL_RULE_ID,
    "moment_interval": "half_open_[start_seconds,end_seconds)",
    "positive_duration_evidence": (
        "require max(moment_start,evidence_start) < min(moment_end,evidence_end)"
    ),
    "point_evidence": "require moment_start <= aligned_timestamp_seconds < moment_end",
    "source_window_fallback": (
        "only evidence without item-local time may borrow its delivered source window; "
        "require strict positive-duration intersection with the moment"
    ),
    "boundary_touch": "not_an_intersection",
}

# These are the identities asserted by each producer contract.
MODALITY_IDENTITY_CONTRACT = {
    "transcript": (),
    "speaker_dynamics": (),
    "visual_scene": ("camera_id",),
    "visual_attention": ("camera_id", "track_id"),
    "modality_coverage": (),
}

_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_RESOLVED_EVIDENCE_FIELDS = (
    "evidence_id",
    "session_id",
    "modality",
    "window_id",
    "source_window_start_seconds",
    "source_window_end_seconds",
    "start_seconds",
    "end_seconds",
    "interval_basis",
    "camera_id",
    "track_id",
    "camera_ids",
    "person_ids",
    "source_artifact_sha256",
    "value",
)


def _valid_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _nonempty_id(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _nonempty_ids(value: object) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and bool(value)
        and all(_nonempty_id(item) for item in value)
    )


def _source_digest(window: Mapping, fallback: str | None) -> str | None:
    # The captured Stage-13 artifact is the exact payload delivered to Stage 14 and is
    # therefore the primary source identity. A window-local digest is compatibility
    # provenance for callers that do not have that artifact envelope.
    if _valid_sha256(fallback):
        return str(fallback)
    provenance = window.get("provenance")
    if isinstance(provenance, Mapping):
        direct = provenance.get("source_artifact_sha256")
        if _valid_sha256(direct):
            return str(direct)
    return None


def _time_fields(value: Mapping, window: Mapping) -> tuple[float, float, str]:
    raw_start = value.get("start_seconds")
    raw_end = value.get("end_seconds")
    if raw_start is not None and raw_end is not None:
        return float(raw_start), float(raw_end), "item_interval"
    point = value.get("aligned_timestamp_seconds")
    if point is not None:
        timestamp = float(point)
        return timestamp, timestamp, "item_point"
    return float(window["start_seconds"]), float(window["end_seconds"]), "source_window"


def _collect(
    value: Any,
    modality: str,
    window: Mapping,
    index: dict[str, list[dict]],
    *,
    delivered_artifact_sha256: str | None,
) -> None:
    if isinstance(value, Mapping):
        evidence_id = value.get("evidence_id")
        if isinstance(evidence_id, str):
            start, end, interval_basis = _time_fields(value, window)
            camera_id = value.get("camera_id", value.get("best_camera"))
            record = {
                "evidence_id": evidence_id,
                # Fall back to the window's session when the record does not carry one.
                # Scene records became citable only recently and never carried a session,
                # so resolution produced a null the focal_run schema types as a string.
                "session_id": value.get("session_id") or window.get("session_id"),
                "modality": modality,
                "window_id": window["window_id"],
                "source_window_start_seconds": window["start_seconds"],
                "source_window_end_seconds": window["end_seconds"],
                "start_seconds": start,
                "end_seconds": end,
                "interval_basis": interval_basis,
                "camera_id": camera_id,
                "track_id": value.get("track_id"),
                "camera_ids": deepcopy(value.get("camera_ids")),
                "person_ids": deepcopy(value.get("person_ids")),
                # The Stage-13 artifact is the direct source delivered to the focal model.
                # Older/synthetic envelopes may instead carry one explicit source digest.
                "source_artifact_sha256": (
                    value.get("source_artifact_sha256")
                    if _valid_sha256(value.get("source_artifact_sha256"))
                    else _source_digest(window, delivered_artifact_sha256)
                ),
                "value": deepcopy(value),
            }
            index.setdefault(evidence_id, []).append(record)
        for child in value.values():
            _collect(
                child,
                modality,
                window,
                index,
                delivered_artifact_sha256=delivered_artifact_sha256,
            )
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            _collect(
                child,
                modality,
                window,
                index,
                delivered_artifact_sha256=delivered_artifact_sha256,
            )


def delivered_evidence_occurrences(
    windows: Sequence[Mapping],
    condition: str,
    *,
    delivered_artifact_sha256: str | None = None,
) -> dict[str, list[dict]]:
    """Return every delivered occurrence; repeated sliding-window IDs are preserved."""
    index: dict[str, list[dict]] = {}
    for window in windows:
        context = prompt_delivered_context(window, condition)
        for modality in SEMANTIC_FIELDS:
            if context[modality] != "not available":
                _collect(
                    context[modality],
                    modality,
                    window,
                    index,
                    delivered_artifact_sha256=delivered_artifact_sha256,
                )
        coverage_id = f"coverage-{window['window_id']}"
        if coverage_id in index:
            continue
        index.setdefault(coverage_id, []).append({
            "evidence_id": coverage_id,
            "session_id": window.get("session_id"),
            "modality": "modality_coverage",
            "window_id": window["window_id"],
            "source_window_start_seconds": window["start_seconds"],
            "source_window_end_seconds": window["end_seconds"],
            "start_seconds": window["start_seconds"],
            "end_seconds": window["end_seconds"],
            "interval_basis": "source_window",
            "camera_id": None,
            "track_id": None,
            "camera_ids": None,
            "person_ids": None,
            "source_artifact_sha256": _source_digest(window, delivered_artifact_sha256),
            "value": deepcopy(context["modality_coverage"]),
        })
    return index


def delivered_evidence_index(
    windows: Sequence[Mapping],
    condition: str,
    *,
    delivered_artifact_sha256: str | None = None,
) -> dict[str, dict]:
    """Compatibility view selecting the first ordered delivered occurrence per ID."""
    occurrences = delivered_evidence_occurrences(
        windows, condition, delivered_artifact_sha256=delivered_artifact_sha256
    )
    return {evidence_id: records[0] for evidence_id, records in occurrences.items()}


def validate_citations(
    moments: Sequence[Mapping],
    *,
    windows: Sequence[Mapping],
    condition: str,
    delivered_artifact_sha256: str | None = None,
) -> list[dict]:
    """Attach condition-specific resolutions; unresolved IDs remain explicit."""
    index = delivered_evidence_index(
        windows, condition, delivered_artifact_sha256=delivered_artifact_sha256
    )
    validated = []
    for moment in moments:
        copied = deepcopy(dict(moment))
        resolved = []
        invalid = []
        evidence_ids = moment.get("evidence_ids", [])
        if not isinstance(evidence_ids, Sequence) or isinstance(evidence_ids, (str, bytes)):
            evidence_ids = []
        for evidence_id in evidence_ids:
            if evidence_id in index:
                # Persist the resolution envelope, including the Stage-13 session and
                # artifact identity, rather than relying on the nested evidence value to
                # retain provenance. ``dict.get`` deliberately records a genuinely absent
                # digest as null; citation validation must never invent one.
                resolution = index[evidence_id]
                resolved.append({
                    field: deepcopy(resolution.get(field))
                    for field in _RESOLVED_EVIDENCE_FIELDS
                })
            else:
                invalid.append(evidence_id)
        copied["resolved_evidence"] = resolved
        copied["invalid_evidence_ids"] = invalid
        copied["citations_valid"] = not invalid
        validated.append(copied)
    return validated


def _finite_number(value: object) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if isfinite(numeric) else None


def _valid_moment_interval(moment: Mapping) -> tuple[float, float] | None:
    start = _finite_number(moment.get("start_seconds"))
    end = _finite_number(moment.get("end_seconds"))
    if start is None or end is None or start < 0 or end <= start:
        return None
    return start, end


def _delivering_window_interval(item: Mapping) -> dict[str, float] | None:
    """The span of the window that delivered this evidence, shaped for `_temporal_match`."""
    start = _finite_number(item.get("source_window_start_seconds"))
    end = _finite_number(item.get("source_window_end_seconds"))
    if start is None or end is None or end <= start:
        return None
    return {"start_seconds": start, "end_seconds": end}


def _temporal_match(moment_interval: tuple[float, float], item: Mapping) -> bool:
    moment_start, moment_end = moment_interval
    start = _finite_number(item.get("start_seconds"))
    end = _finite_number(item.get("end_seconds"))
    basis = item.get("interval_basis")
    if start is None or end is None:
        return False
    if basis == "item_point" or start == end:
        return moment_start <= start < moment_end
    if end <= start:
        return False
    return max(moment_start, start) < min(moment_end, end)


def _item_core_violations(
    item: Mapping, *, session_id: str, allowed_digests: set[str]
) -> list[str]:
    violations = []
    if item.get("session_id") != session_id:
        violations.append("resolved_item_session_missing_or_mismatch")
    if item.get("modality") not in MODALITY_IDENTITY_CONTRACT:
        violations.append("resolved_item_modality_missing_or_unknown")
    start = _finite_number(item.get("start_seconds"))
    end = _finite_number(item.get("end_seconds"))
    if start is None or end is None or start < 0 or end < start:
        violations.append("resolved_item_interval_missing_or_invalid")
    digest = item.get("source_artifact_sha256")
    if not _valid_sha256(digest):
        violations.append("resolved_item_source_digest_missing_or_invalid")
    elif allowed_digests and digest not in allowed_digests:
        violations.append("resolved_item_source_digest_not_delivered")
    return violations


def _identity_violations(item: Mapping) -> list[str]:
    modality = item.get("modality")
    required = MODALITY_IDENTITY_CONTRACT.get(modality, ())
    violations = []
    for field in required:
        value = item.get(field)
        valid = _nonempty_ids(value) if field.endswith("_ids") else _nonempty_id(value)
        if not valid:
            violations.append(f"required_{field}_missing")
    return violations


def _matches_delivered_occurrence(item: Mapping, occurrence: Mapping) -> bool:
    fields = (
        "evidence_id", "session_id", "modality", "window_id",
        "source_window_start_seconds", "source_window_end_seconds",
        "start_seconds", "end_seconds", "interval_basis", "camera_id", "track_id",
        "camera_ids", "person_ids", "source_artifact_sha256",
    )
    return all(item.get(field) == occurrence.get(field) for field in fields)


def audit_provenance_integrity(
    *,
    session_id: str,
    focal_runs: Mapping[str, object],
    windows: Sequence[Mapping],
    delivered_artifact_sha256: str,
) -> dict:
    """Exhaustively audit every T/M detection without excluding malformed moments.

    Integrity failures are measured results. A caller should fail only when the required
    Stage-13/14 artifacts themselves are absent or cannot be interpreted as collections.
    """
    if not _valid_sha256(delivered_artifact_sha256):
        raise ValueError("provenance audit requires the captured Stage-13 artifact SHA-256")
    if any(not isinstance(window, Mapping) for window in windows):
        raise ValueError("provenance audit windows must contain mappings")

    allowed_digests = {delivered_artifact_sha256}
    for window in windows:
        provenance = window.get("provenance")
        if isinstance(provenance, Mapping):
            direct = provenance.get("source_artifact_sha256")
            if _valid_sha256(direct):
                allowed_digests.add(str(direct))
            sources = provenance.get("source_artifacts")
            if isinstance(sources, Mapping):
                allowed_digests.update(
                    str(value) for value in sources.values() if _valid_sha256(value)
                )

    condition_results: dict[str, dict] = {}
    all_moment_results: list[dict] = []
    total_keys = (
        "moment_count", "citation_count", "delivered_resolved_citation_count",
        "undelivered_citation_count", "stored_resolution_match_count",
        "stored_resolution_mismatch_count", "resolved_item_count",
        "complete_provenance_item_count", "incomplete_provenance_item_count",
        "resolved_item_session_complete_count", "resolved_item_interval_complete_count",
        "resolved_item_modality_complete_count",
        "resolved_item_source_digest_complete_count",
        "identity_required_item_count", "identity_complete_item_count",
        "identity_incomplete_item_count", "temporally_valid_citation_count",
        "citation_timing_not_evaluable_count",
        "citation_within_delivering_window_count",
        "temporally_invalid_citation_count", "valid_complete_moment_count",
        "invalid_or_incomplete_moment_count",
    )

    for condition in ("T", "M"):
        run = focal_runs.get(condition)
        if not isinstance(run, Mapping):
            raise ValueError(f"provenance audit is missing the {condition} focal run")
        if run.get("session_id") != session_id or run.get("condition") != condition:
            raise ValueError(f"provenance audit {condition} run has wrong session/condition")
        moments = run.get("moments")
        if not isinstance(moments, Sequence) or isinstance(moments, (str, bytes)):
            raise ValueError(f"provenance audit {condition} run requires a moments array")
        if any(not isinstance(moment, Mapping) for moment in moments):
            raise ValueError(f"provenance audit {condition} moments must contain mappings")

        delivered = delivered_evidence_occurrences(
            windows,
            condition,
            delivered_artifact_sha256=delivered_artifact_sha256,
        )
        counts = {key: 0 for key in total_keys}
        counts["moment_count"] = len(moments)
        condition_moment_results = []
        seen_moment_ids: set[str] = set()
        for index, moment in enumerate(moments):
            raw_id = moment.get("moment_id")
            moment_id = raw_id if _nonempty_id(raw_id) else f"<missing:{condition}:{index}>"
            violations: list[str] = []
            offending_ids: dict[str, list[str]] = {}
            if not _nonempty_id(raw_id):
                violations.append("moment_id_missing")
            elif moment_id in seen_moment_ids:
                violations.append("duplicate_moment_id")
            seen_moment_ids.add(str(moment_id))
            moment_interval = _valid_moment_interval(moment)
            if moment_interval is None:
                violations.append("moment_interval_missing_or_invalid")

            evidence_ids = moment.get("evidence_ids")
            if not isinstance(evidence_ids, Sequence) or isinstance(evidence_ids, (str, bytes)):
                evidence_ids = []
                violations.append("evidence_ids_missing_or_invalid")
            cited_ids = list(evidence_ids)
            counts["citation_count"] += len(cited_ids)
            if not cited_ids:
                violations.append("no_evidence_citations")
            if len(set(map(str, cited_ids))) != len(cited_ids):
                violations.append("duplicate_evidence_citation")

            resolved_items = moment.get("resolved_evidence")
            if not isinstance(resolved_items, Sequence) or isinstance(resolved_items, (str, bytes)):
                resolved_items = []
                violations.append("resolved_evidence_missing_or_invalid")
            resolved_by_id: dict[object, list[Mapping]] = {}
            for item in resolved_items:
                if not isinstance(item, Mapping):
                    violations.append("resolved_evidence_contains_non_object")
                    continue
                resolved_by_id.setdefault(item.get("evidence_id"), []).append(item)
                counts["resolved_item_count"] += 1
                core = _item_core_violations(
                    item, session_id=session_id, allowed_digests=allowed_digests
                )
                identity = _identity_violations(item)
                if MODALITY_IDENTITY_CONTRACT.get(item.get("modality"), ()):
                    counts["identity_required_item_count"] += 1
                    if identity:
                        counts["identity_incomplete_item_count"] += 1
                    else:
                        counts["identity_complete_item_count"] += 1
                if core:
                    counts["incomplete_provenance_item_count"] += 1
                else:
                    counts["complete_provenance_item_count"] += 1
                if "resolved_item_session_missing_or_mismatch" not in core:
                    counts["resolved_item_session_complete_count"] += 1
                if "resolved_item_interval_missing_or_invalid" not in core:
                    counts["resolved_item_interval_complete_count"] += 1
                if "resolved_item_modality_missing_or_unknown" not in core:
                    counts["resolved_item_modality_complete_count"] += 1
                if not {
                    "resolved_item_source_digest_missing_or_invalid",
                    "resolved_item_source_digest_not_delivered",
                } & set(core):
                    counts["resolved_item_source_digest_complete_count"] += 1
                violations.extend(core)
                violations.extend(identity)

            undelivered: list[str] = []
            temporal_invalid: list[str] = []
            missing_stored_resolution: list[str] = []
            mismatched_stored_resolution: list[str] = []
            for evidence_id in cited_ids:
                occurrences = delivered.get(evidence_id, [])
                if occurrences:
                    counts["delivered_resolved_citation_count"] += 1
                else:
                    counts["undelivered_citation_count"] += 1
                    undelivered.append(str(evidence_id))
                stored = resolved_by_id.get(evidence_id, [])
                if not stored:
                    missing_stored_resolution.append(str(evidence_id))
                matching_occurrences = [
                    occurrence for occurrence in occurrences
                    if any(_matches_delivered_occurrence(item, occurrence) for item in stored)
                ]
                if matching_occurrences:
                    counts["stored_resolution_match_count"] += 1
                else:
                    counts["stored_resolution_mismatch_count"] += 1
                    if stored:
                        mismatched_stored_resolution.append(str(evidence_id))
                # The strict rule — evidence must meet the moment's own reported interval —
                # is the one reported as temporal validity, because it is the only one that
                # can fail informatively. Moments come back aligned to the 15s window slide
                # while windows span 30s, so a moment reported as [15,30) is routinely
                # grounded in evidence drawn from its 30s source window [15,45): counting
                # those as valid would put this metric at ~100% by construction and measure
                # nothing. Falling outside the reported interval is a real property of the
                # output and is what this number is for.
                within_moment = moment_interval is not None and occurrences and any(
                    _temporal_match(moment_interval, occurrence)
                    for occurrence in occurrences
                )
                # Recorded separately: whether the citation at least came from a window
                # overlapping the moment. Near-vacuous on its own, but it distinguishes "cited
                # loosely inside what was delivered" from "cited something unrelated", which
                # the strict count alone cannot separate.
                within_delivering_window = moment_interval is not None and occurrences and any(
                    _temporal_match(moment_interval, window)
                    for window in map(_delivering_window_interval, occurrences)
                    if window is not None
                )
                if within_delivering_window:
                    counts["citation_within_delivering_window_count"] += 1
                # An undelivered citation has no occurrence to compare against, so its
                # timing cannot be evaluated at all. Counting it invalid conflated
                # fabrication with mistiming and inflated the published "outside the moment
                # interval" rate by exactly the undelivered count.
                if not occurrences:
                    counts["citation_timing_not_evaluable_count"] += 1
                elif within_moment:
                    counts["temporally_valid_citation_count"] += 1
                else:
                    counts["temporally_invalid_citation_count"] += 1
                    temporal_invalid.append(str(evidence_id))
            if undelivered:
                violations.append("citation_not_delivered_to_condition")
                offending_ids["undelivered_evidence_ids"] = undelivered
            if missing_stored_resolution:
                violations.append("citation_missing_stored_resolution")
                offending_ids["missing_stored_resolution_ids"] = missing_stored_resolution
            if mismatched_stored_resolution:
                violations.append("stored_resolution_differs_from_delivered_evidence")
                offending_ids["mismatched_stored_resolution_ids"] = (
                    mismatched_stored_resolution
                )
            if temporal_invalid:
                violations.append("citation_temporal_rule_failed")
                offending_ids["temporally_invalid_evidence_ids"] = temporal_invalid

            declared_invalid = moment.get("invalid_evidence_ids")
            if not isinstance(declared_invalid, Sequence) or isinstance(
                declared_invalid, (str, bytes)
            ) or list(declared_invalid) != undelivered:
                violations.append("invalid_evidence_ids_inconsistent")
            expected_citations_valid = not undelivered
            if moment.get("citations_valid") is not expected_citations_valid:
                violations.append("citations_valid_inconsistent")

            # A stored resolution that was not one of this moment's cited, delivered IDs is
            # provenance inflation and is therefore listed too.
            extra_resolved = sorted(
                str(evidence_id) for evidence_id in resolved_by_id
                if evidence_id not in cited_ids or evidence_id not in delivered
            )
            if extra_resolved:
                violations.append("resolved_item_not_cited_and_delivered")
                offending_ids["extra_resolved_evidence_ids"] = extra_resolved

            unique_violations = list(dict.fromkeys(violations))
            complete = not unique_violations
            counts[
                "valid_complete_moment_count" if complete
                else "invalid_or_incomplete_moment_count"
            ] += 1
            result = {
                "session_id": session_id,
                "condition": condition,
                "moment_id": moment_id,
                "moment_index": index,
                "citation_count": len(cited_ids),
                "resolved_item_count": sum(len(items) for items in resolved_by_id.values()),
                "integrity_complete": complete,
                "violation_codes": unique_violations,
                **offending_ids,
            }
            condition_moment_results.append(result)
            all_moment_results.append(result)

        condition_results[condition] = {
            **counts,
            "invalid_or_incomplete_moment_ids": [
                result["moment_id"] for result in condition_moment_results
                if not result["integrity_complete"]
            ],
            "moment_results": condition_moment_results,
        }

    totals = {
        key: sum(condition_results[condition][key] for condition in ("T", "M"))
        for key in total_keys
    }
    invalid_ids = [
        f"{item['condition']}:{item['moment_id']}"
        for item in all_moment_results if not item["integrity_complete"]
    ]
    return {
        "definition_id": PROVENANCE_INTEGRITY_DEFINITION_ID,
        "status": "measured",
        "integrity_status": "passed" if not invalid_ids else "violations_detected",
        "session_id": session_id,
        "audited_conditions": ["T", "M"],
        "temporal_rule": dict(TEMPORAL_RULE),
        "modality_identity_contract": {
            modality: list(fields)
            for modality, fields in MODALITY_IDENTITY_CONTRACT.items()
        },
        "delivered_context_artifact_sha256": delivered_artifact_sha256,
        "allowed_source_artifact_sha256": sorted(allowed_digests),
        "counts": totals,
        "invalid_or_incomplete_moment_ids": invalid_ids,
        "conditions": condition_results,
    }


__all__ = [
    "MODALITY_IDENTITY_CONTRACT",
    "PROVENANCE_INTEGRITY_DEFINITION_ID",
    "TEMPORAL_RULE",
    "TEMPORAL_RULE_ID",
    "audit_provenance_integrity",
    "delivered_evidence_index",
    "delivered_evidence_occurrences",
    "validate_citations",
]
