from scripts.focal.evidence import (
    TEMPORAL_RULE_ID,
    audit_provenance_integrity,
    delivered_evidence_index,
    validate_citations,
)
from tests.test_multimodal_windows import sample_window


def test_t_index_excludes_visual_evidence_but_includes_coverage():
    window = sample_window()
    index = delivered_evidence_index([window], "T")
    assert "transcript-1" in index
    assert "dynamics-1" in index
    assert "coverage-window-0032" in index
    assert "scene-1" not in index
    assert "attention-1" not in index


def test_m_citations_resolve_and_unsupported_ids_are_invalid_not_dropped():
    moments = [{"moment_id": "m1", "evidence_ids": ["scene-1", "fabricated-id"]}]
    validated = validate_citations(moments, windows=[sample_window()], condition="M")[0]
    assert [item["evidence_id"] for item in validated["resolved_evidence"]] == ["scene-1"]
    assert validated["invalid_evidence_ids"] == ["fabricated-id"]
    assert validated["citations_valid"] is False
    assert moments == [{"moment_id": "m1", "evidence_ids": ["scene-1", "fabricated-id"]}]


def test_resolution_persists_session_and_exact_delivered_artifact_digest():
    digest = "b" * 64
    validated = validate_citations(
        [{"moment_id": "m1", "evidence_ids": ["scene-1"]}],
        windows=[sample_window()], condition="M", delivered_artifact_sha256=digest,
    )

    resolved = validated[0]["resolved_evidence"][0]
    assert resolved["session_id"] == "session-001"
    assert resolved["source_artifact_sha256"] == digest


def test_resolution_keeps_genuinely_unavailable_digest_explicitly_null():
    window = sample_window()
    window["provenance"] = {}
    validated = validate_citations(
        [{"moment_id": "m1", "evidence_ids": ["scene-1"]}],
        windows=[window], condition="M",
    )

    resolved = validated[0]["resolved_evidence"][0]
    assert "source_artifact_sha256" in resolved
    assert resolved["source_artifact_sha256"] is None


def test_audit_catches_t_citation_to_m_only_evidence_and_lists_the_moment():
    window = sample_window()
    m_resolved = validate_citations(
        [{"moment_id": "m", "start_seconds": 485, "end_seconds": 487,
          "evidence_ids": ["attention-1"]}],
        windows=[window], condition="M",
    )[0]["resolved_evidence"]
    focal_runs = {
        "T": {
            "session_id": "session-001", "condition": "T",
            "moments": [{
                "moment_id": "t-leak", "start_seconds": 485, "end_seconds": 487,
                "evidence_ids": ["attention-1"], "resolved_evidence": m_resolved,
                "invalid_evidence_ids": [], "citations_valid": True,
            }],
        },
        "M": {"session_id": "session-001", "condition": "M", "moments": []},
    }

    audit = audit_provenance_integrity(
        session_id="session-001", focal_runs=focal_runs, windows=[window],
        delivered_artifact_sha256="0" * 64,
    )

    assert audit["temporal_rule"]["rule_id"] == TEMPORAL_RULE_ID
    assert audit["counts"]["moment_count"] == 1
    assert audit["counts"]["undelivered_citation_count"] == 1
    assert audit["counts"]["invalid_or_incomplete_moment_count"] == 1
    assert audit["invalid_or_incomplete_moment_ids"] == ["T:t-leak"]
    assert "citation_not_delivered_to_condition" in (
        audit["conditions"]["T"]["moment_results"][0]["violation_codes"]
    )


def test_audit_counts_incomplete_provenance_and_strict_boundary_touch():
    window = sample_window()
    focal_runs = {
        "T": {"session_id": "session-001", "condition": "T", "moments": []},
        "M": {
            "session_id": "session-001", "condition": "M",
            "moments": validate_citations(
                [{"moment_id": "m-touch", "start_seconds": 484.5, "end_seconds": 487,
                  "evidence_ids": ["transcript-1"]}],
                windows=[window], condition="M",
            ),
        },
    }
    del focal_runs["M"]["moments"][0]["resolved_evidence"][0]["source_artifact_sha256"]

    audit = audit_provenance_integrity(
        session_id="session-001", focal_runs=focal_runs, windows=[window],
        delivered_artifact_sha256="0" * 64,
    )

    assert audit["counts"]["incomplete_provenance_item_count"] == 1
    assert audit["counts"]["temporally_invalid_citation_count"] == 1
    assert audit["counts"]["invalid_or_incomplete_moment_count"] == 1
    codes = audit["conditions"]["M"]["moment_results"][0]["violation_codes"]
    assert "resolved_item_source_digest_missing_or_invalid" in codes
    assert "citation_temporal_rule_failed" in codes
