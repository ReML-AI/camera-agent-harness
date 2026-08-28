from itertools import product
from math import sqrt

import pytest

from scripts.core.errors import MetricDefinitionUnresolvedError
from scripts.metrics.definitions import (
    MEASURED,
    METRIC_DEFINITIONS,
    UNAVAILABLE,
    compute_attention_context_coverage,
    compute_attention_distribution,
    compute_camera_selection_distribution,
    compute_category_diversity,
    compute_cross_modal_share,
    compute_evidence_distribution,
    compute_directional_overlap,
    compute_flagged_agreement,
    compute_flagged_not_critical,
    compute_harness_delivery_funnel,
    compute_m_only,
    compute_monly_visual_share,
    compute_moment_counts,
    compute_participant_counts,
    compute_scene_context_coverage,
    compute_scenario_distribution,
    compute_session_count,
    compute_session_durations,
    compute_speaker_link_coverage,
    compute_symmetric_overlap,
    compute_transcript_context_coverage,
    compute_table3_ratio,
    compute_table3_absolute_percentage_point_gap,
    compute_table3_coverage,
    compute_unflagged_agreement,
    compute_unflagged_critical,
    compute_wilcoxon_signed_rank,
)


def moment(moment_id, start, end, category="a", **extra):
    return {
        "moment_id": moment_id,
        "start_seconds": start,
        "end_seconds": end,
        "category": category,
        **extra,
    }


def evidence_moment(moment_id, *modalities):
    return moment(
        moment_id,
        0,
        1,
        citations_valid=True,
        invalid_evidence_ids=[],
        resolved_evidence=[
            {"evidence_id": f"{moment_id}-{index}", "modality": modality}
            for index, modality in enumerate(modalities)
        ],
    )


def context_window(window_id, start, end, transcript, scene, attention):
    def entry(present):
        return {"present": present, "delivered": True, "evidence_ids": []}

    return {
        "window_id": window_id,
        "start_seconds": start,
        "end_seconds": end,
        "context": {
            "modality_coverage": {
                "transcript": entry(transcript),
                "visual_scene": entry(scene),
                "visual_attention": entry(attention),
            }
        },
    }


def test_definition_registry_has_one_callable_for_every_phase7_metric():
    expected = {
        "METRIC-T2-SESSION-COUNT-001",
        "METRIC-T2-SCENARIO-001",
        "METRIC-T2-DURATION-001",
        "METRIC-T2-PARTICIPANTS-001",
        "METRIC-T3-SPEAKER-LINK-001",
        "METRIC-T3-CAMERA-SELECTION-001",
        "METRIC-T3-ASD-RATIO-001",
        "METRIC-T3-ABSOLUTE-PP-GAP-001",
        "METRIC-T4-MOMENT-COUNT-001",
        "METRIC-T4-CATEGORY-DIVERSITY-001",
        "METRIC-T4-DIRECTIONAL-OVERLAP-001",
        "METRIC-T4-SYMMETRIC-OVERLAP-001",
        "METRIC-T4-M-ONLY-001",
        "METRIC-T4-CROSS-MODAL-001",
        "METRIC-T4-MONLY-VISUAL-001",
        "METRIC-T4-EVIDENCE-DISTRIBUTION-001",
        "METRIC-T4-PROVENANCE-INTEGRITY-001",
        "METRIC-T4-WILCOXON-001",
        "METRIC-CLIN-FLAGGED-AGREEMENT-001",
        "METRIC-CLIN-FLAGGED-NOTCRITICAL-001",
        "METRIC-CLIN-UNFLAGGED-AGREEMENT-001",
        "METRIC-CLIN-UNFLAGGED-CRITICAL-001",
        "METRIC-COVERAGE-TRANSCRIPT-001",
        "METRIC-COVERAGE-SCENE-001",
        "METRIC-COVERAGE-ATTENTION-001",
        "METRIC-EXAMPLE-ATTENTION-001",
        "METRIC-HARNESS-DELIVERY-FUNNEL-001",
    }
    assert expected <= METRIC_DEFINITIONS.keys()
    assert all(callable(METRIC_DEFINITIONS[definition_id]) for definition_id in expected)


