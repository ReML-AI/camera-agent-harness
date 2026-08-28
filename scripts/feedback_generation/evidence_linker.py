"""
Evidence Linker for Professional Debrief Feedback

Links feedback observations to source evidence (video, audio, vitals) moments.
Creates transparent audit trails from raw data to AI interpretations.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
import json
from pathlib import Path

from .feedback_schema import (
    EvidenceSource,
    TimestampedObservation,
    EvidenceLink,
    EvidenceChain,
    format_timestamp
)


# ============================================================================
# Evidence Types
# ============================================================================

class MomentType(str, Enum):
    """Types of critical moments that can be detected"""
    VIDEO_ACTION = "video_action"         # Visual action detected
    AUDIO_SPEECH = "audio_speech"         # Spoken words transcribed
    AUDIO_ALARM = "audio_alarm"           # Alarm or alert detected
    VITALS_CHANGE = "vitals_change"       # Vital signs change
    VITALS_CRITICAL = "vitals_critical"   # Critical vital threshold
    COMPOSITE = "composite"               # Multi-source fusion


class CriticalMoment(BaseModel):
    """A critical moment detected during simulation analysis"""
    moment_id: str
    moment_type: MomentType
    timestamp_start: float  # seconds from start
    timestamp_end: float
    camera_id: Optional[str] = None
    description: str
    severity: Optional[str] = None  # low, medium, high, critical
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    raw_data: Dict[str, Any] = Field(default_factory=dict)
    associated_persons: List[str] = Field(default_factory=list)  # person IDs


class EvidenceCandidate(BaseModel):
    """A candidate evidence link before confirmation"""
    moment: CriticalMoment
    relevance_score: float
    matching_keywords: List[str] = Field(default_factory=list)
    temporal_distance: float = 0.0  # seconds from observation timestamp


# ============================================================================
# Evidence Linker
# ============================================================================

class EvidenceLinker:
    """
    Links feedback observations to source evidence moments.

    Creates the evidence chain:
    Raw Video/Audio/Vitals → Detection → Critical Moment → AI Interpretation → Feedback
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path("data")
        self.moments: List[CriticalMoment] = []
        self._moments_index: Dict[str, CriticalMoment] = {}

    def load_moments(self, moments_file: Optional[Path] = None) -> int:
        """Load critical moments from analysis results"""
        if moments_file is None:
            moments_file = self.data_dir / "processed" / "critical_moments.json"

        if not moments_file.exists():
            return 0

        with open(moments_file, 'r') as f:
            data = json.load(f)

        self.moments = []
        for m in data.get("moments", []):
            moment = CriticalMoment(
                moment_id=m.get("id", f"moment_{len(self.moments)}"),
                moment_type=MomentType(m.get("type", "composite")),
                timestamp_start=m.get("timestamp_start", m.get("timestamp", 0)),
                timestamp_end=m.get("timestamp_end", m.get("timestamp", 0) + 5),
                camera_id=m.get("camera_id"),
                description=m.get("description", ""),
                severity=m.get("severity"),
                confidence=m.get("confidence", 0.8),
                raw_data=m.get("raw_data", {}),
                associated_persons=m.get("associated_persons", [])
            )
            self.moments.append(moment)
            self._moments_index[moment.moment_id] = moment

        return len(self.moments)

    def find_moments_in_timerange(
        self,
        start_seconds: float,
        end_seconds: float,
        source_filter: Optional[EvidenceSource] = None,
        min_confidence: float = 0.5
    ) -> List[CriticalMoment]:
        """Find all moments within a time range"""
        results = []
        for moment in self.moments:
            # Check time overlap
            if moment.timestamp_end < start_seconds or moment.timestamp_start > end_seconds:
                continue

            # Check confidence
            if moment.confidence < min_confidence:
                continue

            # Check source filter
            if source_filter:
                moment_source = self._moment_type_to_evidence_source(moment.moment_type)
                if moment_source != source_filter:
                    continue

            results.append(moment)

        return results

    def find_moments_for_observation(
        self,
        observation_text: str,
        timestamp_hint: Optional[str] = None,
        person_id: Optional[str] = None,
        max_results: int = 5
    ) -> List[EvidenceCandidate]:
        """
        Find relevant moments for a feedback observation.

        Uses text matching and temporal proximity to rank candidates.
        """
        candidates = []

        # Parse timestamp hint if provided
        hint_seconds = self._parse_timestamp(timestamp_hint) if timestamp_hint else None

        # Extract keywords from observation
        keywords = self._extract_keywords(observation_text)

        for moment in self.moments:
            # Calculate relevance score
            relevance = 0.0

            # Keyword matching
            matching_keywords = []
            moment_text = moment.description.lower()
            for kw in keywords:
                if kw.lower() in moment_text:
                    matching_keywords.append(kw)
                    relevance += 0.2

            # Person matching
            if person_id and person_id in moment.associated_persons:
                relevance += 0.3

            # Temporal proximity
            temporal_distance = float('inf')
            if hint_seconds is not None:
                mid_time = (moment.timestamp_start + moment.timestamp_end) / 2
                temporal_distance = abs(mid_time - hint_seconds)
                # Closer = higher score (within 30 seconds is good)
                if temporal_distance < 30:
                    relevance += 0.3 * (1 - temporal_distance / 30)

            # Confidence boost
            relevance += moment.confidence * 0.2

            if relevance > 0.1:  # Minimum threshold
                candidates.append(EvidenceCandidate(
                    moment=moment,
                    relevance_score=relevance,
                    matching_keywords=matching_keywords,
                    temporal_distance=temporal_distance if temporal_distance != float('inf') else -1
                ))

        # Sort by relevance
        candidates.sort(key=lambda x: x.relevance_score, reverse=True)
        return candidates[:max_results]

    def create_evidence_link(
        self,
        moment: CriticalMoment,
        ai_interpretation: str,
        doctor_validated: bool = False,
        validation_notes: Optional[str] = None
    ) -> EvidenceLink:
        """Create an evidence link from a moment to feedback"""
        return EvidenceLink(
            moment_id=moment.moment_id,
            detection_source=self._moment_type_to_evidence_source(moment.moment_type),
            timestamp_start=moment.timestamp_start,
            timestamp_end=moment.timestamp_end,
            raw_data=moment.raw_data,
            ai_interpretation=ai_interpretation,
            confidence_score=moment.confidence,
            doctor_validated=doctor_validated,
            validation_notes=validation_notes
        )

    def create_timestamped_observation(
        self,
        description: str,
        moment: CriticalMoment,
        confidence: float = 1.0
    ) -> TimestampedObservation:
        """Create a timestamped observation linked to a moment"""
        return TimestampedObservation(
            description=description,
            timestamp=f"{format_timestamp(moment.timestamp_start)}-{format_timestamp(moment.timestamp_end)}",
            timestamp_start=moment.timestamp_start,
            timestamp_end=moment.timestamp_end,
            evidence_source=self._moment_type_to_evidence_source(moment.moment_type),
            moment_id=moment.moment_id,
            confidence=confidence
        )

    def build_evidence_chain(
        self,
        observations: List[TimestampedObservation],
        validate_all: bool = False
    ) -> EvidenceChain:
        """Build a complete evidence chain from observations"""
        chain = EvidenceChain()

        for obs in observations:
            if obs.moment_id and obs.moment_id in self._moments_index:
                moment = self._moments_index[obs.moment_id]
                link = self.create_evidence_link(
                    moment=moment,
                    ai_interpretation=obs.description,
                    doctor_validated=validate_all
                )
                chain.evidence_links.append(link)

        chain.compute_stats()
        return chain

    def get_moment_by_id(self, moment_id: str) -> Optional[CriticalMoment]:
        """Get a moment by its ID"""
        return self._moments_index.get(moment_id)

    def get_video_clip_info(self, moment: CriticalMoment) -> Dict[str, Any]:
        """Get information needed to play a video clip for a moment"""
        return {
            "moment_id": moment.moment_id,
            "camera_id": moment.camera_id,
            "start_time": moment.timestamp_start,
            "end_time": moment.timestamp_end,
            "duration": moment.timestamp_end - moment.timestamp_start,
            "timestamp_display": f"{format_timestamp(moment.timestamp_start)}-{format_timestamp(moment.timestamp_end)}",
            "description": moment.description
        }

    # ========================================================================
    # Private Methods
    # ========================================================================

    def _moment_type_to_evidence_source(self, moment_type: MomentType) -> EvidenceSource:
        """Convert moment type to evidence source"""
        if moment_type in [MomentType.VIDEO_ACTION]:
            return EvidenceSource.VIDEO
        elif moment_type in [MomentType.AUDIO_SPEECH, MomentType.AUDIO_ALARM]:
            return EvidenceSource.AUDIO
        elif moment_type in [MomentType.VITALS_CHANGE, MomentType.VITALS_CRITICAL]:
            return EvidenceSource.VITALS
        else:
            return EvidenceSource.VIDEO  # Default for composite

    def _parse_timestamp(self, timestamp: str) -> Optional[float]:
        """Parse a timestamp string to seconds"""
        if not timestamp:
            return None

        try:
            # Handle MM:SS format
            if ':' in timestamp:
                # Handle ranges like "7:09-7:15"
                if '-' in timestamp:
                    timestamp = timestamp.split('-')[0]
                parts = timestamp.strip().split(':')
                if len(parts) == 2:
                    minutes, seconds = int(parts[0]), int(parts[1])
                    return minutes * 60 + seconds
                elif len(parts) == 3:
                    hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
                    return hours * 3600 + minutes * 60 + seconds
            else:
                return float(timestamp)
        except (ValueError, IndexError):
            return None

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract relevant keywords from observation text"""
        # Clinical keywords to look for
        clinical_terms = [
            "airway", "breathing", "circulation", "disability", "exposure",
            "adrenaline", "oxygen", "iv", "fluid", "bolus",
            "escalation", "help", "call", "cpr", "chest compression",
            "anaphylaxis", "rash", "swelling", "wheeze",
            "hypotension", "tachycardia", "bradycardia",
            "communication", "handover", "isbar", "closed-loop",
            "team", "leadership", "delegate"
        ]

        text_lower = text.lower()
        found = []

        for term in clinical_terms:
            if term in text_lower:
                found.append(term)

        return found


# ============================================================================
# Evidence Chain Builder (High-Level API)
# ============================================================================

class EvidenceChainBuilder:
    """
    High-level API for building evidence chains during feedback generation.

    Usage:
        builder = EvidenceChainBuilder(moments_file)

        # For each feedback observation:
        obs = builder.link_observation(
            "Good early recognition of airway compromise",
            timestamp="6:52"
        )

        # Get final chain:
        chain = builder.build()
    """

    def __init__(self, moments_file: Optional[Path] = None):
        self.linker = EvidenceLinker()
        if moments_file:
            self.linker.load_moments(moments_file)
        self.observations: List[TimestampedObservation] = []
        self.unlinked_observations: List[str] = []

    def link_observation(
        self,
        description: str,
        timestamp: Optional[str] = None,
        person_id: Optional[str] = None,
        evidence_source: Optional[EvidenceSource] = None,
        auto_link: bool = True
    ) -> TimestampedObservation:
        """
        Create and link an observation to evidence.

        If auto_link=True, attempts to find a matching moment automatically.
        """
        # Try to find matching moment
        moment = None
        if auto_link and self.linker.moments:
            candidates = self.linker.find_moments_for_observation(
                description, timestamp, person_id
            )
            if candidates and candidates[0].relevance_score > 0.3:
                moment = candidates[0].moment

        if moment:
            obs = self.linker.create_timestamped_observation(
                description, moment
            )
        else:
            # Create observation without moment link
            self.unlinked_observations.append(description)

            # Parse timestamp for display
            ts_start = None
            ts_end = None
            ts_display = timestamp or "N/A"

            if timestamp:
                parsed = self.linker._parse_timestamp(timestamp)
                if parsed is not None:
                    ts_start = parsed
                    # If range, parse end too
                    if '-' in timestamp:
                        end_part = timestamp.split('-')[1]
                        ts_end = self.linker._parse_timestamp(end_part)
                    else:
                        ts_end = parsed + 3  # Default 3 second duration

            obs = TimestampedObservation(
                description=description,
                timestamp=ts_display,
                timestamp_start=ts_start,
                timestamp_end=ts_end,
                evidence_source=evidence_source or EvidenceSource.VIDEO,
                moment_id=None,
                confidence=0.7  # Lower confidence for unlinked
            )

        self.observations.append(obs)
        return obs

    def build(self) -> EvidenceChain:
        """Build the final evidence chain"""
        return self.linker.build_evidence_chain(self.observations)

    def get_unlinked_count(self) -> int:
        """Get count of observations that couldn't be linked to moments"""
        return len(self.unlinked_observations)

    def get_link_rate(self) -> float:
        """Get the percentage of observations successfully linked"""
        total = len(self.observations)
        if total == 0:
            return 1.0
        linked = total - len(self.unlinked_observations)
        return linked / total


