"""Metric-definition gates and prospective Table 3 coverage operators."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from itertools import product
from math import ceil, floor, isfinite, sqrt
from typing import Callable, Mapping, Sequence

from scripts.core.errors import MetricDefinitionUnresolvedError


TABLE3_DEFINITION_IDS = {
    "asd": "METRIC-T3-ASD-001",
    "face": "METRIC-T3-FACE-001",
    "head_pose": "METRIC-T3-HEADPOSE-001",
}

TABLE3_CAMERAS = ("cam1", "cam2", "cam3")
TABLE3_LINK_THRESHOLD = 0.0

EVIDENCE_MODALITY_CHANNEL = {
    "transcript": "verbal_context",
    "speaker_dynamics": "verbal_context",
    "visual_attention": "attention",
    "visual_scene": "scene_pose",
}
EVIDENCE_BUCKETS = (
    "verbal_context_only",
    "verbal_context_plus_attention_only",
    "verbal_context_plus_scene_pose_only",
    "all_three_channels",
)

MEASURED = "measured"
UNAVAILABLE = "unavailable"
ATTENTION_TARGETS = ("patient", "person", "other")
HARNESS_FUNNEL_SIGNALS = ("face", "asd", "head_pose", "attention")
HARNESS_FUNNEL_TRANSITIONS = (
    "eligible_union",
    "stage3_assigned",
    "selected_camera_signal",
    "strict_asd_gate_passed",
    "delivered",
    "valid_downstream_label_delivered",
)
HARNESS_WITHHOLDING_REASONS = (
    "speaker_unlinked",
    "no_selected_camera_track",
    "no_raw_face",
    "no_scored_asd_sample",
    "asd_score_not_strictly_positive",
    "no_usable_head_pose",
    "no_valid_attention_label",
)


@dataclass(frozen=True)
class CountRate:
    """One auditable unit-level rate; a measured zero always has a nonzero denominator."""

    unit_id: str
    numerator: int | None
    denominator: int | None
    value: float | None
    status: str
    unavailable_reason: str | None = None
    numerator_unit_ids: tuple[str, ...] = ()
    denominator_unit_ids: tuple[str, ...] = ()
    excluded_unit_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AggregateMetric:
    """Unweighted aggregation over measured units with a complete aggregation trace."""

    definition_id: str
    units: tuple[CountRate, ...]
    aggregation_trace: tuple[str, ...]
    n: int
    mean: float | None
    sample_std: float | None
    rendered_mean: str | None
    rendered_sample_std: str | None
    status: str


@dataclass(frozen=True)
class MomentCountMetric:
    definition_id: str
    by_condition: Mapping[str, AggregateMetric]


@dataclass(frozen=True)
class DiversityMetric:
    definition_id: str
    condition: str
    distinct_categories: int | None
    taxonomy_categories: int
    value: float | None
    category_ids: tuple[str, ...]
    aggregation_trace: tuple[str, ...]
    n: int
    status: str
    missing_session_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class DirectionalOverlap:
    definition_id: str
    source_condition: str
    target_condition: str
    numerator: int | None
    denominator: int | None
    value: float | None
    overlapping_moment_ids: tuple[str, ...]
    source_moment_ids: tuple[str, ...]
    session_ids: tuple[str, ...]
    missing_session_ids: tuple[str, ...]
    n: int
    status: str


@dataclass(frozen=True)
class SymmetricOverlap:
    definition_id: str
    left_to_right: DirectionalOverlap
    right_to_left: DirectionalOverlap
    value: float | None
    aggregation_trace: tuple[str, str]
    n: int
    status: str


@dataclass(frozen=True)
class MOnlyMetric:
    definition_id: str
    numerator: int | None
    denominator: int | None
    value: float | None
    m_only_moment_ids: tuple[str, ...]
    all_m_moment_ids: tuple[str, ...]
    session_ids: tuple[str, ...]
    missing_session_ids: tuple[str, ...]
    n: int
    status: str


@dataclass(frozen=True)
class WilcoxonMetric:
    definition_id: str
    pairs: tuple[tuple[str, int, int], ...]
    differences: tuple[int, ...]
    ranks: tuple[float, ...]
    w_plus: float | None
    w_minus: float | None
    statistic: float | None
    p_value: float | None
    n: int
    effective_nonzero_n: int
    missing_session_ids: tuple[str, ...]
    alternative: str
    zero_method: str
    method: str
    status: str


@dataclass(frozen=True)
class AttentionDistribution:
    definition_id: str
    interval_id: str
    interval_start_seconds: float
    interval_end_seconds: float
    participant_ids: tuple[str, ...]
    target_counts: Mapping[str, int]
    denominator: int
    rates: Mapping[str, float | None]
    sample_ids: tuple[str, ...]
    excluded_sample_ids: tuple[str, ...]
    aggregation_trace: tuple[str, ...]
    n: int
    status: str


@dataclass(frozen=True)
class SilenceMetric:
    definition_id: str
    interval_id: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    speech_interval_ids: tuple[str, ...]
    aggregation_trace: tuple[str, ...]
    n: int
    status: str


@dataclass(frozen=True)
class ClinicianMetric:
    definition_id: str
    stratum: str
    positive_label: str
    numerator: int
    denominator: int
    value: float | None
    numerator_interval_ids: tuple[str, ...]
    denominator_interval_ids: tuple[str, ...]
    excluded_interval_ids: tuple[str, ...]
    aggregation_trace: tuple[str, ...]
    n: int
    status: str


@dataclass(frozen=True)
class CohortCountMetric:
    definition_id: str
    numerator: int
    denominator: int
    session_ids: tuple[str, ...]
    missing_session_ids: tuple[str, ...]
    aggregation_trace: tuple[str, ...]
    n: int
    status: str


@dataclass(frozen=True)
class CountDistributionMetric:
    definition_id: str
    raw_counts: Mapping[str, int]
    denominator: int
    unit_ids_by_value: Mapping[str, tuple[str, ...]]
    missing_unit_ids: tuple[str, ...]
    aggregation_trace: tuple[str, ...]
    n: int
    status: str


@dataclass(frozen=True)
class DurationUnit:
    session_id: str
    origin_seconds: float | None
    acquisition_end_seconds: float | None
    duration_seconds: float | None
    status: str
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class DurationMetric:
    definition_id: str
    units: tuple[DurationUnit, ...]
    aggregation_trace: tuple[str, ...]
    n: int
    mean_seconds: float | None
    sample_std_seconds: float | None
    status: str


@dataclass(frozen=True)
class RatioMetric:
    definition_id: str
    numerator_mean: float | None
    denominator_mean: float | None
    value: float | None
    numerator_trace: tuple[str, ...]
    denominator_trace: tuple[str, ...]
    n: int
    status: str


@dataclass(frozen=True)
class AbsolutePercentagePointGap:
    """Difference between two unrounded aggregate rates, expressed in percentage points."""

    definition_id: str
    comparison: str
    minuend_mean: float | None
    subtrahend_mean: float | None
    value_percentage_points: float | None
    rendered_percentage_points: str | None
    minuend_trace: tuple[str, ...]
    subtrahend_trace: tuple[str, ...]
    n: int
    status: str
    unavailable_reason: str | None = None


def _require_metric_definition(definition_id: str, *, paper_mode: bool) -> None:
    """Reject unnamed metric definitions before any value is emitted."""
    if paper_mode and not definition_id:
        raise MetricDefinitionUnresolvedError("METRIC_DEFINITION_UNRESOLVED: missing ID")


def _round_half_up(value: float | int) -> str:
    return format(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), "f")


def _sample_std(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _aggregate(definition_id: str, units: Sequence[CountRate]) -> AggregateMetric:
    measured = tuple(unit for unit in units if unit.status == MEASURED)
    values = [unit.value for unit in measured]
    if any(value is None for value in values):
        raise AssertionError("measured units must have a value")
    numeric_values = [float(value) for value in values]
    mean = sum(numeric_values) / len(numeric_values) if numeric_values else None
    std = _sample_std(numeric_values)
    return AggregateMetric(
        definition_id=definition_id,
        units=tuple(units),
        aggregation_trace=tuple(unit.unit_id for unit in measured),
        n=len(measured),
        mean=mean,
        sample_std=std,
        rendered_mean=None if mean is None else _round_half_up(mean),
        rendered_sample_std=None if std is None else _round_half_up(std),
        status=MEASURED if measured else UNAVAILABLE,
    )


def _validate_ids(ids: Sequence[str], *, name: str) -> tuple[str, ...]:
    result = tuple(ids)
    if not result or any(not isinstance(value, str) or not value for value in result):
        raise ValueError(f"{name} must contain non-empty IDs")
    if len(set(result)) != len(result):
        raise ValueError(f"{name} must not contain duplicates")
    return result


def _record_id(record: Mapping[str, object]) -> str:
    value = record.get("moment_id", record.get("match_id"))
    if not isinstance(value, str) or not value:
        raise ValueError("moment records require moment_id or match_id")
    return value


def _validated_moments(
    records: Sequence[Mapping[str, object]], *, session_id: str
) -> tuple[Mapping[str, object], ...]:
    result = tuple(records)
    seen: set[str] = set()
    for record in result:
        moment_id = _record_id(record)
        if moment_id in seen:
            raise ValueError(f"duplicate moment ID: {moment_id}")
        seen.add(moment_id)
        record_session = record.get("session_id", session_id)
        if record_session != session_id:
            raise ValueError(f"moment {moment_id} is assigned to the wrong session")
        start = float(record.get("start_seconds", float("nan")))
        end = float(record.get("end_seconds", float("nan")))
        if not isfinite(start) or not isfinite(end) or start < 0 or end <= start:
            raise ValueError(f"invalid half-open interval for moment {moment_id}")
    return result


@dataclass(frozen=True)
class Table3Coverage:
    """Count-first output for one signal in one session.

    Rates remain derivable from the integer bin sets. The projected segment/camera trace,
    gate failures, and inter-segment bins make the difference between Union and Selected
    auditable without changing the shared denominator.
    """

    definition_id: str
    signal: str
    denominator_bins: int
    per_camera_covered_bins: Mapping[str, frozenset[int]]
    best_camera_id: str
    best_camera_covered_bins: frozenset[int]
    union_covered_bins: frozenset[int]
    selected_covered_bins: frozenset[int]
    selected_segments_by_bin: tuple[tuple[tuple[str, str | None], ...], ...]
    selected_gate_passed_bins: frozenset[int]
    selected_gate_failed_bins: frozenset[int]
    inter_segment_bins: frozenset[int]
    status: str = MEASURED
    aggregation_trace: tuple[str, ...] = ()
    n: int = 0

    def rate(self, covered_bins: frozenset[int]) -> float:
        """Return the unrounded proportion; rendering percentages is a later step."""
        return len(covered_bins) / self.denominator_bins


@dataclass(frozen=True)
class UnavailableMetric:
    definition_id: str
    status: str
    unavailable_reason: str
    missing_unit_ids: tuple[str, ...]
    aggregation_trace: tuple[str, ...] = ()
    n: int = 0


@dataclass(frozen=True)
class HarnessDeliveryFunnel:
    """Count-first delivery trace over unique transcript-eligible one-second bins."""

    definition_id: str
    denominator: int
    denominator_unit: str
    denominator_bin_ids: tuple[int, ...]
    signals: Mapping[str, Mapping[str, CountRate | UnavailableMetric]]
    withholding_reason_counts: Mapping[str, int]
    withholding_bin_ids: Mapping[str, tuple[int, ...]]
    delivered_bin_ids: tuple[int, ...]
    aggregation_trace: tuple[str, ...]
    n: int
    status: str = MEASURED


def compute_harness_delivery_funnel(
    bin_records: Sequence[Mapping[str, object]] | None,
    *,
    paper_mode: bool = True,
) -> HarnessDeliveryFunnel | UnavailableMetric:
    """Lock the harness funnel arithmetic and its mutually exclusive failure partition.

    The producer supplies one record for every unique transcript-segment-eligible canonical
    bin. Signal transitions are cumulative, so each successive measured set must be a subset
    of the preceding set. The final withholding reason is an independent end-to-end cascade:
    every denominator bin is either delivered or assigned exactly one approved reason.

    Face and ASD have no downstream semantic labels of their own, so
    ``valid_downstream_label_delivered`` is explicitly unavailable for that signal. Face's
    ``delivered`` transition means that its gated dependency chain resulted in a delivered
    visual-attention record; it does not claim that face boxes are model context.
    """
    definition_id = "METRIC-HARNESS-DELIVERY-FUNNEL-001"
    _require_metric_definition(definition_id, paper_mode=paper_mode)
    if bin_records is None:
        return UnavailableMetric(
            definition_id,
            UNAVAILABLE,
            "one or more required harness-funnel inputs are unavailable",
            ("transcript_eligible_bin_records",),
        )
    records = tuple(bin_records)
    if not records:
        return UnavailableMetric(
            definition_id,
            UNAVAILABLE,
            "no positive-duration transcript segment intersects the canonical grid",
            ("transcript_eligible_bins",),
        )

    by_bin: dict[int, Mapping[str, object]] = {}
    for record in records:
        bin_id = record.get("bin_id")
        if not isinstance(bin_id, int) or bin_id < 0:
            raise ValueError("harness funnel bin_id must be a non-negative integer")
        if bin_id in by_bin:
            raise ValueError(f"duplicate harness funnel bin_id: {bin_id}")
        by_bin[bin_id] = record
    bin_ids = tuple(sorted(by_bin))

    signals: dict[str, dict[str, CountRate | UnavailableMetric]] = {}
    for signal in HARNESS_FUNNEL_SIGNALS:
        previous: set[int] | None = None
        for transition in HARNESS_FUNNEL_TRANSITIONS:
            if signal in {"face", "asd"} and transition == "valid_downstream_label_delivered":
                signals.setdefault(signal, {})[transition] = UnavailableMetric(
                    definition_id,
                    UNAVAILABLE,
                    f"{signal} presence has no downstream semantic label",
                    (f"{signal}_downstream_label",),
                )
                continue
            covered: list[int] = []
            for bin_id in bin_ids:
                state = by_bin[bin_id].get("signals")
                signal_state = state.get(signal) if isinstance(state, Mapping) else None
                value = signal_state.get(transition) if isinstance(signal_state, Mapping) else None
                if not isinstance(value, bool):
                    raise ValueError(
                        f"harness funnel {signal}/{transition}/{bin_id} must be boolean"
                    )
                if value:
                    covered.append(bin_id)
            current = set(covered)
            if previous is not None and not current <= previous:
                raise ValueError(
                    f"harness funnel transition is not cumulative for {signal}/{transition}"
                )
            previous = current
            signals.setdefault(signal, {})[transition] = CountRate(
                unit_id=f"{signal}.{transition}",
                numerator=len(covered),
                denominator=len(bin_ids),
                value=len(covered) / len(bin_ids),
                status=MEASURED,
                numerator_unit_ids=tuple(str(value) for value in covered),
                denominator_unit_ids=tuple(str(value) for value in bin_ids),
            )

    reason_bins = {reason: [] for reason in HARNESS_WITHHOLDING_REASONS}
    delivered: list[int] = []
    for bin_id in bin_ids:
        reason = by_bin[bin_id].get("withholding_reason")
        is_delivered = by_bin[bin_id].get("delivered")
        if not isinstance(is_delivered, bool):
            raise ValueError(f"harness funnel delivered/{bin_id} must be boolean")
        if is_delivered:
            if reason is not None:
                raise ValueError(f"delivered harness bin {bin_id} has a withholding reason")
            delivered.append(bin_id)
            continue
        if reason not in HARNESS_WITHHOLDING_REASONS:
            raise ValueError(f"harness bin {bin_id} has unsupported withholding reason: {reason}")
        reason_bins[str(reason)].append(bin_id)
    if len(delivered) + sum(map(len, reason_bins.values())) != len(bin_ids):
        raise AssertionError("harness withholding reasons must partition the denominator")

    return HarnessDeliveryFunnel(
        definition_id=definition_id,
        denominator=len(bin_ids),
        denominator_unit="transcript_segment_eligible_canonical_one_second_bins",
        denominator_bin_ids=bin_ids,
        signals=signals,
        withholding_reason_counts={reason: len(reason_bins[reason]) for reason in reason_bins},
        withholding_bin_ids={reason: tuple(reason_bins[reason]) for reason in reason_bins},
        delivered_bin_ids=tuple(delivered),
        aggregation_trace=tuple(str(value) for value in bin_ids),
        n=len(bin_ids),
    )


@dataclass(frozen=True)
class EvidenceDistribution:
    """Raw, exhaustive P6 counts over valid M-condition moments."""

    raw_bucket_counts: Mapping[str, int]
    bucket_by_moment_id: Mapping[str, str]
    valid_moment_count: int
    invalid_moment_ids: tuple[str, ...]
    cross_modal_moment_count: int
    definition_id: str = "METRIC-T4-EVIDENCE-DISTRIBUTION-001"
    aggregation_trace: tuple[str, ...] = ()
    n: int = 0
    status: str = MEASURED


def compute_evidence_distribution(
    moments: Sequence[Mapping[str, object]],
    *,
    paper_mode: bool = True,
) -> EvidenceDistribution:
    """Partition valid M moments from resolved citations into exactly four P6 buckets.

    Free text is ignored. A moment is invalid for this metric if a citation is invalid, a
    resolved modality is outside the signed four-modality vocabulary, or no resolved verbal
    context citation exists. Every valid moment must satisfy exactly one bucket predicate.
    """
    _require_metric_definition("METRIC-T4-EVIDENCE-DISTRIBUTION-001", paper_mode=paper_mode)
    counts = {bucket: 0 for bucket in EVIDENCE_BUCKETS}
    bucket_by_moment: dict[str, str] = {}
    invalid_moment_ids: list[str] = []
    seen_ids: set[str] = set()
    for moment in moments:
        moment_id = moment.get("moment_id")
        if not isinstance(moment_id, str) or not moment_id:
            raise ValueError("evidence-distribution moments require a moment_id")
        if moment_id in seen_ids:
            raise ValueError(f"duplicate moment_id in evidence distribution: {moment_id}")
        seen_ids.add(moment_id)

        resolved = moment.get("resolved_evidence")
        invalid_ids = moment.get("invalid_evidence_ids")
        if (
            moment.get("citations_valid") is not True
            or not isinstance(invalid_ids, Sequence)
            or isinstance(invalid_ids, (str, bytes))
            or bool(invalid_ids)
            or not isinstance(resolved, Sequence)
            or isinstance(resolved, (str, bytes))
        ):
            invalid_moment_ids.append(moment_id)
            continue
        if any(not isinstance(evidence, Mapping) for evidence in resolved):
            invalid_moment_ids.append(moment_id)
            continue
        modality_values = [evidence.get("modality") for evidence in resolved]
        if any(not isinstance(modality, str) for modality in modality_values):
            invalid_moment_ids.append(moment_id)
            continue
        modalities = set(modality_values)
        if not modalities or not modalities <= set(EVIDENCE_MODALITY_CHANNEL):
            invalid_moment_ids.append(moment_id)
            continue
        channels = {EVIDENCE_MODALITY_CHANNEL[modality] for modality in modalities}
        if "verbal_context" not in channels:
            invalid_moment_ids.append(moment_id)
            continue

        has_attention = "attention" in channels
        has_scene_pose = "scene_pose" in channels
        if has_attention and has_scene_pose:
            bucket = "all_three_channels"
        elif has_attention:
            bucket = "verbal_context_plus_attention_only"
        elif has_scene_pose:
            bucket = "verbal_context_plus_scene_pose_only"
        else:
            bucket = "verbal_context_only"
        counts[bucket] += 1
        bucket_by_moment[moment_id] = bucket

    valid_count = len(bucket_by_moment)
    if sum(counts.values()) != valid_count:
        raise AssertionError("evidence buckets must exhaustively partition valid M moments")
    cross_modal_count = valid_count - counts["verbal_context_only"]
    return EvidenceDistribution(
        raw_bucket_counts=counts,
        bucket_by_moment_id=bucket_by_moment,
        valid_moment_count=valid_count,
        invalid_moment_ids=tuple(invalid_moment_ids),
        cross_modal_moment_count=cross_modal_count,
        aggregation_trace=tuple(bucket_by_moment),
        n=valid_count,
    )


def require_table3_definition(signal: str, *, paper_mode: bool = True) -> str:
    """Return the versioned Table 3 definition ID for a supported signal."""
    if signal not in TABLE3_DEFINITION_IDS:
        raise ValueError(f"unsupported Table 3 signal: {signal}")
    return TABLE3_DEFINITION_IDS[signal]


def _validated_camera_grid(
    values_by_camera: Mapping[str, Sequence[object]],
    *,
    name: str,
) -> int:
    if set(values_by_camera) != set(TABLE3_CAMERAS):
        raise ValueError(f"{name} must contain exactly {', '.join(TABLE3_CAMERAS)}")
    lengths = {len(values_by_camera[camera]) for camera in TABLE3_CAMERAS}
    if len(lengths) != 1:
        raise ValueError(f"{name} camera grids must have equal lengths")
    denominator_bins = lengths.pop()
    if denominator_bins < 1:
        raise ValueError(f"{name} must contain at least one canonical bin")
    return denominator_bins


def project_segment_assignments_to_bins(
    best_angle_artifact: Mapping[str, object],
    denominator_bins: int,
) -> tuple[tuple[tuple[str, str | None], ...], ...]:
    """Project Stage 3's fixed per-segment camera assignments onto the canonical grid.

    Each projected item is ``(transcript_segment_id, selected_camera_id)``. Empty tuples are
    intentional inter-segment bins. Overlapping speech can project more than one segment into
    a bin; the artifact order is retained and no camera is re-selected by this metric.
    """
    if denominator_bins < 1:
        raise ValueError("denominator_bins must be positive")
    segments = best_angle_artifact.get("segments")
    if not isinstance(segments, Sequence) or isinstance(segments, (str, bytes)):
        raise ValueError("best_angle_artifact.segments must be a sequence")

    projected: list[list[tuple[str, str | None]]] = [[] for _ in range(denominator_bins)]
    seen_segment_ids: set[str] = set()
    for segment in segments:
        if not isinstance(segment, Mapping):
            raise ValueError("every best-angle segment must be a mapping")
        segment_id = segment.get("transcript_segment_id")
        if not isinstance(segment_id, str) or not segment_id:
            raise ValueError("every best-angle segment needs a transcript_segment_id")
        if segment_id in seen_segment_ids:
            raise ValueError(f"duplicate best-angle segment: {segment_id}")
        seen_segment_ids.add(segment_id)

        start = float(segment.get("start_seconds", float("nan")))
        end = float(segment.get("end_seconds", float("nan")))
        if not isfinite(start) or not isfinite(end) or start < 0 or end <= start:
            raise ValueError(f"invalid interval for best-angle segment {segment_id}")
        # A segment may overshoot the grid's trailing edge: the grid spans the SHORTEST
        # stream, while speech is transcribed from cam1, and ASR can place a final word end
        # slightly past the audio it decoded. Such a segment is scored over its intersection
        # with the grid, which is the same rule every interior segment already follows.
        # A segment starting at or after the grid is different — it has no intersection to
        # score and cannot be a rounding effect, so it still fails loudly.
        if start >= denominator_bins:
            raise ValueError(f"best-angle segment {segment_id} is outside the canonical grid")
        end = min(end, float(denominator_bins))

        camera = segment.get("selected_camera_id")
        if camera is not None and camera not in TABLE3_CAMERAS:
            raise ValueError(f"unsupported selected camera for {segment_id}: {camera}")
        first_bin = floor(start)
        last_bin = min(denominator_bins - 1, ceil(end) - 1)
        for bin_index in range(first_bin, last_bin + 1):
            if start < bin_index + 1 and bin_index < end:
                projected[bin_index].append((segment_id, camera))
    return tuple(tuple(items) for items in projected)


def _frame_gate_bins_by_segment(
    best_angle_artifact: Mapping[str, object],
    asd_artifacts_by_camera: Mapping[str, Mapping[str, object] | None],
    denominator_bins: int,
) -> dict[str, frozenset[int]]:
    """Apply Stage 4 to frame-level scores for each artifact-assigned camera and track."""
    if set(asd_artifacts_by_camera) != set(TABLE3_CAMERAS):
        raise ValueError(
            f"asd_artifacts_by_camera must contain exactly {', '.join(TABLE3_CAMERAS)}"
        )
    result: dict[str, frozenset[int]] = {}
    for segment in best_angle_artifact["segments"]:  # validated by projection above
        segment_id = segment["transcript_segment_id"]
        start = float(segment["start_seconds"])
        end = float(segment["end_seconds"])
        camera = segment.get("selected_camera_id")
        track_id = segment.get("selected_track_id")
        if camera is None:
            if track_id is not None:
                raise ValueError(f"segment {segment_id} has a track without a selected camera")
            result[segment_id] = frozenset()
            continue
        if not isinstance(track_id, str) or not track_id:
            raise ValueError(f"segment {segment_id} needs its Stage 3 selected_track_id")
        camera_artifact = asd_artifacts_by_camera[camera]
        if camera_artifact is None:
            result[segment_id] = frozenset()
            continue
        tracks = camera_artifact.get("tracks")
        if not isinstance(tracks, Sequence) or isinstance(tracks, (str, bytes)):
            raise ValueError(f"ASD tracks must be a sequence for {camera}")
        matching_tracks = [track for track in tracks if track.get("track_id") == track_id]
        if len(matching_tracks) > 1:
            raise ValueError(f"duplicate ASD track {track_id} on {camera}")
        samples = matching_tracks[0].get("samples", ()) if matching_tracks else ()
        if not isinstance(samples, Sequence) or isinstance(samples, (str, bytes)):
            raise ValueError(f"ASD samples must be a sequence for {track_id}")
        passed: set[int] = set()
        for sample in samples:
            if not isinstance(sample, Mapping):
                raise ValueError(f"ASD samples must be mappings for {segment_id}")
            timestamp = float(sample.get("aligned_timestamp_seconds", float("nan")))
            if not isfinite(timestamp):
                raise ValueError(f"non-finite ASD timestamp for {segment_id}")
            if not start <= timestamp < end:
                continue
            score_value = sample.get("score")
            score = None if score_value is None else float(score_value)
            if score is not None and not isfinite(score):
                raise ValueError(f"non-finite frame-level ASD score for {segment_id}")
            gate_passed = score is not None and score > TABLE3_LINK_THRESHOLD
            if gate_passed:
                bin_index = floor(timestamp)
                if not 0 <= bin_index < denominator_bins:
                    raise ValueError(f"ASD timestamp outside canonical grid for {segment_id}")
                passed.add(bin_index)
        result[segment_id] = frozenset(passed)
    return result


def compute_table3_coverage(
    signal: str,
    signal_present_by_camera: Mapping[str, Sequence[bool] | None],
    best_angle_artifact: Mapping[str, object],
    asd_artifacts_by_camera: Mapping[str, Mapping[str, object] | None],
    *,
    signal_present_by_camera_track: Mapping[str, Mapping[str, Sequence[bool]]] | None = None,
    paper_mode: bool = True,
) -> Table3Coverage | UnavailableMetric:
    """Compute Best Cam, any-camera Union, and gated Selected coverage.

    ``signal_present_by_camera`` uses the signal-specific predicate on the shared canonical
    grid. Stage 3 camera choice and Stage 4 frame decisions come directly from
    ``best_angle_artifact``; this function never recomputes a camera argmax. It then looks up
    frame-level scores for the artifact's selected camera and selected track in
    ``asd_artifacts_by_camera`` and applies the strict-positive gate. An unrelated positive
    ASD track can therefore contribute to Union without selecting or opening a downstream
    gate. Inter-segment bins remain in the denominator and fail Selected closed, preserving
    the one shared session-duration grid for Best Cam, Union, and Selected.
    """
    definition_id = require_table3_definition(signal, paper_mode=paper_mode)
    unknown_cameras = set(signal_present_by_camera) - set(TABLE3_CAMERAS)
    if unknown_cameras:
        raise ValueError(f"unsupported signal cameras: {sorted(unknown_cameras)}")
    missing_cameras = tuple(
        camera
        for camera in TABLE3_CAMERAS
        if signal_present_by_camera.get(camera) is None or asd_artifacts_by_camera.get(camera) is None
    )
    if missing_cameras:
        return UnavailableMetric(
            definition_id, UNAVAILABLE, "camera acquisition or row dependency missing/failed",
            missing_cameras,
        )
    denominator_bins = _validated_camera_grid(
        signal_present_by_camera, name="signal_present_by_camera"  # type: ignore[arg-type]
    )

    per_camera = {
        camera: frozenset(
            bin_index
            for bin_index, present in enumerate(signal_present_by_camera[camera])
            if bool(present)
        )
        for camera in TABLE3_CAMERAS
    }
    best_camera = max(TABLE3_CAMERAS, key=lambda camera: len(per_camera[camera]))
    union_bins = frozenset().union(*(per_camera[camera] for camera in TABLE3_CAMERAS))
    projected_segments = project_segment_assignments_to_bins(best_angle_artifact, denominator_bins)
    gate_bins_by_segment = _frame_gate_bins_by_segment(
        best_angle_artifact, asd_artifacts_by_camera, denominator_bins
    )
    inter_segment_bins = frozenset(
        bin_index for bin_index, assignments in enumerate(projected_segments) if not assignments
    )
    gate_passed_bins = frozenset(
        bin_index
        for bin_index, assignments in enumerate(projected_segments)
        if any(
            camera is not None and bin_index in gate_bins_by_segment[segment_id]
            for segment_id, camera in assignments
        )
    )
    # Selected means the SELECTED track carried the signal. Testing per_camera here asked
    # only whether SOME track on the assigned camera had it, so another person standing in
    # frame could satisfy the selected speaker's coverage. When a per-track map is supplied
    # the selected track is required; without one this falls back to the camera-level test
    # and the column is reported as camera-level rather than track-level.
    selected_track_by_segment = {
        segment["transcript_segment_id"]: segment.get("selected_track_id")
        for segment in best_angle_artifact["segments"]  # validated by projection above
    }

    def _selected_track_has_signal(segment_id: str, camera: str, bin_index: int) -> bool:
        if signal_present_by_camera_track is None:
            return bin_index in per_camera[camera]
        track_id = selected_track_by_segment.get(segment_id)
        if not track_id:
            return False
        bins = (signal_present_by_camera_track.get(camera) or {}).get(track_id)
        return bool(bins) and bin_index < len(bins) and bool(bins[bin_index])

    selected_bins = frozenset(
        bin_index
        for bin_index, assignments in enumerate(projected_segments)
        if any(
            camera is not None
            and bin_index in gate_bins_by_segment[segment_id]
            and _selected_track_has_signal(segment_id, camera, bin_index)
            for segment_id, camera in assignments
        )
    )
    gate_failed_bins = frozenset(range(denominator_bins)) - inter_segment_bins - gate_passed_bins

    if not selected_bins <= union_bins:
        raise AssertionError("Table 3 invariant violated: Selected must be a subset of Union")

    return Table3Coverage(
        definition_id=definition_id,
        signal=signal,
        denominator_bins=denominator_bins,
        per_camera_covered_bins=per_camera,
        best_camera_id=best_camera,
        best_camera_covered_bins=per_camera[best_camera],
        union_covered_bins=union_bins,
        selected_covered_bins=selected_bins,
        selected_segments_by_bin=projected_segments,
        selected_gate_passed_bins=gate_passed_bins,
        selected_gate_failed_bins=gate_failed_bins,
        inter_segment_bins=inter_segment_bins,
        aggregation_trace=tuple(str(index) for index in range(denominator_bins)),
        n=denominator_bins,
    )


def compute_moment_counts(
    session_ids: Sequence[str],
    moments_by_condition: Mapping[str, Mapping[str, Sequence[Mapping[str, object]] | None]],
    *,
    paper_mode: bool = True,
) -> MomentCountMetric:
    """Count validated K/T/M records per session and aggregate without session weighting."""
    definition_id = "METRIC-T4-MOMENT-COUNT-001"
    _require_metric_definition(definition_id, paper_mode=paper_mode)
    sessions = _validate_ids(session_ids, name="session_ids")
    if set(moments_by_condition) != {"K", "T", "M"}:
        raise ValueError("moments_by_condition must contain exactly K, T, and M")
    aggregates: dict[str, AggregateMetric] = {}
    for condition in ("K", "T", "M"):
        units: list[CountRate] = []
        supplied = moments_by_condition[condition]
        unknown = set(supplied) - set(sessions)
        if unknown:
            raise ValueError(f"unknown {condition} session IDs: {sorted(unknown)}")
        for session_id in sessions:
            records = supplied.get(session_id)
            if records is None:
                units.append(
                    CountRate(session_id, None, None, None, UNAVAILABLE, "missing condition artifact")
                )
                continue
            validated = _validated_moments(records, session_id=session_id)
            ids = tuple(_record_id(record) for record in validated)
            units.append(
                CountRate(
                    session_id,
                    len(validated),
                    1,
                    float(len(validated)),
                    MEASURED,
                    numerator_unit_ids=ids,
                    denominator_unit_ids=(session_id,),
                )
            )
        aggregates[condition] = _aggregate(definition_id, units)
    return MomentCountMetric(definition_id=definition_id, by_condition=aggregates)


def compute_category_diversity(
    condition: str,
    session_ids: Sequence[str],
    moments_by_session: Mapping[str, Sequence[Mapping[str, object]] | None],
    taxonomy: Sequence[str],
    *,
    paper_mode: bool = True,
) -> DiversityMetric:
    """Count distinct focal categories over complete T or M session artifacts."""
    definition_id = "METRIC-T4-CATEGORY-DIVERSITY-001"
    _require_metric_definition(definition_id, paper_mode=paper_mode)
    if condition not in {"T", "M"}:
        raise ValueError("focal-category diversity is defined only for T and M")
    sessions = _validate_ids(session_ids, name="session_ids")
    category_ids = _validate_ids(taxonomy, name="taxonomy")
    if len(category_ids) != 7:
        raise ValueError("T/M focal taxonomy must contain exactly seven categories")
    missing = tuple(session for session in sessions if moments_by_session.get(session) is None)
    if missing:
        return DiversityMetric(
            definition_id=definition_id,
            condition=condition,
            distinct_categories=None,
            taxonomy_categories=len(category_ids),
            value=None,
            category_ids=(),
            aggregation_trace=tuple(session for session in sessions if session not in missing),
            n=len(sessions) - len(missing),
            status=UNAVAILABLE,
            missing_session_ids=missing,
        )
    used: set[str] = set()
    moment_ids: list[str] = []
    for session_id in sessions:
        for moment in _validated_moments(moments_by_session[session_id] or (), session_id=session_id):
            category = moment.get("category")
            if category not in category_ids:
                raise ValueError(f"moment {_record_id(moment)} has a category outside the taxonomy")
            used.add(str(category))
            moment_ids.append(_record_id(moment))
    return DiversityMetric(
        definition_id=definition_id,
        condition=condition,
        distinct_categories=len(used),
        taxonomy_categories=len(category_ids),
        value=len(used) / len(category_ids),
        category_ids=tuple(sorted(used)),
        aggregation_trace=tuple(moment_ids),
        n=len(sessions),
        status=MEASURED,
    )


def _strict_overlap(left: Mapping[str, object], right: Mapping[str, object]) -> bool:
    return max(float(left["start_seconds"]), float(right["start_seconds"])) < min(
        float(left["end_seconds"]), float(right["end_seconds"])
    )


def compute_directional_overlap(
    source_condition: str,
    target_condition: str,
    session_ids: Sequence[str],
    source_by_session: Mapping[str, Sequence[Mapping[str, object]] | None],
    target_by_session: Mapping[str, Sequence[Mapping[str, object]] | None],
    *,
    paper_mode: bool = True,
) -> DirectionalOverlap:
    """Pool source moments, matching strictly only against target moments in their session."""
    definition_id = "METRIC-T4-DIRECTIONAL-OVERLAP-001"
    _require_metric_definition(definition_id, paper_mode=paper_mode)
    sessions = _validate_ids(session_ids, name="session_ids")
    missing = tuple(
        session
        for session in sessions
        if source_by_session.get(session) is None or target_by_session.get(session) is None
    )
    if missing:
        return DirectionalOverlap(
            definition_id, source_condition, target_condition, None, None, None, (), (),
            sessions, missing, 0, UNAVAILABLE,
        )
    source_ids: list[str] = []
    overlapping_ids: list[str] = []
    for session_id in sessions:
        sources = _validated_moments(source_by_session[session_id] or (), session_id=session_id)
        targets = _validated_moments(target_by_session[session_id] or (), session_id=session_id)
        for source in sources:
            moment_id = _record_id(source)
            source_ids.append(moment_id)
            if any(_strict_overlap(source, target) for target in targets):
                overlapping_ids.append(moment_id)
    denominator = len(source_ids)
    if denominator == 0:
        return DirectionalOverlap(
            definition_id, source_condition, target_condition, 0, 0, None,
            (), (), sessions, (), len(sessions), UNAVAILABLE,
        )
    numerator = len(overlapping_ids)
    return DirectionalOverlap(
        definition_id=definition_id,
        source_condition=source_condition,
        target_condition=target_condition,
        numerator=numerator,
        denominator=denominator,
        value=numerator / denominator,
        overlapping_moment_ids=tuple(overlapping_ids),
        source_moment_ids=tuple(source_ids),
        session_ids=sessions,
        missing_session_ids=(),
        n=len(sessions),
        status=MEASURED,
    )


def compute_symmetric_overlap(
    left_condition: str,
    right_condition: str,
    session_ids: Sequence[str],
    left_by_session: Mapping[str, Sequence[Mapping[str, object]] | None],
    right_by_session: Mapping[str, Sequence[Mapping[str, object]] | None],
    *,
    paper_mode: bool = True,
) -> SymmetricOverlap:
    """Average both pooled directional percentages without changing their denominators."""
    definition_id = "METRIC-T4-SYMMETRIC-OVERLAP-001"
    _require_metric_definition(definition_id, paper_mode=paper_mode)
    forward = compute_directional_overlap(
        left_condition, right_condition, session_ids, left_by_session, right_by_session,
        paper_mode=paper_mode,
    )
    reverse = compute_directional_overlap(
        right_condition, left_condition, session_ids, right_by_session, left_by_session,
        paper_mode=paper_mode,
    )
    if forward.value is None or reverse.value is None:
        value = None
        status = UNAVAILABLE
        n = 0
    else:
        value = (forward.value + reverse.value) / 2
        status = MEASURED
        n = len(_validate_ids(session_ids, name="session_ids"))
    return SymmetricOverlap(
        definition_id=definition_id,
        left_to_right=forward,
        right_to_left=reverse,
        value=value,
        aggregation_trace=(
            f"{left_condition}->{right_condition}", f"{right_condition}->{left_condition}"
        ),
        n=n,
        status=status,
    )


def compute_m_only(
    session_ids: Sequence[str],
    t_by_session: Mapping[str, Sequence[Mapping[str, object]] | None],
    m_by_session: Mapping[str, Sequence[Mapping[str, object]] | None],
    *,
    paper_mode: bool = True,
) -> MOnlyMetric:
    """Count M moments with no strict same-session overlap with a T moment."""
    definition_id = "METRIC-T4-M-ONLY-001"
    _require_metric_definition(definition_id, paper_mode=paper_mode)
    sessions = _validate_ids(session_ids, name="session_ids")
    missing = tuple(
        session
        for session in sessions
        if t_by_session.get(session) is None or m_by_session.get(session) is None
    )
    if missing:
        return MOnlyMetric(definition_id, None, None, None, (), (), sessions, missing, 0, UNAVAILABLE)
    all_m: list[str] = []
    m_only: list[str] = []
    for session_id in sessions:
        t_moments = _validated_moments(t_by_session[session_id] or (), session_id=session_id)
        m_moments = _validated_moments(m_by_session[session_id] or (), session_id=session_id)
        for moment in m_moments:
            moment_id = _record_id(moment)
            all_m.append(moment_id)
            if not any(_strict_overlap(moment, t_moment) for t_moment in t_moments):
                m_only.append(moment_id)
    denominator = len(all_m)
    return MOnlyMetric(
        definition_id, len(m_only), denominator,
        None if denominator == 0 else len(m_only) / denominator,
        tuple(m_only), tuple(all_m), sessions, (), len(sessions), MEASURED,
    )


def compute_cross_modal_share(
    moments: Sequence[Mapping[str, object]], *, paper_mode: bool = True
) -> AggregateMetric:
    """Derive the valid-M cross-modal share only from the canonical evidence partition."""
    definition_id = "METRIC-T4-CROSS-MODAL-001"
    _require_metric_definition(definition_id, paper_mode=paper_mode)
    distribution = compute_evidence_distribution(moments, paper_mode=paper_mode)
    valid_ids = tuple(distribution.bucket_by_moment_id)
    cross_modal_ids = tuple(
        moment_id
        for moment_id, bucket in distribution.bucket_by_moment_id.items()
        if bucket != "verbal_context_only"
    )
    denominator = distribution.valid_moment_count
    unit = CountRate(
        "valid-M-moments",
        distribution.cross_modal_moment_count,
        denominator,
        None if denominator == 0 else distribution.cross_modal_moment_count / denominator,
        MEASURED if denominator else UNAVAILABLE,
        None if denominator else "no valid M moments",
        cross_modal_ids,
        valid_ids,
    )
    value = unit.value
    return AggregateMetric(
        definition_id, (unit,), valid_ids, denominator, value, None,
        None if value is None else _round_half_up(value), None,
        MEASURED if denominator else UNAVAILABLE,
    )


def compute_monly_visual_share(
    m_only_moments: Sequence[Mapping[str, object]], *, paper_mode: bool = True
) -> AggregateMetric:
    """Apply the canonical cross-modal predicate to the M-only subset."""
    definition_id = "METRIC-T4-MONLY-VISUAL-001"
    _require_metric_definition(definition_id, paper_mode=paper_mode)
    distribution = compute_evidence_distribution(m_only_moments, paper_mode=paper_mode)
    valid_ids = tuple(distribution.bucket_by_moment_id)
    numerator_ids = tuple(
        moment_id
        for moment_id, bucket in distribution.bucket_by_moment_id.items()
        if bucket != "verbal_context_only"
    )
    denominator = distribution.valid_moment_count
    unit = CountRate(
        "valid-M-only-moments", len(numerator_ids), denominator,
        None if denominator == 0 else len(numerator_ids) / denominator,
        MEASURED if denominator else UNAVAILABLE,
        None if denominator else "no valid M-only moments",
        numerator_ids, valid_ids, excluded_unit_ids=distribution.invalid_moment_ids,
    )
    value = unit.value
    return AggregateMetric(
        definition_id, (unit,), valid_ids, denominator, value, None,
        None if value is None else _round_half_up(value), None,
        MEASURED if denominator else UNAVAILABLE,
    )


def compute_camera_selection_distribution(
    session_ids: Sequence[str],
    best_angle_by_session: Mapping[str, Mapping[str, object] | None],
    *,
    paper_mode: bool = True,
) -> Mapping[str, AggregateMetric]:
    """Report each camera and no-selection as unweighted per-session segment proportions."""
    definition_id = "METRIC-T3-CAMERA-SELECTION-001"
    _require_metric_definition(definition_id, paper_mode=paper_mode)
    sessions = _validate_ids(session_ids, name="session_ids")
    by_label: dict[str, list[CountRate]] = {camera: [] for camera in TABLE3_CAMERAS}
    by_label["no_selection"] = []
    for session_id in sessions:
        artifact = best_angle_by_session.get(session_id)
        if artifact is None:
            for label in by_label:
                by_label[label].append(
                    CountRate(session_id, None, None, None, UNAVAILABLE, "missing session artifact")
                )
            continue
        segments = artifact.get("segments")
        cameras_status = artifact.get("camera_status")
        if not isinstance(segments, Sequence) or isinstance(segments, (str, bytes)):
            raise ValueError("best-angle segments must be a sequence")
        if not isinstance(cameras_status, Mapping) or any(
            cameras_status.get(camera) != "complete" for camera in TABLE3_CAMERAS
        ):
            for label in by_label:
                by_label[label].append(
                    CountRate(session_id, None, None, None, UNAVAILABLE, "camera missing or failed")
                )
            continue
        ids: list[str] = []
        selected: dict[str, list[str]] = {label: [] for label in by_label}
        for segment in segments:
            if not isinstance(segment, Mapping):
                raise ValueError("best-angle segment must be a mapping")
            segment_id = segment.get("transcript_segment_id")
            if not isinstance(segment_id, str) or not segment_id or segment_id in ids:
                raise ValueError("best-angle segments require unique IDs")
            ids.append(segment_id)
            camera = segment.get("selected_camera_id")
            label = "no_selection" if camera is None else camera
            if label not in selected:
                raise ValueError(f"unsupported selected camera: {camera}")
            selected[label].append(segment_id)
        for label in by_label:
            denominator = len(ids)
            by_label[label].append(
                CountRate(
                    session_id, len(selected[label]), denominator,
                    None if denominator == 0 else len(selected[label]) / denominator,
                    MEASURED if denominator else UNAVAILABLE,
                    None if denominator else "empty segment population",
                    tuple(selected[label]), tuple(ids),
                )
            )
    return {label: _aggregate(definition_id, units) for label, units in by_label.items()}


def _context_present(window: Mapping[str, object], field: str) -> bool:
    context = window.get("context")
    if not isinstance(context, Mapping):
        raise ValueError("context window requires context")
    coverage = context.get("modality_coverage")
    if not isinstance(coverage, Mapping) or not isinstance(coverage.get(field), Mapping):
        raise ValueError(f"context window lacks modality_coverage.{field}")
    entry = coverage[field]
    return entry.get("present") is True and entry.get("delivered") is True


def _compute_context_coverage(
    definition_id: str,
    coverage_field: str,
    session_ids: Sequence[str],
    session_ends: Mapping[str, float | None],
    windows_by_session: Mapping[str, Sequence[Mapping[str, object]] | None],
    *,
    paper_mode: bool,
) -> AggregateMetric:
    _require_metric_definition(definition_id, paper_mode=paper_mode)
    sessions = _validate_ids(session_ids, name="session_ids")
    units: list[CountRate] = []
    for session_id in sessions:
        end_value = session_ends.get(session_id)
        windows = windows_by_session.get(session_id)
        if end_value is None or windows is None:
            units.append(CountRate(session_id, None, None, None, UNAVAILABLE, "missing session"))
            continue
        session_end = float(end_value)
        if not isfinite(session_end) or session_end <= 0:
            raise ValueError("session end must be positive and finite")
        # POPULATION: the windows delivered to both focal conditions, as numerator
        # population and denominator alike. This once demanded a canonical 30/15 tiling of
        # the whole session, which no run can satisfy -- the assembler slides 30s and keeps
        # only flag-intersecting windows, and Stage 18 forwards only the budget-delivered
        # subset -- so the metric reported unavailable for every session.
        #
        # Reconstructing the session-wide population instead would change the experiment:
        # overlapping windows duplicate evidence, prompt cost and ranking shift, a
        # different set fits the budget, and the T/M prompt hashes move. This measures
        # modality availability inside the context actually exposed to the model. It is
        # conditional on selection and is NOT session-wide sensing coverage.
        seen: set[tuple[float, float]] = set()
        for window in windows:
            interval = (float(window["start_seconds"]), float(window["end_seconds"]))
            if interval in seen:
                raise ValueError(f"duplicate delivered window interval in {session_id}")
            seen.add(interval)
        if not windows:
            units.append(
                CountRate(
                    session_id, None, 0, None, UNAVAILABLE,
                    "no windows were delivered to the focal conditions",
                )
            )
            continue
        denominator_ids = tuple(str(window.get("window_id")) for window in windows)
        numerator_ids = tuple(
            str(window.get("window_id")) for window in windows
            if _context_present(window, coverage_field)
        )
        units.append(
            CountRate(
                session_id, len(numerator_ids), len(windows),
                len(numerator_ids) / len(windows),
                MEASURED, numerator_unit_ids=numerator_ids,
                denominator_unit_ids=denominator_ids,
            )
        )
    return _aggregate(definition_id, units)


def compute_transcript_context_coverage(
    session_ids: Sequence[str], session_ends: Mapping[str, float | None],
    windows_by_session: Mapping[str, Sequence[Mapping[str, object]] | None], *,
    paper_mode: bool = True,
) -> AggregateMetric:
    return _compute_context_coverage(
        "METRIC-COVERAGE-TRANSCRIPT-001", "transcript", session_ids, session_ends,
        windows_by_session, paper_mode=paper_mode,
    )


def compute_scene_context_coverage(
    session_ids: Sequence[str], session_ends: Mapping[str, float | None],
    windows_by_session: Mapping[str, Sequence[Mapping[str, object]] | None], *,
    paper_mode: bool = True,
) -> AggregateMetric:
    return _compute_context_coverage(
        "METRIC-COVERAGE-SCENE-001", "visual_scene", session_ids, session_ends,
        windows_by_session, paper_mode=paper_mode,
    )


def compute_attention_context_coverage(
    session_ids: Sequence[str], session_ends: Mapping[str, float | None],
    windows_by_session: Mapping[str, Sequence[Mapping[str, object]] | None], *,
    paper_mode: bool = True,
) -> AggregateMetric:
    return _compute_context_coverage(
        "METRIC-COVERAGE-ATTENTION-001", "visual_attention", session_ids, session_ends,
        windows_by_session, paper_mode=paper_mode,
    )


def _average_ranks(values: Sequence[int]) -> tuple[float, ...]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position + 1
        while end < len(order) and values[order[end]] == values[order[position]]:
            end += 1
        average = ((position + 1) + end) / 2
        for ordered_index in order[position:end]:
            ranks[ordered_index] = average
        position = end
    return tuple(ranks)


def compute_wilcoxon_signed_rank(
    session_ids: Sequence[str],
    t_counts: Mapping[str, int | None],
    m_counts: Mapping[str, int | None],
    *,
    paper_mode: bool = True,
) -> WilcoxonMetric:
    """Compute the signed exact two-sided Pratt permutation test from paired counts."""
    definition_id = "METRIC-T4-WILCOXON-001"
    _require_metric_definition(definition_id, paper_mode=paper_mode)
    sessions = _validate_ids(session_ids, name="session_ids")
    missing = tuple(
        session for session in sessions
        if t_counts.get(session) is None or m_counts.get(session) is None
    )
    pairs = tuple(
        (session, int(t_counts[session]), int(m_counts[session]))
        for session in sessions if session not in missing
    )
    if any(t < 0 or m < 0 for _, t, m in pairs):
        raise ValueError("paired moment counts must be non-negative")
    if missing:
        return WilcoxonMetric(
            definition_id, pairs, (), (), None, None, None, None, len(pairs), 0, missing,
            "two-sided", "Pratt", "exact conditional sign enumeration", UNAVAILABLE,
        )
    differences = tuple(m - t for _, t, m in pairs)
    ranks = _average_ranks(tuple(abs(value) for value in differences))
    nonzero_ranks = tuple(rank for rank, difference in zip(ranks, differences) if difference)
    w_plus = sum(rank for rank, difference in zip(ranks, differences) if difference > 0)
    w_minus = sum(rank for rank, difference in zip(ranks, differences) if difference < 0)
    statistic = min(w_plus, w_minus)
    effective_n = len(nonzero_ranks)
    if effective_n == 0:
        p_value = 1.0
    else:
        mu = sum(nonzero_ranks) / 2
        observed_distance = abs(w_plus - mu)
        extreme = 0
        total = 0
        for signs in product((False, True), repeat=effective_n):
            permuted_w_plus = sum(
                rank for rank, positive in zip(nonzero_ranks, signs) if positive
            )
            if abs(permuted_w_plus - mu) >= observed_distance:
                extreme += 1
            total += 1
        p_value = extreme / total
    return WilcoxonMetric(
        definition_id=definition_id,
        pairs=pairs,
        differences=differences,
        ranks=ranks,
        w_plus=w_plus,
        w_minus=w_minus,
        statistic=statistic,
        p_value=p_value,
        n=len(pairs),
        effective_nonzero_n=effective_n,
        missing_session_ids=(),
        alternative="two-sided",
        zero_method="Pratt",
        method="exact conditional sign enumeration",
        status=MEASURED,
    )


def _compute_clinician_metric(
    definition_id: str,
    records: Sequence[Mapping[str, object]],
    *,
    stratum: str,
    positive_label: str,
    paper_mode: bool,
) -> ClinicianMetric:
    _require_metric_definition(definition_id, paper_mode=paper_mode)
    if stratum not in {"flagged", "unflagged"} or positive_label not in {
        "critical", "not_critical"
    }:
        raise ValueError("unsupported clinician stratum or blinded label")
    denominator_ids: list[str] = []
    numerator_ids: list[str] = []
    excluded_ids: list[str] = []
    seen: set[str] = set()
    for record in records:
        interval_id = record.get("interval_id")
        if not isinstance(interval_id, str) or not interval_id or interval_id in seen:
            raise ValueError("clinician records require unique interval IDs")
        seen.add(interval_id)
        if record.get("stratum") != stratum:
            continue
        denominator_ids.append(interval_id)
        if record.get("valid") is not True:
            excluded_ids.append(interval_id)
            continue
        label = record.get("blinded_label")
        if label not in {"critical", "not_critical"}:
            excluded_ids.append(interval_id)
            continue
        if label == positive_label:
            numerator_ids.append(interval_id)
    denominator = len(denominator_ids)
    complete = denominator > 0 and not excluded_ids
    return ClinicianMetric(
        definition_id=definition_id,
        stratum=stratum,
        positive_label=positive_label,
        numerator=len(numerator_ids),
        denominator=denominator,
        value=len(numerator_ids) / denominator if complete else None,
        numerator_interval_ids=tuple(numerator_ids),
        denominator_interval_ids=tuple(denominator_ids),
        excluded_interval_ids=tuple(excluded_ids),
        aggregation_trace=tuple(denominator_ids),
        n=denominator,
        status=MEASURED if complete else UNAVAILABLE,
    )


def compute_flagged_agreement(
    records: Sequence[Mapping[str, object]], *, paper_mode: bool = True
) -> ClinicianMetric:
    return _compute_clinician_metric(
        "METRIC-CLIN-FLAGGED-AGREEMENT-001", records, stratum="flagged",
        positive_label="critical", paper_mode=paper_mode,
    )


def compute_flagged_not_critical(
    records: Sequence[Mapping[str, object]], *, paper_mode: bool = True
) -> ClinicianMetric:
    return _compute_clinician_metric(
        "METRIC-CLIN-FLAGGED-NOTCRITICAL-001", records, stratum="flagged",
        positive_label="not_critical", paper_mode=paper_mode,
    )


def compute_unflagged_agreement(
    records: Sequence[Mapping[str, object]], *, paper_mode: bool = True
) -> ClinicianMetric:
    return _compute_clinician_metric(
        "METRIC-CLIN-UNFLAGGED-AGREEMENT-001", records, stratum="unflagged",
        positive_label="not_critical", paper_mode=paper_mode,
    )


def compute_unflagged_critical(
    records: Sequence[Mapping[str, object]], *, paper_mode: bool = True
) -> ClinicianMetric:
    return _compute_clinician_metric(
        "METRIC-CLIN-UNFLAGGED-CRITICAL-001", records, stratum="unflagged",
        positive_label="critical", paper_mode=paper_mode,
    )


def compute_attention_distribution(
    interval_id: str | None,
    interval_start_seconds: float,
    interval_end_seconds: float,
    participant_ids: Sequence[str],
    samples: Sequence[Mapping[str, object]],
    *,
    paper_mode: bool = True,
) -> AttentionDistribution:
    """Compute three target counts for an explicitly identified worked-example interval.

    The historical example interval and participants remain unknown, so paper mode fails
    closed. Synthetic use is available only with explicit interval and participant IDs.
    """
    definition_id = "METRIC-EXAMPLE-ATTENTION-001"
    if paper_mode:
        raise MetricDefinitionUnresolvedError(
            f"METRIC_DEFINITION_UNRESOLVED: {definition_id} requires the exact example "
            "interval and authorized participant IDs"
        )
    if not isinstance(interval_id, str) or not interval_id:
        raise MetricDefinitionUnresolvedError(
            f"METRIC_DEFINITION_UNRESOLVED: {definition_id} requires an interval ID"
        )
    participants = _validate_ids(participant_ids, name="participant_ids")
    start = float(interval_start_seconds)
    end = float(interval_end_seconds)
    if not isfinite(start) or not isfinite(end) or start < 0 or end <= start:
        raise ValueError("worked-example interval must be finite and positive-duration")
    counts = {target: 0 for target in ATTENTION_TARGETS}
    included: list[str] = []
    excluded: list[str] = []
    seen: set[str] = set()
    for sample in samples:
        sample_id = sample.get("sample_id")
        if not isinstance(sample_id, str) or not sample_id or sample_id in seen:
            raise ValueError("attention samples require unique sample IDs")
        seen.add(sample_id)
        timestamp = float(sample.get("aligned_timestamp_seconds", float("nan")))
        participant = sample.get("participant_id")
        label = sample.get("label")
        eligible = (
            isfinite(timestamp)
            and start <= timestamp < end
            and participant in participants
            and sample.get("asd_gate_passed") is True
            and label in ATTENTION_TARGETS
        )
        if not eligible:
            excluded.append(sample_id)
            continue
        counts[str(label)] += 1
        included.append(sample_id)
    denominator = len(included)
    if denominator == 0:
        return AttentionDistribution(
            definition_id, interval_id, start, end, participants, counts, 0,
            {target: None for target in ATTENTION_TARGETS}, (), tuple(excluded), (), 0,
            UNAVAILABLE,
        )
    return AttentionDistribution(
        definition_id, interval_id, start, end, participants, counts, denominator,
        {target: counts[target] / denominator for target in ATTENTION_TARGETS},
        tuple(included), tuple(excluded), tuple(included), denominator, MEASURED,
    )


def compute_example_silence(
    interval_id: str | None,
    interval_start_seconds: float,
    interval_end_seconds: float,
    speech_intervals: Sequence[Mapping[str, object]],
    *,
    paper_mode: bool = True,
) -> SilenceMetric:
    """Find the maximal no-speech interval inside an explicitly identified example span."""
    definition_id = "METRIC-EXAMPLE-SILENCE-001"
    if paper_mode:
        raise MetricDefinitionUnresolvedError(
            f"METRIC_DEFINITION_UNRESOLVED: {definition_id} requires exact example boundaries"
        )
    if not isinstance(interval_id, str) or not interval_id:
        raise MetricDefinitionUnresolvedError(
            f"METRIC_DEFINITION_UNRESOLVED: {definition_id} requires an interval ID"
        )
    start = float(interval_start_seconds)
    end = float(interval_end_seconds)
    if not isfinite(start) or not isfinite(end) or start < 0 or end <= start:
        raise ValueError("example interval must be finite and positive-duration")
    clipped: list[tuple[float, float, str]] = []
    for record in speech_intervals:
        speech_id = record.get("speech_interval_id")
        if not isinstance(speech_id, str) or not speech_id:
            raise ValueError("speech intervals require an ID")
        speech_start = max(start, float(record["start_seconds"]))
        speech_end = min(end, float(record["end_seconds"]))
        if speech_start < speech_end:
            clipped.append((speech_start, speech_end, speech_id))
    clipped.sort()
    cursor = start
    best = (start, start)
    for speech_start, speech_end, _ in clipped:
        if speech_start - cursor > best[1] - best[0]:
            best = (cursor, speech_start)
        cursor = max(cursor, speech_end)
    if end - cursor > best[1] - best[0]:
        best = (cursor, end)
    return SilenceMetric(
        definition_id, interval_id, best[0], best[1], best[1] - best[0],
        tuple(item[2] for item in clipped), tuple(item[2] for item in clipped),
        len(clipped), MEASURED,
    )


def compute_session_count(
    session_ids: Sequence[str],
    manifests_by_session: Mapping[str, Mapping[str, object] | None],
    *,
    paper_mode: bool = True,
) -> CohortCountMetric:
    """Count unique declared sessions whose acquisition manifest is present."""
    definition_id = "METRIC-T2-SESSION-COUNT-001"
    _require_metric_definition(definition_id, paper_mode=paper_mode)
    sessions = _validate_ids(session_ids, name="session_ids")
    missing = tuple(session for session in sessions if manifests_by_session.get(session) is None)
    present = tuple(session for session in sessions if session not in missing)
    for session in present:
        if manifests_by_session[session].get("session_id") != session:
            raise ValueError(f"session manifest ID mismatch for {session}")
    return CohortCountMetric(
        definition_id, len(present), len(sessions), present, missing, present, len(present),
        MEASURED if not missing else UNAVAILABLE,
    )


def compute_scenario_distribution(
    session_ids: Sequence[str],
    manifests_by_session: Mapping[str, Mapping[str, object] | None],
    *,
    paper_mode: bool = True,
) -> CountDistributionMetric:
    """Count author-manifest scenario labels; no transcript inference is accepted."""
    definition_id = "METRIC-T2-SCENARIO-001"
    _require_metric_definition(definition_id, paper_mode=paper_mode)
    sessions = _validate_ids(session_ids, name="session_ids")
    grouped: dict[str, list[str]] = {}
    missing: list[str] = []
    for session in sessions:
        manifest = manifests_by_session.get(session)
        scenario = None if manifest is None else manifest.get("scenario_type")
        if not isinstance(scenario, str) or not scenario:
            missing.append(session)
            continue
        grouped.setdefault(scenario, []).append(session)
    trace = tuple(session for session in sessions if session not in missing)
    return CountDistributionMetric(
        definition_id, {key: len(value) for key, value in grouped.items()}, len(trace),
        {key: tuple(value) for key, value in grouped.items()}, tuple(missing), trace, len(trace),
        MEASURED if not missing else UNAVAILABLE,
    )


def compute_session_durations(
    session_ids: Sequence[str],
    manifests_by_session: Mapping[str, Mapping[str, object] | None],
    *,
    paper_mode: bool = True,
) -> DurationMetric:
    """Compute acquisition-end minus session-origin with explicit unavailable units."""
    definition_id = "METRIC-T2-DURATION-001"
    _require_metric_definition(definition_id, paper_mode=paper_mode)
    sessions = _validate_ids(session_ids, name="session_ids")
    units: list[DurationUnit] = []
    for session in sessions:
        manifest = manifests_by_session.get(session)
        if manifest is None:
            units.append(DurationUnit(session, None, None, None, UNAVAILABLE, "missing manifest"))
            continue
        origin_value = manifest.get("session_origin_seconds")
        end_value = manifest.get("acquisition_end_seconds")
        if origin_value is None or end_value is None:
            units.append(
                DurationUnit(session, None, None, None, UNAVAILABLE, "missing acquisition times")
            )
            continue
        origin = float(origin_value)
        end = float(end_value)
        if not isfinite(origin) or not isfinite(end) or end <= origin:
            raise ValueError(f"invalid acquisition interval for {session}")
        units.append(DurationUnit(session, origin, end, end - origin, MEASURED))
    measured = tuple(unit for unit in units if unit.status == MEASURED)
    values = [float(unit.duration_seconds) for unit in measured]
    return DurationMetric(
        definition_id, tuple(units), tuple(unit.session_id for unit in measured), len(measured),
        None if not values else sum(values) / len(values), _sample_std(values),
        MEASURED if measured else UNAVAILABLE,
    )


def compute_participant_counts(
    session_ids: Sequence[str],
    role_manifests_by_session: Mapping[str, Sequence[Mapping[str, object]] | None],
    *,
    paper_mode: bool = True,
) -> AggregateMetric:
    """Count unique authorized learners in each validated role manifest."""
    definition_id = "METRIC-T2-PARTICIPANTS-001"
    _require_metric_definition(definition_id, paper_mode=paper_mode)
    sessions = _validate_ids(session_ids, name="session_ids")
    units: list[CountRate] = []
    for session in sessions:
        roles = role_manifests_by_session.get(session)
        if roles is None:
            units.append(CountRate(session, None, None, None, UNAVAILABLE, "missing role manifest"))
            continue
        learner_ids = {
            record.get("participant_id")
            for record in roles
            if record.get("authorized") is True and record.get("role") == "learner"
        }
        if None in learner_ids or any(not isinstance(value, str) or not value for value in learner_ids):
            raise ValueError("authorized learner records require participant IDs")
        ordered = tuple(sorted(learner_ids))
        units.append(
            CountRate(session, len(ordered), 1, float(len(ordered)), MEASURED,
                      numerator_unit_ids=ordered, denominator_unit_ids=(session,))
        )
    return _aggregate(definition_id, units)


def compute_speaker_link_coverage(
    session_ids: Sequence[str],
    speakers_by_session: Mapping[str, Sequence[Mapping[str, object]] | None],
    *,
    paper_mode: bool = True,
) -> AggregateMetric:
    """Count fully linked identities over all positive-duration diarized speakers.

    Speaker linking is not a time-bin metric. Its denominator is the session's diarized
    speaker population; authorization metadata must not silently shrink that population.
    """
    definition_id = "METRIC-T3-SPEAKER-LINK-001"
    _require_metric_definition(definition_id, paper_mode=paper_mode)
    sessions = _validate_ids(session_ids, name="session_ids")
    results: list[CountRate] = []
    for session in sessions:
        records = speakers_by_session.get(session)
        if records is None:
            results.append(CountRate(session, None, None, None, UNAVAILABLE, "missing identity map"))
            continue
        eligible: list[str] = []
        linked: list[str] = []
        excluded: list[str] = []
        for record in records:
            speaker_id = record.get("speaker_id")
            if not isinstance(speaker_id, str) or not speaker_id:
                raise ValueError("speaker-link records require speaker IDs")
            if float(record.get("speech_duration_seconds", 0)) <= 0:
                excluded.append(speaker_id)
                continue
            status = record.get("link_status")
            if status not in {"fully_linked", "partially_linked", "unlinked"}:
                raise ValueError(f"unsupported speaker link status: {status}")
            eligible.append(speaker_id)
            if status == "fully_linked":
                linked.append(speaker_id)
        denominator = len(eligible)
        results.append(
            CountRate(
                session, len(linked), denominator,
                None if not denominator else len(linked) / denominator,
                MEASURED if denominator else UNAVAILABLE,
                None if denominator else "no eligible participant-speakers",
                tuple(linked), tuple(eligible), tuple(excluded),
            )
        )
    return _aggregate(definition_id, results)


def compute_table3_ratio(
    numerator: AggregateMetric,
    denominator: AggregateMetric,
    *,
    paper_mode: bool = True,
) -> RatioMetric:
    """Derive a Table 3 ratio from unrounded across-session means and their traces."""
    definition_id = "METRIC-T3-ASD-RATIO-001"
    _require_metric_definition(definition_id, paper_mode=paper_mode)
    common = tuple(
        unit_id for unit_id in numerator.aggregation_trace
        if unit_id in set(denominator.aggregation_trace)
    )
    if (
        numerator.mean is None or denominator.mean is None or denominator.mean == 0
        or numerator.aggregation_trace != denominator.aggregation_trace
    ):
        return RatioMetric(
            definition_id, numerator.mean, denominator.mean, None,
            numerator.aggregation_trace, denominator.aggregation_trace, len(common), UNAVAILABLE,
        )
    return RatioMetric(
        definition_id, numerator.mean, denominator.mean, numerator.mean / denominator.mean,
        numerator.aggregation_trace, denominator.aggregation_trace, len(common), MEASURED,
    )


def compute_table3_absolute_percentage_point_gap(
    comparison: str,
    minuend: AggregateMetric,
    subtrahend: AggregateMetric,
    *,
    paper_mode: bool = True,
) -> AbsolutePercentagePointGap:
    """Subtract unrounded Table 3 aggregate rates and convert once to percentage points."""
    definition_id = "METRIC-T3-ABSOLUTE-PP-GAP-001"
    _require_metric_definition(definition_id, paper_mode=paper_mode)
    common = tuple(
        unit_id for unit_id in minuend.aggregation_trace
        if unit_id in set(subtrahend.aggregation_trace)
    )
    if (
        minuend.status != MEASURED
        or subtrahend.status != MEASURED
        or minuend.mean is None
        or subtrahend.mean is None
        or minuend.aggregation_trace != subtrahend.aggregation_trace
    ):
        reasons = []
        if minuend.status != MEASURED or minuend.mean is None:
            reasons.append("minuend aggregate unavailable")
        if subtrahend.status != MEASURED or subtrahend.mean is None:
            reasons.append("subtrahend aggregate unavailable")
        if minuend.aggregation_trace != subtrahend.aggregation_trace:
            reasons.append("aggregation traces differ")
        return AbsolutePercentagePointGap(
            definition_id, comparison, minuend.mean, subtrahend.mean, None, None,
            minuend.aggregation_trace, subtrahend.aggregation_trace, len(common),
            UNAVAILABLE, "; ".join(reasons) or "required aggregate unavailable",
        )
    value = (minuend.mean - subtrahend.mean) * 100.0
    return AbsolutePercentagePointGap(
        definition_id, comparison, minuend.mean, subtrahend.mean, value,
        format(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), "f"),
        minuend.aggregation_trace, subtrahend.aggregation_trace,
        len(minuend.aggregation_trace), MEASURED,
    )


def compute_provenance_integrity(**kwargs: object) -> dict:
    """Dispatch the locked structural audit kept beside focal evidence resolution."""
    from scripts.focal.evidence import audit_provenance_integrity

    return audit_provenance_integrity(**kwargs)  # type: ignore[arg-type]


# This is the sole public dispatch table. Helpers beginning with ``_`` perform shared
# arithmetic but are not alternate metric definitions.
METRIC_DEFINITIONS: Mapping[str, Callable[..., object]] = {
    "METRIC-T2-SESSION-COUNT-001": compute_session_count,
    "METRIC-T2-SCENARIO-001": compute_scenario_distribution,
    "METRIC-T2-DURATION-001": compute_session_durations,
    "METRIC-T2-PARTICIPANTS-001": compute_participant_counts,
    "METRIC-T3-ASD-001": compute_table3_coverage,
    "METRIC-T3-FACE-001": compute_table3_coverage,
    "METRIC-T3-HEADPOSE-001": compute_table3_coverage,
    "METRIC-T3-SPEAKER-LINK-001": compute_speaker_link_coverage,
    "METRIC-T3-CAMERA-SELECTION-001": compute_camera_selection_distribution,
    "METRIC-T3-ASD-RATIO-001": compute_table3_ratio,
    "METRIC-T3-ABSOLUTE-PP-GAP-001": compute_table3_absolute_percentage_point_gap,
    "METRIC-HARNESS-DELIVERY-FUNNEL-001": compute_harness_delivery_funnel,
    "METRIC-T4-MOMENT-COUNT-001": compute_moment_counts,
    "METRIC-T4-CATEGORY-DIVERSITY-001": compute_category_diversity,
    "METRIC-T4-DIRECTIONAL-OVERLAP-001": compute_directional_overlap,
    "METRIC-T4-SYMMETRIC-OVERLAP-001": compute_symmetric_overlap,
    "METRIC-T4-M-ONLY-001": compute_m_only,
    "METRIC-T4-CROSS-MODAL-001": compute_cross_modal_share,
    "METRIC-T4-MONLY-VISUAL-001": compute_monly_visual_share,
    "METRIC-T4-EVIDENCE-DISTRIBUTION-001": compute_evidence_distribution,
    "METRIC-T4-PROVENANCE-INTEGRITY-001": compute_provenance_integrity,
    "METRIC-T4-WILCOXON-001": compute_wilcoxon_signed_rank,
    "METRIC-CLIN-FLAGGED-AGREEMENT-001": compute_flagged_agreement,
    "METRIC-CLIN-FLAGGED-NOTCRITICAL-001": compute_flagged_not_critical,
    "METRIC-CLIN-UNFLAGGED-AGREEMENT-001": compute_unflagged_agreement,
    "METRIC-CLIN-UNFLAGGED-CRITICAL-001": compute_unflagged_critical,
    "METRIC-COVERAGE-TRANSCRIPT-001": compute_transcript_context_coverage,
    "METRIC-COVERAGE-SCENE-001": compute_scene_context_coverage,
    "METRIC-COVERAGE-ATTENTION-001": compute_attention_context_coverage,
    "METRIC-EXAMPLE-ATTENTION-001": compute_attention_distribution,
    "METRIC-EXAMPLE-SILENCE-001": compute_example_silence,
}