def test_harness_funnel_reasons_are_mutually_exclusive_and_exhaust_denominator():
    reasons = (
        "speaker_unlinked", "no_selected_camera_track", "no_raw_face",
        "no_scored_asd_sample", "asd_score_not_strictly_positive",
        "no_usable_head_pose", "no_valid_attention_label",
    )

    def signal_state(value):
        return {
            "eligible_union": value,
            "stage3_assigned": value,
            "selected_camera_signal": value,
            "strict_asd_gate_passed": value,
            "delivered": value,
            "valid_downstream_label_delivered": value,
        }

    records = [
        {
            "bin_id": index,
            "signals": {
                signal: signal_state(False)
                for signal in ("face", "asd", "head_pose", "attention")
            },
            "delivered": False,
            "withholding_reason": reason,
        }
        for index, reason in enumerate(reasons)
    ]
    records.append({
        "bin_id": len(reasons),
        "signals": {
            signal: signal_state(True)
            for signal in ("face", "asd", "head_pose", "attention")
        },
        "delivered": True,
        "withholding_reason": None,
    })

    result = compute_harness_delivery_funnel(records)

    assert result.denominator == 8
    assert result.delivered_bin_ids == (7,)
    assert result.withholding_reason_counts == {reason: 1 for reason in reasons}
    assert sum(result.withholding_reason_counts.values()) + len(result.delivered_bin_ids) == 8
    assert result.signals["face"]["valid_downstream_label_delivered"].status == UNAVAILABLE
    assert result.signals["asd"]["valid_downstream_label_delivered"].status == UNAVAILABLE


def test_harness_funnel_missing_inputs_are_explicitly_unavailable():
    result = compute_harness_delivery_funnel(None)
    assert result.status == UNAVAILABLE
    assert result.missing_unit_ids == ("transcript_eligible_bin_records",)


def test_table2_manifest_metrics_are_count_first_and_do_not_infer_missing_values():
    manifests = {
        "s-a": {
            "session_id": "s-a", "scenario_type": "alpha",
            "session_origin_seconds": 2, "acquisition_end_seconds": 7,
        },
        "s-b": {
            "session_id": "s-b", "scenario_type": "beta",
            "session_origin_seconds": 1, "acquisition_end_seconds": 6,
        },
    }
    cohort = compute_session_count(("s-a", "s-b", "s-c"), manifests)
    scenarios = compute_scenario_distribution(("s-a", "s-b", "s-c"), manifests)
    durations = compute_session_durations(("s-a", "s-b", "s-c"), manifests)
    participants = compute_participant_counts(
        ("s-a", "s-b"),
        {
            "s-a": [
                {"participant_id": "p1", "authorized": True, "role": "learner"},
                {"participant_id": "p1", "authorized": True, "role": "learner"},
                {"participant_id": "p2", "authorized": True, "role": "educator"},
            ],
            "s-b": [],
        },
    )

    assert (cohort.numerator, cohort.denominator, cohort.status) == (2, 3, UNAVAILABLE)
    assert cohort.missing_session_ids == ("s-c",)
    assert scenarios.raw_counts == {"alpha": 1, "beta": 1}
    assert scenarios.missing_unit_ids == ("s-c",)
    assert [unit.duration_seconds for unit in durations.units] == [5, 5, None]
    assert durations.n == 2
    assert [unit.numerator for unit in participants.units] == [1, 0]
    assert participants.units[1].status == MEASURED