# ============================================================================
# Utility Functions
# ============================================================================

def verify_evidence_chain(chain: EvidenceChain) -> Dict[str, Any]:
    """Verify the integrity of an evidence chain"""
    issues = []
    stats = {
        "total_links": len(chain.evidence_links),
        "validated_links": 0,
        "high_confidence_links": 0,
        "low_confidence_links": 0,
        "issues": []
    }

    for link in chain.evidence_links:
        if link.doctor_validated:
            stats["validated_links"] += 1

        if link.confidence_score >= 0.8:
            stats["high_confidence_links"] += 1
        elif link.confidence_score < 0.5:
            stats["low_confidence_links"] += 1
            issues.append(f"Low confidence ({link.confidence_score:.2f}) for moment {link.moment_id}")

        # Check for missing data
        if not link.ai_interpretation:
            issues.append(f"Missing AI interpretation for moment {link.moment_id}")

    stats["issues"] = issues
    stats["is_valid"] = len(issues) == 0

    return stats


def export_evidence_chain_html(chain: EvidenceChain, title: str = "Evidence Chain") -> str:
    """Export evidence chain as HTML for display"""
    html = f"""
    <div class="evidence-chain">
        <h3>{title}</h3>
        <div class="stats">
            <span>Total Evidence: {chain.total_moments_referenced}</span>
            <span>Video: {chain.total_video_evidence}</span>
            <span>Audio: {chain.total_audio_evidence}</span>
            <span>Vitals: {chain.total_vitals_evidence}</span>
        </div>
        <div class="links">
    """

    for link in chain.evidence_links:
        validated_class = "validated" if link.doctor_validated else "pending"
        html += f"""
            <div class="evidence-link {validated_class}">
                <span class="timestamp">{format_timestamp(link.timestamp_start)}</span>
                <span class="source">{link.detection_source.value}</span>
                <span class="interpretation">{link.ai_interpretation}</span>
                <span class="confidence">{link.confidence_score:.0%}</span>
                {"✓" if link.doctor_validated else "?"}
            </div>
        """

    html += """
        </div>
    </div>
    """
    return html


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    # Demo usage
    print("Evidence Linker Demo")
    print("=" * 80)

    # Create sample moments
    sample_moments = [
        CriticalMoment(
            moment_id="moment_001",
            moment_type=MomentType.VIDEO_ACTION,
            timestamp_start=412,  # 6:52
            timestamp_end=415,    # 6:55
            camera_id="cam1",
            description="Tongue swelling observed, student recognizes airway compromise",
            severity="high",
            confidence=0.92,
            associated_persons=["student_1"]
        ),
        CriticalMoment(
            moment_id="moment_002",
            moment_type=MomentType.AUDIO_SPEECH,
            timestamp_start=429,  # 7:09
            timestamp_end=435,
            camera_id="cam1",
            description="Student calls for help, early escalation",
            severity="medium",
            confidence=0.88,
            associated_persons=["student_1"]
        ),
        CriticalMoment(
            moment_id="moment_003",
            moment_type=MomentType.VIDEO_ACTION,
            timestamp_start=513,  # 8:33
            timestamp_end=520,
            camera_id="cam2",
            description="IM Adrenaline administered",
            severity="high",
            confidence=0.95,
            associated_persons=["student_1", "student_2"]
        )
    ]

    # Build evidence chain
    builder = EvidenceChainBuilder()
    builder.linker.moments = sample_moments
    builder.linker._moments_index = {m.moment_id: m for m in sample_moments}

    # Link observations
    obs1 = builder.link_observation(
        "Early recognition of tongue swelling and airway compromise",
        timestamp="6:52-6:55",
        person_id="student_1"
    )
    print(f"Observation 1: {obs1.description}")
    print(f"  Linked to: {obs1.moment_id}")
    print(f"  Timestamp: {obs1.timestamp}")

    obs2 = builder.link_observation(
        "Prompt call for help demonstrating good escalation",
        timestamp="7:09",
        person_id="student_1"
    )
    print(f"\nObservation 2: {obs2.description}")
    print(f"  Linked to: {obs2.moment_id}")

    # Build chain
    chain = builder.build()
    print("\nEvidence Chain Built:")
    print(f"  Total links: {len(chain.evidence_links)}")
    print(f"  Link rate: {builder.get_link_rate():.0%}")

    # Verify
    verification = verify_evidence_chain(chain)
    print("\nVerification:")
    print(f"  Valid: {verification['is_valid']}")
    print(f"  High confidence: {verification['high_confidence_links']}")
