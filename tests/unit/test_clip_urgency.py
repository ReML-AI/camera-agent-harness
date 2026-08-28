import pytest

from scripts.core.errors import ContractError
from scripts.flags.clip_urgency import ClipUrgencyAdapter, ClipUrgencyInterval


class SyntheticClipPolicy:
    policy_id = "synthetic-clip-policy"

    def __init__(self):
        self.calls = 0

    def flag(self, frame_records):
        self.calls += 1
        return [
            ClipUrgencyInterval(
                "1", 2, 3, ("clip-frame-1",), ("cam1",),
                {"opaque_synthetic_score": 0.25},
            )
        ]


def test_synthetic_clip_policy_runs_outside_paper_mode():
    policy = SyntheticClipPolicy()
    artifact = ClipUrgencyAdapter(policy, paper_mode=False).run("session-1", [])
    assert policy.calls == 1
    assert artifact.flags[0].policy_id == "synthetic-clip-policy"


def test_paper_mode_rejects_caller_supplied_clip_substitute():
    with pytest.raises(ContractError, match="fixed CLIP"):
        ClipUrgencyAdapter(SyntheticClipPolicy(), paper_mode=True)


def test_synthetic_clip_adapter_preserves_policy_output_and_provenance():
    artifact = ClipUrgencyAdapter(SyntheticClipPolicy(), paper_mode=False).run("session-1", [])
    assert artifact.status.value == "success_nonempty"
    assert artifact.flags[0].payload["score_record"] == {"opaque_synthetic_score": 0.25}
    assert artifact.provenance["policy_id"] == "synthetic-clip-policy"