def test_speaker_link_keeps_eligibility_denominator():
    link = compute_speaker_link_coverage(
        ("s",),
        {"s": [
            {"speaker_id": "a", "authorized_participant": True,
             "speech_duration_seconds": 1, "link_status": "fully_linked"},
            {"speaker_id": "b", "authorized_participant": True,
             "speech_duration_seconds": 2, "link_status": "partially_linked"},
            {"speaker_id": "c", "authorized_participant": False,
             "speech_duration_seconds": 1, "link_status": "unlinked"},
        ]},
    )
    assert (link.units[0].numerator, link.units[0].denominator) == (1, 3)
    assert link.units[0].excluded_unit_ids == ()


def test_table3_ratio_uses_unrounded_means_and_identical_session_trace():
    artifacts = {
        "a": {
            "camera_status": {"cam1": "complete", "cam2": "complete", "cam3": "complete"},
            "segments": [
                {"transcript_segment_id": "a1", "selected_camera_id": "cam1"},
                {"transcript_segment_id": "a2", "selected_camera_id": "cam2"},
            ],
        },
        "b": {
            "camera_status": {"cam1": "complete", "cam2": "complete", "cam3": "complete"},
            "segments": [
                {"transcript_segment_id": "b1", "selected_camera_id": "cam1"},
                {"transcript_segment_id": "b2", "selected_camera_id": "cam1"},
            ],
        },
    }
    distribution = compute_camera_selection_distribution(("a", "b"), artifacts)
    ratio = compute_table3_ratio(distribution["cam1"], distribution["cam2"])
    assert ratio.numerator_mean == 3 / 4
    assert ratio.denominator_mean == 1 / 4
    assert ratio.value == 3
    assert ratio.n == 2


def test_table3_absolute_gap_uses_unrounded_means_and_preserves_measured_zero():
    artifacts = {
        "a": {"camera_status": {"cam1": "complete", "cam2": "complete", "cam3": "complete"},
              "segments": [{"transcript_segment_id": "a1", "selected_camera_id": "cam1"}]},
        "b": {"camera_status": {"cam1": "complete", "cam2": "complete", "cam3": "complete"},
              "segments": [{"transcript_segment_id": "b1", "selected_camera_id": "cam2"}]},
    }
    distribution = compute_camera_selection_distribution(("a", "b"), artifacts)

    gap = compute_table3_absolute_percentage_point_gap(
        "cam1_minus_cam2", distribution["cam1"], distribution["cam2"]
    )

    assert gap.status == MEASURED
    assert gap.value_percentage_points == 0.0
    assert gap.rendered_percentage_points == "0.0"
    assert gap.n == 2


def test_moment_counts_mean_sample_std_rounding_and_measured_zero():
    inputs = {
        "K": {"s-a": [moment("k-a", 0, 1)], "s-b": [
            moment("k-b1", 0, 1), moment("k-b2", 2, 3), moment("k-b3", 4, 5)
        ]},
        "T": {"s-a": [], "s-b": [moment("t-b", 0, 1)]},
        "M": {"s-a": [moment("m-a", 0, 1)], "s-b": None},
    }
    result = compute_moment_counts(("s-a", "s-b"), inputs)

    k = result.by_condition["K"]
    assert [unit.numerator for unit in k.units] == [1, 3]
    assert k.mean == 2
    assert k.sample_std == pytest.approx(sqrt(2))
    assert (k.rendered_mean, k.rendered_sample_std, k.n) == ("2.0", "1.4", 2)
    assert result.by_condition["T"].units[0].status == MEASURED
    assert result.by_condition["T"].units[0].numerator == 0
    assert result.by_condition["M"].units[1].status == UNAVAILABLE
    assert result.by_condition["M"].n == 1


def test_decimal_display_uses_round_half_up_without_changing_unrounded_mean():
    sessions = ("a", "b", "c", "d")
    counts = (0, 1, 2, 2)
    by_session = {
        session: [moment(f"{session}-{index}", index, index + 1) for index in range(count)]
        for session, count in zip(sessions, counts)
    }
    result = compute_moment_counts(
        sessions, {"K": by_session, "T": by_session, "M": by_session}
    ).by_condition["T"]
    assert result.mean == 5 / 4
    assert result.rendered_mean == "1.3"


