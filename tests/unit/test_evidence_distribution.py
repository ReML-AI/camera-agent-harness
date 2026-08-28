from scripts.metrics.definitions import compute_evidence_distribution


def _moment(moment_id, *modalities, valid=True):
    return {
        "moment_id": moment_id,
        "citations_valid": valid,
        "invalid_evidence_ids": [] if valid else ["bad-id"],
        "resolved_evidence": [
            {"evidence_id": f"{moment_id}-{index}", "modality": modality}
            for index, modality in enumerate(modalities)
        ],
    }


def test_evidence_buckets_are_disjoint_exhaustive_and_count_first():
    result = compute_evidence_distribution(
        [
            _moment("verbal", "transcript"),
            _moment("attention", "speaker_dynamics", "visual_attention"),
            _moment("scene", "transcript", "visual_scene"),
            _moment("all", "transcript", "visual_attention", "visual_scene"),
            _moment("no-verbal", "visual_attention"),
            _moment("unsupported", "transcript", "modality_coverage"),
            _moment("invalid-citation", "transcript", valid=False),
        ]
    )

    assert result.raw_bucket_counts == {
        "verbal_context_only": 1,
        "verbal_context_plus_attention_only": 1,
        "verbal_context_plus_scene_pose_only": 1,
        "all_three_channels": 1,
    }
    assert sum(result.raw_bucket_counts.values()) == result.valid_moment_count == 4
    assert set(result.bucket_by_moment_id) == {"verbal", "attention", "scene", "all"}
    assert result.invalid_moment_ids == (
        "no-verbal",
        "unsupported",
        "invalid-citation",
    )
    assert result.cross_modal_moment_count == 3
