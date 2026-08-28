"""The prompt must fit the context window, and must fail loudly when it does not."""
from types import SimpleNamespace

import pytest

from scripts.analytics.assemble_multimodal_windows import _prompt_transcript
from scripts.core.errors import ContractError
from scripts.focal.pipeline_stages import _reject_truncated_prompt


def _segment():
    return {
        "evidence_id": "segment-000000",
        "transcript_segment_id": "segment-000000",
        "speaker": "SPEAKER_01",
        "speaker_id": "SPEAKER_01",
        "start": 0.031,
        "start_seconds": 0.031,
        "end": 0.932,
        "end_seconds": 0.932,
        "text": " It's not tingly at all.",
        "words": [{"word": "It's", "start": 0.031, "end": 0.151, "score": 0.74}] * 8,
    }


def test_prompt_transcript_keeps_only_what_the_model_can_use():
    projected = _prompt_transcript([_segment()])
    assert projected == [
        {
            "evidence_id": "segment-000000",
            "speaker_id": "SPEAKER_01",
            "start_seconds": 0.031,
            "end_seconds": 0.932,
            "text": " It's not tingly at all.",
        }
    ]


def test_prompt_transcript_drops_word_timings_and_aliases():
    """Word timings and duplicate aliases were 87% of the rendered prompt."""
    projected = _prompt_transcript([_segment()])[0]
    assert "words" not in projected
    assert not {"start", "end", "speaker", "transcript_segment_id"} & set(projected)


def test_prompt_transcript_leaves_unexpected_shapes_alone():
    assert _prompt_transcript("not available") == "not available"
    assert _prompt_transcript(["a string"]) == ["a string"]


def _response(prompt_tokens):
    return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=prompt_tokens))


def _request(context_length=32768):
    return SimpleNamespace(runtime=SimpleNamespace(context_length=context_length))


def test_truncated_prompt_is_rejected():
    """Ollama keeps the tail and warns; the run must not record the result as complete."""
    with pytest.raises(ContractError, match="truncated by the backend"):
        _reject_truncated_prompt(_response(32768), _request())


def test_prompt_within_the_window_is_accepted():
    _reject_truncated_prompt(_response(13359), _request())


def test_missing_usage_is_not_treated_as_truncation():
    """A backend that reports no usage gives no evidence either way."""
    _reject_truncated_prompt(SimpleNamespace(usage=None), _request())