def test_category_diversity_counts_native_focal_categories_and_blocks_missing_session():
    taxonomy = tuple("abcdefg")
    result = compute_category_diversity(
        "T", ("s-a", "s-b"),
        {"s-a": [moment("a-1", 0, 1, "a")], "s-b": [moment("b-1", 0, 1, "c")]},
        taxonomy,
    )
    assert (result.distinct_categories, result.taxonomy_categories) == (2, 7)
    assert result.value == 2 / 7
    assert result.aggregation_trace == ("a-1", "b-1")
    assert result.n == 2

    missing = compute_category_diversity("T", ("s-a", "s-b"), {"s-a": []}, taxonomy)
    assert missing.status == UNAVAILABLE
    assert missing.missing_session_ids == ("s-b",)
    assert missing.value is None


def test_directional_overlap_uses_strict_same_session_intersection_and_raw_denominators():
    left = {
        "s-a": [moment("l-1", 0, 2), moment("l-2", 4, 5)],
        "s-b": [],
    }
    right = {
        "s-a": [
            moment("r-1", 1, 3),
            moment("r-touch", 5, 6),
            moment("r-2", 4.5, 4.75),
        ],
        "s-b": [moment("r-other-session", 0, 10)],
    }
    forward = compute_directional_overlap("T", "M", ("s-a", "s-b"), left, right)
    reverse = compute_directional_overlap("M", "T", ("s-a", "s-b"), right, left)

    assert (forward.numerator, forward.denominator, forward.value) == (2, 2, 1)
    assert forward.overlapping_moment_ids == ("l-1", "l-2")
    assert (reverse.numerator, reverse.denominator) == (2, 4)
    assert "r-touch" not in reverse.overlapping_moment_ids
    assert "r-other-session" not in reverse.overlapping_moment_ids


def test_symmetric_overlap_is_order_independent_and_retains_both_directions():
    left = {"s": [moment("l", 0, 2)]}
    right = {"s": [moment("r-hit", 1, 3), moment("r-miss", 4, 5)]}
    lr = compute_symmetric_overlap("K", "T", ("s",), left, right)
    rl = compute_symmetric_overlap("T", "K", ("s",), right, left)

    # Hand calculation: (one of one + one of two) / two.
    assert lr.value == (1 + 1 / 2) / 2
    assert rl.value == lr.value
    assert (lr.left_to_right.denominator, lr.right_to_left.denominator) == (1, 2)


def test_empty_overlap_direction_and_missing_session_are_explicitly_unavailable():
    empty = compute_directional_overlap("T", "M", ("s",), {"s": []}, {"s": []})
    missing = compute_directional_overlap("T", "M", ("s",), {}, {"s": []})
    assert (empty.numerator, empty.denominator, empty.value, empty.status) == (
        0, 0, None, UNAVAILABLE
    )
    assert missing.missing_session_ids == ("s",)
    assert missing.status == UNAVAILABLE


def test_m_only_derivation_treats_boundary_touch_as_non_overlap():
    result = compute_m_only(
        ("s",),
        {"s": [moment("t", 0, 1)]},
        {"s": [moment("m-touch", 1, 2), moment("m-hit", 0.5, 0.75)]},
    )
    assert (result.numerator, result.denominator, result.value) == (1, 2, 1 / 2)
    assert result.m_only_moment_ids == ("m-touch",)


