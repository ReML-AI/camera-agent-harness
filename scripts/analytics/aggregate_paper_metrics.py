#!/usr/bin/env python3
"""Aggregate exactly the retained paper metrics and fail closed on incomplete cohorts."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from decimal import Decimal, ROUND_HALF_UP
import json
from math import sqrt
from pathlib import Path
import sys
from typing import Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.focal.pipeline_stages import FOCAL_CATEGORIES
from scripts.metrics.definitions import (
    AggregateMetric,
    CountRate,
    HARNESS_FUNNEL_SIGNALS,
    HARNESS_FUNNEL_TRANSITIONS,
    HARNESS_WITHHOLDING_REASONS,
    compute_attention_context_coverage,
    compute_camera_selection_distribution,
    compute_category_diversity,
    compute_directional_overlap,
    compute_moment_counts,
    compute_participant_counts,
    compute_scenario_distribution,
    compute_scene_context_coverage,
    compute_session_count,
    compute_session_durations,
    compute_table3_absolute_percentage_point_gap,
    compute_table3_ratio,
    compute_transcript_context_coverage,
    compute_wilcoxon_signed_rank,
)


PRODUCER_VERSION = "3.1.0"
EXPECTED_SESSION_COUNT = 9
SIGNALS = ("asd", "face", "head_pose")
COLUMNS = ("best_cam", "union", "selected")
BASE_QUANTITY_IDS = (
    *(f"table3.{signal}.{column}" for signal in SIGNALS for column in COLUMNS),
    "speaker_identity_link",
    "tm_overlap",
    "m_only_count",
    "m_only_cross_modal_evidence",
    "aggregate_cross_modal_evidence",
    "provenance_integrity",
    "evidence_distribution",
    "attention_distribution",
    "example_silence",
    "moment_counts",
    "category_diversity",
    "directional_overlap",
    "camera_selection_distribution",
    "transcript_context_coverage",
    "scene_context_coverage",
    "attention_context_coverage",
    "wilcoxon_signed_rank",
    "session_count",
    "scenario_distribution",
    "session_durations",
    "participant_counts",
    "table3_ratio",
    "harness_delivery_failure_funnel",
)
TABLE3_GAP_COMPARISONS = {
    "union_minus_best_cam": ("union", "best_cam"),
    "selected_minus_best_cam": ("selected", "best_cam"),
    "union_minus_selected": ("union", "selected"),
}
TABLE3_GAP_QUANTITY_DEPENDENCIES = {
    f"table3.{signal}.gap.{comparison}": (
        f"table3.{signal}.{minuend}", f"table3.{signal}.{subtrahend}"
    )
    for signal in SIGNALS
    for comparison, (minuend, subtrahend) in TABLE3_GAP_COMPARISONS.items()
}
QUANTITY_IDS = (*BASE_QUANTITY_IDS, *TABLE3_GAP_QUANTITY_DEPENDENCIES)


class MetricsValidationError(ValueError):
    """A hard cohort-validation failure carrying the machine-readable partial report."""

    def __init__(self, report: dict):
        self.report = report
        failures = report.get("validation", {}).get("failures", [])
        super().__init__("paper metrics validation failed: " + "; ".join(map(str, failures)))


def _sample_std(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _percent(value: float | None) -> str | None:
    if value is None:
        return None
    return format(
        Decimal(str(value * 100)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), "f"
    )


def _aggregate_rate(
    records: Sequence[tuple[str, Mapping[str, object]]],
    *,
    denominator_unit: str,
    expected_session_count: int,
) -> dict:
    units: list[dict] = []
    unavailable: list[str] = []
    values: list[float] = []
    for session_id, record in records:
        numerator = record.get("numerator")
        denominator = record.get("denominator")
        value = record.get("value")
        if (
            record.get("status", "measured") != "measured"
            or not isinstance(numerator, int)
            or not isinstance(denominator, int)
            or denominator < 1
        ):
            unavailable.append(session_id)
            continue
        expected = numerator / denominator
        if not isinstance(value, (int, float)) or abs(float(value) - expected) > 1e-12:
            raise ValueError(f"rate/count mismatch for {session_id}")
        unit = {
            "session_id": session_id,
            "numerator": numerator,
            "denominator": denominator,
            "denominator_unit": denominator_unit,
            "value": expected,
        }
        excluded_ids = record.get("excluded_moment_ids")
        if isinstance(excluded_ids, Sequence) and not isinstance(excluded_ids, (str, bytes)):
            unit["excluded_moment_ids"] = list(excluded_ids)
            unit["excluded_moment_count"] = len(excluded_ids)
        if isinstance(record.get("camera_id"), str):
            unit["camera_id"] = record["camera_id"]
        units.append(unit)
        values.append(expected)
    mean = sum(values) / len(values) if values else None
    standard_deviation = _sample_std(values)
    total_numerator = sum(unit["numerator"] for unit in units)
    total_denominator = sum(unit["denominator"] for unit in units)
    return {
        "status": "measured" if len(units) == expected_session_count else "incomplete",
        "denominator_statement": (
            f"mean/sample_std: one {denominator_unit} rate per complete session; "
            f"cohort_rate: pooled {denominator_unit} counts"
        ),
        "units": units,
        "expected_session_count": expected_session_count,
        "contributing_session_count": len(units),
        "noncontributing_session_count": len(unavailable),
        "noncontributing_session_ids": unavailable,
        "aggregation": "unweighted_mean_of_session_rates",
        "aggregation_trace": [unit["session_id"] for unit in units],
        "n": len(units),
        "mean": mean,
        "sample_std": standard_deviation,
        "rendered_percent_mean": _percent(mean),
        "rendered_percent_sample_std": _percent(standard_deviation),
        "cohort_numerator": total_numerator,
        "cohort_denominator": total_denominator,
        "cohort_denominator_unit": denominator_unit,
        "cohort_rate": total_numerator / total_denominator if total_denominator else None,
        "rendered_percent_cohort_rate": _percent(
            total_numerator / total_denominator if total_denominator else None
        ),
    }


def _aggregate_overlap(
    records: Sequence[tuple[str, Mapping[str, object]]], *, expected_session_count: int
) -> dict:
    units: list[dict] = []
    unavailable: list[str] = []
    for session_id, record in records:
        forward = record.get("t_to_m")
        reverse = record.get("m_to_t")
        value = record.get("value")
        if (
            record.get("status") != "measured"
            or not isinstance(value, (int, float))
            or not isinstance(forward, Mapping)
            or not isinstance(reverse, Mapping)
        ):
            unavailable.append(session_id)
            continue
        directions = []
        for direction, item, denominator_unit in (
            ("T_to_M", forward, "T_moments"), ("M_to_T", reverse, "M_moments")
        ):
            numerator = item.get("numerator")
            denominator = item.get("denominator")
            directional_value = item.get("value")
            if (
                not isinstance(numerator, int) or not isinstance(denominator, int)
                or denominator < 1 or not isinstance(directional_value, (int, float))
                or abs(float(directional_value) - numerator / denominator) > 1e-12
            ):
                unavailable.append(session_id)
                directions = []
                break
            directions.append({
                "direction": direction, "numerator": numerator, "denominator": denominator,
                "denominator_unit": denominator_unit, "value": numerator / denominator,
            })
        if not directions:
            continue
        expected_value = (directions[0]["value"] + directions[1]["value"]) / 2
        if abs(float(value) - expected_value) > 1e-12:
            raise ValueError(f"symmetric overlap mismatch for {session_id}")
        units.append({"session_id": session_id, "value": expected_value, "directions": directions})
    values = [unit["value"] for unit in units]
    forward_numerator = sum(unit["directions"][0]["numerator"] for unit in units)
    forward_denominator = sum(unit["directions"][0]["denominator"] for unit in units)
    reverse_numerator = sum(unit["directions"][1]["numerator"] for unit in units)
    reverse_denominator = sum(unit["directions"][1]["denominator"] for unit in units)
    cohort_value = None
    if forward_denominator and reverse_denominator:
        cohort_value = (
            forward_numerator / forward_denominator + reverse_numerator / reverse_denominator
        ) / 2
    missing = sorted(set(unavailable))
    mean = sum(values) / len(values) if values else None
    std = _sample_std(values)
    return {
        "status": "measured" if len(units) == expected_session_count else "incomplete",
        "denominator_statement": (
            "each session value is the arithmetic mean of T-moment and M-moment directional "
            "overlap rates; cohort_value pools each direction before the same arithmetic mean"
        ),
        "units": units,
        "expected_session_count": expected_session_count,
        "contributing_session_count": len(units),
        "noncontributing_session_count": len(missing),
        "noncontributing_session_ids": missing,
        "aggregation": "unweighted_mean_of_session_symmetric_overlap_rates",
        "aggregation_trace": [unit["session_id"] for unit in units],
        "n": len(units),
        "mean": mean,
        "sample_std": std,
        "rendered_percent_mean": _percent(mean),
        "rendered_percent_sample_std": _percent(std),
        "cohort_directions": {
            "T_to_M": {
                "numerator": forward_numerator, "denominator": forward_denominator,
                "denominator_unit": "T_moments",
                "value": forward_numerator / forward_denominator if forward_denominator else None,
            },
            "M_to_T": {
                "numerator": reverse_numerator, "denominator": reverse_denominator,
                "denominator_unit": "M_moments",
                "value": reverse_numerator / reverse_denominator if reverse_denominator else None,
            },
        },
        "cohort_value": cohort_value,
        "rendered_percent_cohort_value": _percent(cohort_value),
    }


def _aggregate_count(
    records: Sequence[tuple[str, Mapping[str, object]]], *, expected_session_count: int
) -> dict:
    units = []
    unavailable = []
    for session_id, record in records:
        count = record.get("count")
        if record.get("status") != "measured" or not isinstance(count, int) or count < 0:
            unavailable.append(session_id)
            continue
        units.append({
            "session_id": session_id,
            "count": count,
            "denominator": 1,
            "denominator_unit": "complete_T_and_M_session_artifact_pair",
            "all_m_moment_count": record.get("all_m_moment_count"),
        })
    values = [float(unit["count"]) for unit in units]
    mean = sum(values) / len(values) if values else None
    std = _sample_std(values)
    return {
        "status": "measured" if len(units) == expected_session_count else "incomplete",
        "denominator_statement": (
            "total_count denominator is the complete nine-session cohort; mean/sample_std "
            "denominator is one complete T/M artifact pair per session"
        ),
        "units": units,
        "expected_session_count": expected_session_count,
        "contributing_session_count": len(units),
        "noncontributing_session_count": len(unavailable),
        "noncontributing_session_ids": unavailable,
        "aggregation": "sum_and_unweighted_session_count_distribution",
        "aggregation_trace": [unit["session_id"] for unit in units],
        "n": len(units),
        "total_count": sum(unit["count"] for unit in units),
        "total_count_denominator_sessions": len(units),
        "mean_per_session": mean,
        "sample_std_per_session": std,
    }


def _aggregate_provenance_integrity(
    records: Sequence[tuple[str, Mapping[str, object]]], *, expected_session_count: int
) -> dict:
    required_counts = {
        "moment_count", "citation_count", "delivered_resolved_citation_count",
        "undelivered_citation_count", "stored_resolution_match_count",
        "stored_resolution_mismatch_count", "resolved_item_count",
        "complete_provenance_item_count", "incomplete_provenance_item_count",
        "resolved_item_session_complete_count", "resolved_item_interval_complete_count",
        "resolved_item_modality_complete_count",
        "resolved_item_source_digest_complete_count",
        "identity_required_item_count", "identity_complete_item_count",
        "identity_incomplete_item_count", "temporally_valid_citation_count",
        # Supplementary, but it must survive aggregation: without it the cohort
        # artifact can only say how many citations met the strict rule, not how many
        # of the rest still came from a window that was actually delivered.
        "citation_within_delivering_window_count",
        "temporally_invalid_citation_count",
        # Citations whose timing could not be evaluated because they were never delivered.
        # Dropping it from the cohort left the aggregated counts summing to 724 against a
        # stated 787 citations, and the per-session invariant did not catch it because the
        # key is present at session level.
        "citation_timing_not_evaluable_count",
        "valid_complete_moment_count",
        "invalid_or_incomplete_moment_count",
    }
    units = []
    unavailable = []
    for session_id, record in records:
        counts = record.get("counts")
        invalid_ids = record.get("invalid_or_incomplete_moment_ids")
        temporal_rule = record.get("temporal_rule")
        if (
            record.get("status") != "measured"
            or record.get("definition_id") != "METRIC-T4-PROVENANCE-INTEGRITY-001"
            or not isinstance(counts, Mapping)
            or not required_counts <= set(counts)
            or any(not isinstance(counts[key], int) or counts[key] < 0 for key in required_counts)
            or not isinstance(invalid_ids, Sequence)
            or isinstance(invalid_ids, (str, bytes))
            or not isinstance(temporal_rule, Mapping)
            or temporal_rule.get("rule_id") != "PROVENANCE-TEMPORAL-HALF-OPEN-V1"
        ):
            unavailable.append(session_id)
            continue
        if (
            counts["valid_complete_moment_count"]
            + counts["invalid_or_incomplete_moment_count"]
            != counts["moment_count"]
            or counts["delivered_resolved_citation_count"]
            + counts["undelivered_citation_count"]
            != counts["citation_count"]
            or counts["complete_provenance_item_count"]
            + counts["incomplete_provenance_item_count"]
            != counts["resolved_item_count"]
            or counts["stored_resolution_match_count"]
            + counts["stored_resolution_mismatch_count"]
            != counts["citation_count"]
            or counts["identity_complete_item_count"]
            + counts["identity_incomplete_item_count"]
            != counts["identity_required_item_count"]
            or counts["temporally_valid_citation_count"]
            + counts["temporally_invalid_citation_count"]
            + counts.get("citation_timing_not_evaluable_count", 0)
            != counts["citation_count"]
            or len(invalid_ids) != counts["invalid_or_incomplete_moment_count"]
        ):
            unavailable.append(session_id)
            continue
        units.append({
            "session_id": session_id,
            "integrity_status": record.get("integrity_status"),
            "counts": {key: counts[key] for key in sorted(required_counts)},
            "invalid_or_incomplete_moment_ids": list(invalid_ids),
        })
    aggregate_counts = {
        key: sum(unit["counts"][key] for unit in units) for key in sorted(required_counts)
    }
    invalid_moments = [
        {"session_id": unit["session_id"], "condition_moment_id": moment_id}
        for unit in units
        for moment_id in unit["invalid_or_incomplete_moment_ids"]
    ]
    passing_sessions = [
        unit["session_id"] for unit in units
        if unit["counts"]["invalid_or_incomplete_moment_count"] == 0
    ]
    contributing = len(units)
    return {
        "definition_id": "METRIC-T4-PROVENANCE-INTEGRITY-001",
        "status": "measured" if contributing == expected_session_count else "incomplete",
        "integrity_status": "passed" if not invalid_moments else "violations_detected",
        "denominator_statement": (
            "exhaustive T/M detections and their citation occurrences in every required session"
        ),
        "temporal_rule": {
            "rule_id": "PROVENANCE-TEMPORAL-HALF-OPEN-V1",
            "aggregation": "identical_locked_rule_required_for_every_session",
        },
        "units": units,
        "expected_session_count": expected_session_count,
        "contributing_session_count": contributing,
        "noncontributing_session_count": len(unavailable),
        "noncontributing_session_ids": unavailable,
        "aggregation_trace": [unit["session_id"] for unit in units],
        "counts": aggregate_counts,
        "invalid_or_incomplete_moments": invalid_moments,
        "passing_session_count": len(passing_sessions),
        "passing_session_ids": passing_sessions,
        "session_pass_rate": (
            len(passing_sessions) / contributing if contributing else None
        ),
    }


def _aggregate_harness_funnel(
    records: Sequence[tuple[str, Mapping[str, object]]],
    *,
    expected_session_count: int,
) -> tuple[dict, list[str]]:
    """Pool count-first funnel cells while retaining every session denominator."""
    failures: list[str] = []
    contributing = [
        (session_id, record)
        for session_id, record in records
        if record.get("status") == "measured"
    ]
    missing = [session_id for session_id, record in records if record.get("status") != "measured"]
    if len(contributing) != expected_session_count:
        failures.append(
            "harness_delivery_failure_funnel: computed from "
            f"{len(contributing)}/{expected_session_count} sessions; missing={missing}"
        )

    signals: dict[str, dict] = {}
    for signal in HARNESS_FUNNEL_SIGNALS:
        signals[signal] = {}
        for transition in HARNESS_FUNNEL_TRANSITIONS:
            if signal in {"face", "asd"} and transition == "valid_downstream_label_delivered":
                signals[signal][transition] = {
                    "definition_id": "METRIC-HARNESS-DELIVERY-FUNNEL-001",
                    "status": "unavailable",
                    "unavailable_reason": f"{signal} presence has no downstream semantic label",
                    "expected_session_count": expected_session_count,
                    "contributing_session_count": 0,
                }
                continue
            transition_records = []
            for session_id, record in records:
                by_signal = record.get("signals")
                row = by_signal.get(signal) if isinstance(by_signal, Mapping) else None
                cell = row.get(transition) if isinstance(row, Mapping) else None
                transition_records.append((session_id, cell if isinstance(cell, Mapping) else {}))
            aggregate = _aggregate_rate(
                transition_records,
                denominator_unit="transcript_segment_eligible_canonical_one_second_bins",
                expected_session_count=expected_session_count,
            )
            if aggregate["contributing_session_count"] != expected_session_count:
                failures.append(
                    f"harness_delivery_failure_funnel.{signal}.{transition}: computed from "
                    f"{aggregate['contributing_session_count']}/{expected_session_count} sessions; "
                    f"missing={aggregate['noncontributing_session_ids']}"
                )
            signals[signal][transition] = aggregate

    units = []
    reason_totals = {reason: 0 for reason in HARNESS_WITHHOLDING_REASONS}
    total_delivered = 0
    total_denominator = 0
    for session_id, record in contributing:
        denominator = record.get("denominator")
        counts = record.get("withholding_reason_counts")
        delivered_ids = record.get("delivered_bin_ids")
        if (
            not isinstance(denominator, int) or denominator < 1
            or not isinstance(counts, Mapping)
            or set(counts) != set(HARNESS_WITHHOLDING_REASONS)
            or any(not isinstance(counts[reason], int) or counts[reason] < 0 for reason in counts)
            or not isinstance(delivered_ids, Sequence) or isinstance(delivered_ids, (str, bytes))
        ):
            failures.append(f"{session_id}: invalid harness withholding partition")
            continue
        delivered_count = len(delivered_ids)
        if delivered_count + sum(int(counts[reason]) for reason in counts) != denominator:
            failures.append(f"{session_id}: harness withholding reasons do not partition denominator")
            continue
        unit = {
            "session_id": session_id,
            "denominator": denominator,
            "denominator_unit": "transcript_segment_eligible_canonical_one_second_bins",
            "delivered_count": delivered_count,
            "withholding_reason_counts": {reason: int(counts[reason]) for reason in counts},
        }
        units.append(unit)
        total_denominator += denominator
        total_delivered += delivered_count
        for reason in reason_totals:
            reason_totals[reason] += int(counts[reason])

    return {
        "definition_id": "METRIC-HARNESS-DELIVERY-FUNNEL-001",
        "status": "measured" if len(units) == expected_session_count else "incomplete",
        "expected_session_count": expected_session_count,
        "contributing_session_count": len(units),
        "noncontributing_session_ids": [
            session_id for session_id, _ in records if session_id not in {unit["session_id"] for unit in units}
        ],
        "denominator_statement": "pooled unique transcript-segment-eligible one-second bins; each session denominator remains visible",
        "units": units,
        "signals": signals,
        "withholding": {
            "cohort_denominator": total_denominator,
            "delivered_count": total_delivered,
            "delivered_rate": total_delivered / total_denominator if total_denominator else None,
            "reason_counts": reason_totals,
            "reason_rates": {
                reason: reason_totals[reason] / total_denominator if total_denominator else None
                for reason in reason_totals
            },
            "partition_invariant": total_delivered + sum(reason_totals.values()) == total_denominator,
        },
        "aggregation_trace": [unit["session_id"] for unit in units],
        "n": len(units),
    }, failures


def _validate_artifact(artifact: Mapping[str, object]) -> tuple[str, str]:
    if artifact.get("schema_version") != PRODUCER_VERSION:
        raise ValueError("unsupported per-session paper metric schema")
    if artifact.get("producer") != "compute_paper_metrics":
        raise ValueError("unsupported per-session paper metric producer")
    if artifact.get("measurement") != "capture_at_run":
        raise ValueError("per-session paper metrics must be capture_at_run")
    session_id = artifact.get("session_id")
    run_id = artifact.get("run_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("per-session metric artifact requires session_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("per-session metric artifact requires run_id")
    source_artifacts = artifact.get("source_artifacts")
    if not isinstance(source_artifacts, Mapping) or not source_artifacts:
        raise ValueError(f"per-session metric artifact has no source lineage: {session_id}")
    for source_key, source in source_artifacts.items():
        if not isinstance(source, Mapping):
            raise ValueError(f"invalid source lineage for {session_id}/{source_key}")
        if source.get("run_id") != run_id or source.get("session_id") != session_id:
            raise ValueError(f"cross-run source lineage for {session_id}/{source_key}")
    return session_id, run_id


def _build_quantity_map(
    ordered: Sequence[tuple[str, Mapping[str, object]]], failures: list[str]
) -> dict[str, dict]:
    result = {}
    for quantity_id in BASE_QUANTITY_IDS:
        sources = []
        missing = []
        for session_id, artifact in ordered:
            mapping = artifact.get("quantity_artifact_map")
            row = mapping.get(quantity_id) if isinstance(mapping, Mapping) else None
            if (
                not isinstance(row, Mapping)
                or row.get("quantity_id") != quantity_id
                or row.get("session_id") != session_id
                or row.get("run_id") != artifact.get("run_id")
                or not isinstance(row.get("artifacts"), Sequence)
                or not row.get("artifacts")
            ):
                missing.append(session_id)
                continue
            sources.append({
                "session_id": session_id,
                "run_id": row["run_id"],
                "artifacts": row["artifacts"],
            })
        if missing:
            failures.append(
                f"{quantity_id}: artifact lineage present for {len(sources)}/{len(ordered)} "
                f"sessions; missing={missing}"
            )
        result[quantity_id] = {
            "quantity_id": quantity_id,
            "measurement": "capture_at_run",
            "source_session_count": len(sources),
            "sources": sources,
            "missing_source_session_ids": missing,
        }
    # Stage 19 is the sole producer of prose-level gaps. Its lineage is derived from
    # both declared base cells for every session; Stage 18 must not falsely declare a
    # gap quantity that it does not compute or store.
    for quantity_id, dependencies in TABLE3_GAP_QUANTITY_DEPENDENCIES.items():
        sources = []
        missing = []
        for session_id, artifact in ordered:
            mapping = artifact.get("quantity_artifact_map")
            rows = [mapping.get(dependency) for dependency in dependencies] if isinstance(
                mapping, Mapping
            ) else []
            valid = len(rows) == len(dependencies) and all(
                isinstance(row, Mapping)
                and row.get("quantity_id") == dependency
                and row.get("session_id") == session_id
                and row.get("run_id") == artifact.get("run_id")
                and isinstance(row.get("artifacts"), Sequence)
                and bool(row.get("artifacts"))
                for dependency, row in zip(dependencies, rows)
            )
            if not valid:
                missing.append(session_id)
                continue
            artifacts = []
            seen_artifacts = set()
            for row in rows:
                for source in row["artifacts"]:  # type: ignore[index,union-attr]
                    identity = (
                        source.get("path"), source.get("sha256")
                    ) if isinstance(source, Mapping) else (repr(source), None)
                    if identity not in seen_artifacts:
                        seen_artifacts.add(identity)
                        artifacts.append(source)
            sources.append({
                "session_id": session_id,
                "run_id": artifact.get("run_id"),
                "input_quantity_ids": list(dependencies),
                "artifacts": artifacts,
            })
        if missing:
            failures.append(
                f"{quantity_id}: base-cell lineage present for {len(sources)}/{len(ordered)} "
                f"sessions; missing={missing}"
            )
        result[quantity_id] = {
            "quantity_id": quantity_id,
            "definition_id": "METRIC-T3-ABSOLUTE-PP-GAP-001",
            "measurement": "capture_at_run",
            "producer_stage": "19_aggregate_paper_metrics",
            "source_session_count": len(sources),
            "sources": sources,
            "missing_source_session_ids": missing,
        }
    for quantity_id in QUANTITY_IDS:
        alias = f"{quantity_id}[cohort]"
        result[alias] = {**result[quantity_id], "quantity_id": alias}
    result["paper_metrics[cohort]"] = {
        "quantity_id": "paper_metrics[cohort]",
        "measurement": "capture_at_run",
        "source_session_count": len(ordered),
        "sources": [
            {"session_id": session_id, "run_id": artifact.get("run_id")}
            for session_id, artifact in ordered
        ],
        "missing_source_session_ids": [],
    }
    return result


def _cohort_input(
    artifact: Mapping[str, object], session_id: str
) -> Mapping[str, object]:
    value = artifact.get("cohort_inputs")
    if not isinstance(value, Mapping):
        raise ValueError(f"per-session metric artifact has no cohort inputs: {session_id}")
    return value


def _moments(
    cohort_input: Mapping[str, object], session_id: str, condition: str
) -> Sequence[Mapping[str, object]] | None:
    by_condition = cohort_input.get("moments_by_condition")
    if not isinstance(by_condition, Mapping):
        return None
    records = by_condition.get(condition)
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        return None
    if any(not isinstance(record, Mapping) for record in records):
        raise ValueError(f"invalid {condition} moments in cohort input for {session_id}")
    return records  # type: ignore[return-value]


def _aggregate_metric_from_table3(record: Mapping[str, object]) -> AggregateMetric:
    trace = record.get("aggregation_trace")
    units = record.get("units")
    if (
        record.get("status") != "measured"
        or not isinstance(trace, Sequence)
        or isinstance(trace, (str, bytes))
        or not isinstance(units, Sequence)
        or isinstance(units, (str, bytes))
    ):
        return AggregateMetric(
            str(record.get("definition_id")), (), (), 0, None, None, None, None,
            "unavailable",
        )
    count_rates = []
    for unit in units:
        if not isinstance(unit, Mapping):
            raise ValueError("Table 3 aggregate contains an invalid unit")
        count_rates.append(
            CountRate(
                str(unit["session_id"]), int(unit["numerator"]), int(unit["denominator"]),
                float(unit["value"]), "measured",
            )
        )
    return AggregateMetric(
        definition_id=str(record.get("definition_id")),
        units=tuple(count_rates),
        aggregation_trace=tuple(str(value) for value in trace),
        n=int(record.get("n", 0)),
        mean=float(record["mean"]) if isinstance(record.get("mean"), (int, float)) else None,
        sample_std=(
            float(record["sample_std"])
            if isinstance(record.get("sample_std"), (int, float)) else None
        ),
        rendered_mean=None,
        rendered_sample_std=None,
        status="measured",
    )


def aggregate_paper_metrics(
    session_metrics: Sequence[Mapping[str, object]],
    *,
    expected_session_count: int = EXPECTED_SESSION_COUNT,
    expected_session_ids: Sequence[str] | None = None,
) -> dict:
    if not isinstance(expected_session_count, int) or expected_session_count < 1:
        raise ValueError("expected_session_count must be a positive integer")
    if expected_session_ids is not None:
        expected_ids = tuple(expected_session_ids)
        if len(expected_ids) != expected_session_count or len(set(expected_ids)) != len(expected_ids):
            raise ValueError("expected_session_ids must be unique and match expected_session_count")
    else:
        expected_ids = ()
    if not session_metrics:
        raise ValueError("at least one session metric artifact is required")

    by_session: dict[str, Mapping[str, object]] = {}
    run_ids = {}
    for artifact in session_metrics:
        session_id, run_id = _validate_artifact(artifact)
        if session_id in by_session:
            raise ValueError(f"duplicate session metric artifact: {session_id}")
        by_session[session_id] = artifact
        run_ids[session_id] = run_id
    ordered = sorted(by_session.items())
    failures: list[str] = []
    if len(ordered) != expected_session_count:
        failures.append(
            f"cohort: received {len(ordered)}/{expected_session_count} expected session artifacts"
        )
    if expected_ids:
        missing = sorted(set(expected_ids) - set(by_session))
        unexpected = sorted(set(by_session) - set(expected_ids))
        if missing or unexpected:
            failures.append(f"cohort session IDs mismatch; missing={missing}, unexpected={unexpected}")

    table3: dict[str, dict] = {}
    for signal in SIGNALS:
        table3[signal] = {}
        for column in COLUMNS:
            records = []
            definition_ids = set()
            for session_id, artifact in ordered:
                table = artifact.get("table3")
                row = table.get(signal) if isinstance(table, Mapping) else None
                if not isinstance(row, Mapping) or row.get("status") != "measured":
                    records.append((session_id, {}))
                    continue
                definition_ids.add(row.get("definition_id"))
                record = row.get(column)
                records.append((session_id, record if isinstance(record, Mapping) else {}))
                if column == "selected":
                    union = row.get("union")
                    if not isinstance(record, Mapping) or not isinstance(union, Mapping):
                        failures.append(f"{session_id}/{signal}: Selected or Union record missing")
                    elif int(record.get("numerator", 0)) > int(union.get("numerator", 0)):
                        failures.append(f"{session_id}/{signal}: Selected exceeds Union")
            if len(definition_ids) > 1:
                raise ValueError(f"mixed metric definitions for {signal}")
            aggregate = _aggregate_rate(
                records, denominator_unit="canonical_one_second_bins",
                expected_session_count=expected_session_count,
            )
            if aggregate["contributing_session_count"] != expected_session_count:
                failures.append(
                    f"table3.{signal}.{column}: computed from "
                    f"{aggregate['contributing_session_count']}/{expected_session_count} sessions; "
                    f"missing={aggregate['noncontributing_session_ids']}"
                )
            table3[signal][column] = {
                "definition_id": next(iter(definition_ids), None), **aggregate,
            }

    def records_for(key: str) -> list[tuple[str, Mapping[str, object]]]:
        return [
            (session_id, value if isinstance(value := artifact.get(key), Mapping) else {})
            for session_id, artifact in ordered
        ]

    def definition_id_for(
        records: Sequence[tuple[str, Mapping[str, object]]], label: str
    ) -> object:
        definition_ids = {
            record.get("definition_id") for _, record in records
            if record.get("definition_id") is not None
        }
        if len(definition_ids) > 1:
            raise ValueError(f"mixed metric definitions for {label}")
        return next(iter(definition_ids), None)

    speaker_records = records_for("speaker_identity_link")
    overlap_records = records_for("tm_overlap")
    m_only_records = records_for("m_only_count")
    m_only_cross_records = records_for("m_only_cross_modal_evidence")
    all_m_cross_records = records_for("aggregate_cross_modal_evidence")
    provenance_records = records_for("provenance_integrity")
    harness_records = records_for("harness_delivery_failure_funnel")
    speaker_definition_id = definition_id_for(speaker_records, "speaker identity link")
    overlap_definition_id = definition_id_for(overlap_records, "T/M overlap")
    m_only_definition_id = definition_id_for(m_only_records, "M-only count")
    m_only_cross_definition_id = definition_id_for(
        m_only_cross_records, "M-only cross-modal evidence"
    )
    all_m_cross_definition_id = definition_id_for(
        all_m_cross_records, "aggregate cross-modal evidence"
    )
    provenance_definition_id = definition_id_for(
        provenance_records, "provenance integrity"
    )
    speaker = _aggregate_rate(
        speaker_records,
        denominator_unit="positive_duration_diarized_speakers",
        expected_session_count=expected_session_count,
    )
    overlap = _aggregate_overlap(overlap_records, expected_session_count=expected_session_count)
    m_only = _aggregate_count(m_only_records, expected_session_count=expected_session_count)
    m_only_cross = _aggregate_rate(
        m_only_cross_records,
        denominator_unit="valid_M_only_moments",
        expected_session_count=expected_session_count,
    )
    all_m_cross = _aggregate_rate(
        all_m_cross_records,
        denominator_unit="valid_M_moments",
        expected_session_count=expected_session_count,
    )
    provenance_integrity = _aggregate_provenance_integrity(
        provenance_records, expected_session_count=expected_session_count
    )
    harness_funnel, harness_failures = _aggregate_harness_funnel(
        harness_records, expected_session_count=expected_session_count
    )
    failures.extend(harness_failures)
    for quantity_id, aggregate in (
        ("speaker_identity_link", speaker), ("tm_overlap", overlap),
        ("m_only_count", m_only), ("m_only_cross_modal_evidence", m_only_cross),
        ("aggregate_cross_modal_evidence", all_m_cross),
        ("provenance_integrity", provenance_integrity),
    ):
        if aggregate["contributing_session_count"] != expected_session_count:
            failures.append(
                f"{quantity_id}: computed from {aggregate['contributing_session_count']}/"
                f"{expected_session_count} sessions; missing={aggregate['noncontributing_session_ids']}"
            )

    quantity_map = _build_quantity_map(ordered, failures)

    cohort_inputs = {
        session_id: _cohort_input(artifact, session_id)
        for session_id, artifact in ordered
    }
    session_ids = tuple(session_id for session_id, _ in ordered)
    moments_by_condition = {
        condition: {
            session_id: _moments(cohort_inputs[session_id], session_id, condition)
            for session_id in session_ids
        }
        for condition in ("K", "T", "M")
    }
    moment_counts_metric = compute_moment_counts(session_ids, moments_by_condition)
    category_diversity = {
        condition: asdict(
            compute_category_diversity(
                condition, session_ids, moments_by_condition[condition], FOCAL_CATEGORIES
            )
        )
        for condition in ("T", "M")
    }
    directional_overlap = {
        "T_to_M": asdict(
            compute_directional_overlap(
                "T", "M", session_ids,
                moments_by_condition["T"], moments_by_condition["M"],
            )
        ),
        "M_to_T": asdict(
            compute_directional_overlap(
                "M", "T", session_ids,
                moments_by_condition["M"], moments_by_condition["T"],
            )
        ),
    }
    best_angles_by_session = {
        session_id: (
            value if isinstance(value := cohort_inputs[session_id].get("best_angles"), Mapping)
            else None
        )
        for session_id in session_ids
    }
    camera_selection = {
        label: asdict(metric)
        for label, metric in compute_camera_selection_distribution(
            session_ids, best_angles_by_session
        ).items()
    }
    session_ends = {
        session_id: (
            float(value)
            if isinstance(value := cohort_inputs[session_id].get("session_end_seconds"), (int, float))
            else None
        )
        for session_id in session_ids
    }
    windows_by_session = {
        session_id: (
            value
            if isinstance(value := cohort_inputs[session_id].get("multimodal_windows"), Sequence)
            and not isinstance(value, (str, bytes))
            else None
        )
        for session_id in session_ids
    }
    transcript_coverage = compute_transcript_context_coverage(
        session_ids, session_ends, windows_by_session
    )
    scene_coverage = compute_scene_context_coverage(
        session_ids, session_ends, windows_by_session
    )
    attention_coverage = compute_attention_context_coverage(
        session_ids, session_ends, windows_by_session
    )
    t_counts = {
        session_id: (
            None if moments_by_condition["T"][session_id] is None
            else len(moments_by_condition["T"][session_id] or ())
        )
        for session_id in session_ids
    }
    m_counts = {
        session_id: (
            None if moments_by_condition["M"][session_id] is None
            else len(moments_by_condition["M"][session_id] or ())
        )
        for session_id in session_ids
    }
    wilcoxon = compute_wilcoxon_signed_rank(session_ids, t_counts, m_counts)
    manifests_by_session = {
        session_id: (
            value
            if isinstance(value := cohort_inputs[session_id].get("session_manifest"), Mapping)
            else None
        )
        for session_id in session_ids
    }
    session_count = compute_session_count(session_ids, manifests_by_session)
    scenarios = compute_scenario_distribution(session_ids, manifests_by_session)
    durations = compute_session_durations(session_ids, manifests_by_session)
    role_records = {
        session_id: (
            value
            if isinstance(value := cohort_inputs[session_id].get("role_records"), Sequence)
            and not isinstance(value, (str, bytes))
            else None
        )
        for session_id in session_ids
    }
    participants = compute_participant_counts(session_ids, role_records)
    asd_best = _aggregate_metric_from_table3(table3["asd"]["best_cam"])
    asd_union = _aggregate_metric_from_table3(table3["asd"]["union"])
    asd_selected = _aggregate_metric_from_table3(table3["asd"]["selected"])
    table3_ratio = {
        "union_to_best_cam": asdict(compute_table3_ratio(asd_union, asd_best)),
        "selected_to_best_cam": asdict(compute_table3_ratio(asd_selected, asd_best)),
    }
    table3_absolute_percentage_point_gaps = {
        "definition_id": "METRIC-T3-ABSOLUTE-PP-GAP-001",
        "unit": "percentage_points",
        "signals": {
            signal: {
                comparison: {
                    "quantity_id": f"table3.{signal}.gap.{comparison}",
                    **asdict(compute_table3_absolute_percentage_point_gap(
                        comparison,
                        _aggregate_metric_from_table3(table3[signal][minuend]),
                        _aggregate_metric_from_table3(table3[signal][subtrahend]),
                    )),
                }
                for comparison, (minuend, subtrahend) in TABLE3_GAP_COMPARISONS.items()
            }
            for signal in SIGNALS
        },
    }
    for signal, gaps in table3_absolute_percentage_point_gaps["signals"].items():
        for comparison in ("union_minus_best_cam", "union_minus_selected"):
            gap = gaps[comparison]
            value = gap["value_percentage_points"]
            if gap["status"] == "measured" and isinstance(value, (int, float)) and value < -1e-12:
                failures.append(f"table3.{signal}: {comparison} is negative")
    report = {
        "schema_version": PRODUCER_VERSION,
        "producer": "aggregate_paper_metrics",
        "measurement": "capture_at_run",
        "expected_session_count": expected_session_count,
        "artifact_session_count": len(ordered),
        "session_ids": [session_id for session_id, _ in ordered],
        "run_ids_by_session": run_ids,
        "table3": table3,
        "speaker_identity_link": {
            "definition_id": speaker_definition_id, **speaker,
        },
        "tm_overlap": {"definition_id": overlap_definition_id, **overlap},
        "m_only_count": {"definition_id": m_only_definition_id, **m_only},
        "m_only_cross_modal_evidence": {
            "definition_id": m_only_cross_definition_id, **m_only_cross,
        },
        "aggregate_cross_modal_evidence": {
            "definition_id": all_m_cross_definition_id, **all_m_cross,
        },
        "provenance_integrity": {
            "definition_id": provenance_definition_id, **provenance_integrity,
        },
        "harness_delivery_failure_funnel": harness_funnel,
        "evidence_distribution": {
            "definition_id": "METRIC-T4-EVIDENCE-DISTRIBUTION-001",
            "status": (
                "measured"
                if all(
                    isinstance(artifact.get("evidence_distribution"), Mapping)
                    and artifact["evidence_distribution"].get("status") == "measured"
                    for _, artifact in ordered
                )
                else "unavailable"
            ),
            "units": [
                {"session_id": session_id, **dict(artifact["evidence_distribution"])}
                for session_id, artifact in ordered
                if isinstance(artifact.get("evidence_distribution"), Mapping)
            ],
            "aggregation_trace": list(session_ids),
            "n": len(session_ids),
        },
        "attention_distribution": {
            "definition_id": "METRIC-EXAMPLE-ATTENTION-001",
            "status": "unavailable",
            "units": [
                {"session_id": session_id, **dict(artifact["attention_distribution"])}
                for session_id, artifact in ordered
                if isinstance(artifact.get("attention_distribution"), Mapping)
            ],
            "unavailable_reason": "exact worked-example interval and authorized participants are unresolved",
        },
        "example_silence": {
            "definition_id": "METRIC-EXAMPLE-SILENCE-001",
            "status": "unavailable",
            "units": [
                {"session_id": session_id, **dict(artifact["example_silence"])}
                for session_id, artifact in ordered
                if isinstance(artifact.get("example_silence"), Mapping)
            ],
            "unavailable_reason": "exact worked-example interval boundaries are unresolved",
        },
        "moment_counts": asdict(moment_counts_metric),
        "category_diversity": category_diversity,
        "directional_overlap": directional_overlap,
        "camera_selection_distribution": camera_selection,
        "transcript_context_coverage": asdict(transcript_coverage),
        "scene_context_coverage": asdict(scene_coverage),
        "attention_context_coverage": asdict(attention_coverage),
        "wilcoxon_signed_rank": asdict(wilcoxon),
        "session_count": asdict(session_count),
        "scenario_distribution": asdict(scenarios),
        "session_durations": asdict(durations),
        "participant_counts": asdict(participants),
        "table3_ratio": table3_ratio,
        "table3_absolute_percentage_point_gaps": table3_absolute_percentage_point_gaps,
        "quantity_artifact_map": quantity_map,
        "validation": {
            "status": "passed" if not failures else "failed",
            "failure_count": len(failures),
            "failures": failures,
            "rules": {
                "expected_session_count": expected_session_count,
                "all_quantities_require_expected_sessions": True,
                "selected_must_not_exceed_union": True,
                "all_required_upstream_artifacts_must_have_current_run_lineage": True,
            },
        },
    }
    if failures:
        raise MetricsValidationError(report)
    return report


def _load(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"required per-session metric artifact is missing: {path}")
    with path.open("r", encoding="utf-8") as handle:
        result = json.load(handle)
    if not isinstance(result, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate and validate per-session paper metrics")
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-session-count", type=int, default=EXPECTED_SESSION_COUNT)
    parser.add_argument("--expected-session-id", action="append")
    args = parser.parse_args()
    try:
        result = aggregate_paper_metrics(
            [_load(path) for path in args.input],
            expected_session_count=args.expected_session_count,
            expected_session_ids=args.expected_session_id,
        )
    except MetricsValidationError as error:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(error.report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        raise SystemExit(str(error)) from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
