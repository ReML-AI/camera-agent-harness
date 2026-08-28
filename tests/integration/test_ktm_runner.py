import json

from scripts.flags.keyword import KBaseline, KeywordMatch
from scripts.focal.runner import run_ktm
from scripts.focal.runtime import FocalRuntime
from tests.test_multimodal_windows import sample_window
from tests.unit.test_focal_runtime import runtime_values


class SyntheticMatcher:
    policy_id = "synthetic-k-policy"

    def find_matches(self, transcript):
        return [KeywordMatch("k-1", 1, 2, ("transcript-1",), "synthetic-0", "term-1")]


class FakeFocalEndpoint:
    def __init__(self):
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        evidence_id = "transcript-1" if request.condition == "T" else "scene-1"
        return json.dumps({
            "moments": [{
                "moment_id": f"moment-{request.condition}",
                "start_seconds": 481, "end_seconds": 482,
                "description": "synthetic description",
                "clinical_significance": "synthetic significance",
                "category": "synthetic-0", "evidence_ids": [evidence_id],
                "cross_modal_observations": [],
            }]
        })


def test_fake_endpoint_ktm_flow_has_symmetric_order_controls_and_valid_citations():
    endpoint = FakeFocalEndpoint()
    runtime = FocalRuntime.checked(paper_mode=False, **runtime_values())
    delivered_digest = "b" * 64
    output = run_ktm(
        session_id="session-001", transcript=[{"evidence_id": "transcript-1"}],
        windows=[sample_window()], session_duration_seconds=600,
        speakers=[{"speaker_id": "speaker-1", "role": "synthetic-role"}],
        k_baseline=KBaseline(SyntheticMatcher(), paper_mode=False),
        runtime=runtime, endpoint=endpoint,
        category_taxonomy=[f"synthetic-{i}" for i in range(7)],
        delivered_artifact_sha256=delivered_digest, paper_mode=False,
    )
    # One discarded warm-up, then both conditions measured. Neither measured call is the
    # server's first, so request position no longer tracks condition.
    issued = [request.condition for request in endpoint.requests]
    assert len(issued) == 3
    measured = issued[1:]
    assert sorted(measured) == ["M", "T"]
    assert measured == output["T"]["control_manifest"]["request_order"]
    assert output["T"]["control_manifest"]["warmup_discarded"] is True
    assert output["T"]["ordered_window_ids"] == output["M"]["ordered_window_ids"] == ["window-0032"]
    assert output["T"]["control_manifest"] == output["M"]["control_manifest"]
    assert output["T"]["moments"][0]["citations_valid"] is True
    assert output["M"]["moments"][0]["citations_valid"] is True
    for condition in ("T", "M"):
        stored = output[condition]["moments"][0]["resolved_evidence"][0]
        assert stored["session_id"] == "session-001"
        assert stored["source_artifact_sha256"] == delivered_digest
    t_index = 1 + measured.index("T")
    assert 'Visual scene: not available' in endpoint.requests[t_index].prompt
    m_index = 1 + measured.index("M")
    assert "synthetic scene" in endpoint.requests[m_index].prompt
    assert "Modality coverage:" in endpoint.requests[0].prompt
    assert output["K"]["condition"] == "K"
    assert output["K"]["matches"][0]["match_id"] == "k-1"


def test_resolved_paper_mode_runs_the_same_validated_fake_endpoint_flow():
    endpoint = FakeFocalEndpoint()
    output = run_ktm(
        session_id="session-001", transcript=[], windows=[sample_window()],
        session_duration_seconds=600, speakers=[],
        k_baseline=KBaseline(SyntheticMatcher(), paper_mode=True),
        runtime=FocalRuntime.checked(paper_mode=True, **runtime_values()),
        endpoint=endpoint, category_taxonomy=[f"synthetic-{i}" for i in range(7)],
        paper_mode=True,
    )
    issued = [request.condition for request in endpoint.requests]
    assert len(issued) == 3 and sorted(issued[1:]) == ["M", "T"]
    assert output["T"]["moments"][0]["citations_valid"] is True
    assert output["M"]["moments"][0]["citations_valid"] is True


def test_numeric_moment_id_is_normalised_not_fatal():
    """Quoted and numeric model-generated moment IDs identify the same moment."""
    from scripts.focal.runner import _parse_response

    raw = json.dumps({"moments": [{
        "moment_id": 1, "start_seconds": 0.0, "end_seconds": 5.0,
        "description": "d", "clinical_significance": "s", "category": "synthetic-0",
        "evidence_ids": ["transcript-1"], "cross_modal_observations": [],
    }]})

    parsed = _parse_response(raw, {"synthetic-0"})
    assert parsed[0]["moment_id"] == "1"