def test_cross_modal_and_monly_visual_citation_counts_are_independent():
    moments = [
        evidence_moment("verbal", "transcript"),
        evidence_moment("attention", "transcript", "visual_attention"),
        evidence_moment("scene", "speaker_dynamics", "visual_scene"),
        evidence_moment("all", "transcript", "visual_attention", "visual_scene"),
    ]
    buckets = compute_evidence_distribution(moments)
    assert buckets.raw_bucket_counts == {
        "verbal_context_only": 1,
        "verbal_context_plus_attention_only": 1,
        "verbal_context_plus_scene_pose_only": 1,
        "all_three_channels": 1,
    }
    assert sum(buckets.raw_bucket_counts.values()) == buckets.valid_moment_count

    share = compute_cross_modal_share(moments)
    unit = share.units[0]
    assert (unit.numerator, unit.denominator, unit.value) == (3, 4, 3 / 4)
    assert share.n == unit.denominator

    monly = compute_monly_visual_share(
        [
            moment("event", 0, 1, citations_valid=True, invalid_evidence_ids=[],
                   resolved_evidence=[
                       {"modality": "transcript"}, {"modality": "visual_scene"},
                   ]),
            moment("other", 2, 3, citations_valid=True, invalid_evidence_ids=[],
                   resolved_evidence=[{"modality": "transcript"}]),
            moment("invalid", 4, 5, citations_valid=False, invalid_evidence_ids=["x"],
                   resolved_evidence=[]),
        ]
    )
    assert (monly.units[0].numerator, monly.units[0].denominator) == (1, 2)


def test_camera_selection_rates_include_no_selection_and_missing_camera_status():
    artifacts = {
        "complete": {
            "camera_status": {"cam1": "complete", "cam2": "complete", "cam3": "complete"},
            "segments": [
                {"transcript_segment_id": "a", "selected_camera_id": "cam1"},
                {"transcript_segment_id": "b", "selected_camera_id": "cam1"},
                {"transcript_segment_id": "c", "selected_camera_id": None},
            ],
        },
        "failed": {
            "camera_status": {"cam1": "complete", "cam2": "failed", "cam3": "complete"},
            "segments": [],
        },
    }
    result = compute_camera_selection_distribution(("complete", "failed", "missing"), artifacts)

    assert (result["cam1"].units[0].numerator, result["cam1"].units[0].denominator) == (2, 3)
    assert result["cam2"].units[0].numerator == 0
    assert result["no_selection"].units[0].numerator == 1
    assert result["cam1"].units[1].unavailable_reason == "camera missing or failed"
    assert result["cam1"].units[2].unavailable_reason == "missing session artifact"
    assert all(metric.n == 1 for metric in result.values())


def test_table3_missing_camera_is_unavailable_not_a_surviving_camera_maximum():
    result = compute_table3_coverage(
        "asd",
        {"cam1": [True], "cam2": [False]},
        {"segments": []},
        {"cam1": {"tracks": []}, "cam2": {"tracks": []}},
    )
    assert result.status == UNAVAILABLE
    assert result.missing_unit_ids == ("cam3",)
    assert result.n == 0


def test_context_coverage_uses_all_canonical_windows_including_terminal_partial():
    windows = {
        "s": [
            context_window("w0", 0, 30, True, True, False),
            context_window("w1", 15, 31, True, False, True),
            context_window("w2", 30, 31, False, False, True),
        ],
        "missing": None,
    }
    args = (("s", "missing"), {"s": 31, "missing": None}, windows)
    transcript = compute_transcript_context_coverage(*args)
    scene = compute_scene_context_coverage(*args)
    attention = compute_attention_context_coverage(*args)

    assert (transcript.units[0].numerator, transcript.units[0].denominator) == (2, 3)
    assert (scene.units[0].numerator, scene.units[0].denominator) == (1, 3)
    assert (attention.units[0].numerator, attention.units[0].denominator) == (2, 3)
    assert transcript.units[1].status == UNAVAILABLE
    assert transcript.aggregation_trace == ("s",)
    assert transcript.n == 1


def test_context_coverage_measures_the_delivered_population_not_a_canonical_tiling():
    """Coverage is conditional on delivery, and an empty delivery is not zero coverage.

    This once required a canonical 30/15 tiling of the whole session, which no run can
    produce: the assembler slides 30s and keeps only flag-intersecting windows, and Stage
    18 forwards only the delivered subset, so every session reported unavailable.
    """
    delivered = compute_transcript_context_coverage(
        ("s",), {"s": 16}, {"s": [context_window("w0", 0, 16, True, True, True)]}
    )
    assert delivered.units[0].status == MEASURED
    assert (delivered.units[0].numerator, delivered.units[0].denominator) == (1, 1)

    # Nothing delivered means nothing to measure -- never a fabricated zero.
    empty = compute_transcript_context_coverage(("s",), {"s": 16}, {"s": []})
    assert empty.units[0].status == UNAVAILABLE
    assert empty.units[0].numerator is None
    assert empty.units[0].value is None


