"""Author-policy boundary shared by K and transcript critical-window flags."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Protocol, Sequence

from scripts.core.errors import ContractError
from scripts.core.records import Interval

from .models import FlagArtifact, FlagRecord, FlagSource


@dataclass(frozen=True)
class KeywordMatch:
    match_id: str
    start_seconds: float
    end_seconds: float
    evidence_ids: tuple[str, ...]
    category: str
    matched_policy_term_id: str

    def __post_init__(self) -> None:
        Interval(self.start_seconds, self.end_seconds)
        if not self.match_id or not self.evidence_ids or not self.category or not self.matched_policy_term_id:
            raise ContractError("keyword matches require IDs, evidence, category, and policy term ID")


class KeywordMatcher(Protocol):
    """Complete keyword/stem, normalization, and proximity policy."""

    policy_id: str

    def find_matches(self, transcript: Sequence[Mapping]) -> Iterable[KeywordMatch]: ...


class KBaseline:
    def __init__(self, matcher: KeywordMatcher, *, paper_mode: bool = True) -> None:
        if not matcher.policy_id:
            raise ContractError("keyword policy_id is required")
        self.matcher = matcher

    def run(self, transcript: Sequence[Mapping]) -> list[dict]:
        """Return every match supplied by the configured policy, without truncation."""
        matches = list(self.matcher.find_matches(transcript))
        if len({match.match_id for match in matches}) != len(matches):
            raise ContractError("keyword policy emitted duplicate match IDs")
        return [
            {
                "match_id": match.match_id,
                "start_seconds": match.start_seconds,
                "end_seconds": match.end_seconds,
                "evidence_ids": list(match.evidence_ids),
                "category": match.category,
                "matched_policy_term_id": match.matched_policy_term_id,
                "policy_id": self.matcher.policy_id,
            }
            for match in matches
        ]

    def flag_artifact(self, session_id: str, transcript: Sequence[Mapping]) -> FlagArtifact:
        flags = [
            FlagRecord(
                flag_id=f"flag-{match['match_id']}",
                source=FlagSource.TRANSCRIPT_KEYWORD,
                start_seconds=match["start_seconds"],
                end_seconds=match["end_seconds"],
                evidence_ids=tuple(match["evidence_ids"]),
                policy_id=self.matcher.policy_id,
                payload={
                    "category": match["category"],
                    "matched_policy_term_id": match["matched_policy_term_id"],
                },
            )
            for match in self.run(transcript)
        ]
        return FlagArtifact.success(
            session_id=session_id,
            source=FlagSource.TRANSCRIPT_KEYWORD,
            flags=flags,
            provenance={"policy_id": self.matcher.policy_id},
        )

    def run_artifact(self, session_id: str, transcript: Sequence[Mapping]) -> dict:
        return {
            "schema_version": "1.0.0",
            "session_id": session_id,
            "condition": "K",
            "policy_id": self.matcher.policy_id,
            "matches": self.run(transcript),
        }