def test_exact_two_sided_pratt_wilcoxon_includes_zero_in_ranking():
    result = compute_wilcoxon_signed_rank(
        ("a", "b", "c"),
        {"a": 2, "b": 1, "c": 4},
        {"a": 2, "b": 2, "c": 2},
    )
    # Differences are zero, plus one, minus two. Pratt ranks are one, two, three.
    assert result.differences == (0, 1, -2)
    assert result.ranks == (1, 2, 3)
    assert (result.w_plus, result.w_minus, result.statistic) == (2, 3, 2)
    assert result.p_value == 1
    assert (result.n, result.effective_nonzero_n) == (3, 2)
    assert (result.alternative, result.zero_method) == ("two-sided", "Pratt")


def test_wilcoxon_all_zero_and_missing_pair_status():
    zero = compute_wilcoxon_signed_rank(("a", "b"), {"a": 1, "b": 2}, {"a": 1, "b": 2})
    assert (zero.statistic, zero.p_value, zero.effective_nonzero_n) == (0, 1, 0)

    missing = compute_wilcoxon_signed_rank(("a", "b"), {"a": 1, "b": 2}, {"a": 1})
    assert missing.status == UNAVAILABLE
    assert missing.missing_session_ids == ("b",)
    assert missing.n == 1


def test_clinician_strata_keep_complementary_counts_separate():
    records = [
        {"interval_id": "f-a", "stratum": "flagged", "blinded_label": "critical", "valid": True},
        {"interval_id": "f-b", "stratum": "flagged", "blinded_label": "critical", "valid": True},
        {"interval_id": "f-c", "stratum": "flagged", "blinded_label": "not_critical", "valid": True},
        {"interval_id": "u-a", "stratum": "unflagged", "blinded_label": "critical", "valid": True},
        {"interval_id": "u-b", "stratum": "unflagged", "blinded_label": "not_critical", "valid": True},
    ]
    flagged = compute_flagged_agreement(records)
    flagged_other = compute_flagged_not_critical(records)
    unflagged = compute_unflagged_agreement(records)
    unflagged_other = compute_unflagged_critical(records)

    assert (flagged.numerator, flagged.denominator) == (2, 3)
    assert (flagged_other.numerator, flagged_other.denominator) == (1, 3)
    assert flagged.excluded_interval_ids == ()
    assert (unflagged.numerator, unflagged.denominator) == (1, 2)
    assert (unflagged_other.numerator, unflagged_other.denominator) == (1, 2)
    assert flagged.numerator + flagged_other.numerator == flagged.denominator
    assert unflagged.numerator + unflagged_other.numerator == unflagged.denominator

    incomplete = compute_flagged_agreement(
        records + [
            {"interval_id": "f-x", "stratum": "flagged", "blinded_label": None, "valid": False}
        ]
    )
    assert incomplete.denominator == 4
    assert incomplete.excluded_interval_ids == ("f-x",)
    assert incomplete.status == UNAVAILABLE
    assert incomplete.value is None


def test_worked_example_attention_is_three_target_count_first_distribution():
    samples = [
        {"sample_id": "a", "participant_id": "p1", "aligned_timestamp_seconds": 1,
         "asd_gate_passed": True, "label": "patient"},
        {"sample_id": "b", "participant_id": "p2", "aligned_timestamp_seconds": 2,
         "asd_gate_passed": True, "label": "patient"},
        {"sample_id": "c", "participant_id": "p1", "aligned_timestamp_seconds": 3,
         "asd_gate_passed": True, "label": "monitor"},
        {"sample_id": "d", "participant_id": "p2", "aligned_timestamp_seconds": 4,
         "asd_gate_passed": True, "label": "person"},
        {"sample_id": "closed", "participant_id": "p1", "aligned_timestamp_seconds": 5,
         "asd_gate_passed": False, "label": "other"},
    ]
    result = compute_attention_distribution(
        "synthetic-example", 0, 5, ("p1", "p2"), samples, paper_mode=False
    )
    assert result.target_counts == {"patient": 2, "person": 1, "other": 0}
    assert result.denominator == 3
    assert result.rates == {"patient": 2 / 3, "person": 1 / 3, "other": 0}
    assert result.excluded_sample_ids == ("c", "closed")

    with pytest.raises(MetricDefinitionUnresolvedError, match="exact example interval"):
        compute_attention_distribution("arbitrary", 0, 1, ("p1",), samples)


def test_property_rates_equal_numerator_over_denominator_for_small_count_populations():
    for denominator in range(1, 6):
        for numerator in range(denominator + 1):
            records = [
                {"interval_id": f"x-{index}", "stratum": "flagged",
                 "blinded_label": "critical" if index < numerator else "not_critical",
                 "valid": True}
                for index in range(denominator)
            ]
            result = compute_flagged_agreement(records)
            assert result.value == result.numerator / result.denominator


def test_property_wilcoxon_pairs_t_and_m_in_declared_session_order():
    sessions = ("s-a", "s-b", "s-c")
    for t_values, m_values in product(product(range(2), repeat=3), repeat=2):
        t_counts = dict(zip(sessions, t_values))
        m_counts = dict(zip(sessions, m_values))
        result = compute_wilcoxon_signed_rank(sessions, t_counts, m_counts)
        assert result.pairs == tuple(
            (session, t_counts[session], m_counts[session]) for session in sessions
        )
        assert result.differences == tuple(
            m_counts[session] - t_counts[session] for session in sessions
        )


def _one_segment_artifacts(selected_track="track:cam1:1"):
    """One 2s speech segment on cam1, selected track given, ASD positive in both bins."""
    best_angles = {"segments": [{
        "transcript_segment_id": "seg-1", "start_seconds": 0.0, "end_seconds": 2.0,
        "selected_camera_id": "cam1", "selected_track_id": selected_track,
    }]}
    asd = {
        "cam1": {"tracks": [{
            "track_id": selected_track,
            "samples": [{"aligned_timestamp_seconds": 0.5, "score": 0.9},
                        {"aligned_timestamp_seconds": 1.5, "score": 0.9}],
        }]},
        "cam2": {"tracks": []}, "cam3": {"tracks": []},
    }
    return best_angles, asd


def test_selected_head_pose_rejects_another_persons_pose_on_the_same_camera():
    """Selected coverage must be the selected speaker's pose, not anyone's.

    The Selected column tested only whether SOME track on the assigned camera had a usable
    pose, so a bystander standing in frame could satisfy the selected speaker's coverage
    and inflate what the harness is said to propagate.
    """
    best_angles, asd = _one_segment_artifacts()
    presence = {"cam1": [True, True], "cam2": [False, False], "cam3": [False, False]}
    # Only a DIFFERENT track has usable pose on cam1.
    by_track = {"cam1": {"track:cam1:99": [True, True]}, "cam2": {}, "cam3": {}}

    result = compute_table3_coverage(
        "head_pose", presence, best_angles, asd,
        signal_present_by_camera_track=by_track, paper_mode=False,
    )

    assert result.selected_covered_bins == frozenset()

    # The selected track's own pose does count.
    by_track_ok = {"cam1": {"track:cam1:1": [True, True]}, "cam2": {}, "cam3": {}}
    ok = compute_table3_coverage(
        "head_pose", presence, best_angles, asd,
        signal_present_by_camera_track=by_track_ok, paper_mode=False,
    )
    assert ok.selected_covered_bins == frozenset({0, 1})
