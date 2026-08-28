"""
Rich Feedback Schema for Professional Clinical Debrief

Defines Pydantic models for the eight-section professional debrief structure.
"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


# ============================================================================
# Enums and Constants
# ============================================================================

class EvidenceSource(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"
    VITALS = "vitals"


class SkillRating(int, Enum):
    POOR = 1
    BELOW_AVERAGE = 2
    AVERAGE = 3
    ABOVE_AVERAGE = 4
    EXCELLENT = 5


class FeedbackStatus(str, Enum):
    DRAFT = "draft"
    AI_GENERATED = "ai_generated"
    DOCTOR_REVIEWED = "doctor_reviewed"
    FINAL = "final"


# ============================================================================
# Section 1: Scenario Details
# ============================================================================

class ScenarioDetails(BaseModel):
    """Section 1: Scenario Context"""
    patient_presentation: str = Field(
        ...,
        description="Brief description of patient presentation (e.g., '73-year-old male with respiratory tract infection')"
    )
    clinical_context: str = Field(
        ...,
        description="Clinical context and setting (e.g., 'Ward transfer for observation and IVABs')"
    )
    learning_objectives: List[str] = Field(
        default_factory=list,
        description="Learning objectives for this simulation"
    )
    scenario_type: Optional[str] = Field(
        None,
        description="Type of scenario (e.g., 'Anaphylaxis', 'Cardiac Arrest', 'Sepsis')"
    )


# ============================================================================
# Section 2: Clinical Skills Assessment
# ============================================================================

class TimestampedObservation(BaseModel):
    """Individual observation with timestamp and evidence link"""
    description: str = Field(..., description="What was observed")
    timestamp: str = Field(..., description="Timestamp in format 'MM:SS' or 'MM:SS-MM:SS'")
    timestamp_start: Optional[float] = Field(None, description="Start time in seconds")
    timestamp_end: Optional[float] = Field(None, description="End time in seconds")
    evidence_source: EvidenceSource = Field(..., description="Source of evidence")
    moment_id: Optional[str] = Field(None, description="Link to critical moment ID")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="AI confidence in this observation")


class ClinicalSkill(BaseModel):
    """Assessment of a single clinical skill"""
    skill_name: str = Field(..., description="Name of the skill (e.g., 'Airway Management')")
    performance_rating: SkillRating = Field(..., description="Rating 1-5")
    observations: List[TimestampedObservation] = Field(
        default_factory=list,
        description="Specific timestamped observations for this skill"
    )
    protocol_reference: Optional[str] = Field(
        None,
        description="Reference to clinical protocol (e.g., 'ABCDE Assessment')"
    )
    summary: Optional[str] = Field(None, description="Brief summary of performance")


# ============================================================================
# Section 3: ABCDE Assessment
# ============================================================================

class ABCDEItem(BaseModel):
    """Single ABCDE component assessment"""
    component: Literal["airway", "breathing", "circulation", "disability", "exposure"]
    status: str = Field(..., description="Assessment findings")
    actions_taken: List[str] = Field(default_factory=list, description="Actions taken for this component")
    observations: List[TimestampedObservation] = Field(default_factory=list)
    rating: Optional[SkillRating] = None
    notes: Optional[str] = None


class ABCDEAssessment(BaseModel):
    """Section 3: ABCDE Assessment"""
    airway: ABCDEItem
    breathing: ABCDEItem
    circulation: ABCDEItem
    disability: ABCDEItem
    exposure: ABCDEItem

    overall_sequence_followed: bool = Field(
        ...,
        description="Whether ABCDE sequence was followed correctly"
    )
    time_to_complete: Optional[float] = Field(
        None,
        description="Time to complete full assessment in seconds"
    )


# ============================================================================
# Section 4: Non-Technical Skills (NTS)
# ============================================================================

class NTSComponent(BaseModel):
    """Assessment of a single non-technical skill"""
    skill_name: str
    rating: SkillRating
    observations: List[TimestampedObservation] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    areas_for_improvement: List[str] = Field(default_factory=list)


class NonTechnicalSkills(BaseModel):
    """Section 4: Non-Technical Skills Assessment"""
    communication: NTSComponent = Field(..., description="Verbal and non-verbal communication")
    teamwork: NTSComponent = Field(..., description="Collaboration and coordination")
    leadership: NTSComponent = Field(..., description="Leadership and followership")
    situational_awareness: NTSComponent = Field(..., description="Awareness of environment and patient status")
    decision_making: NTSComponent = Field(..., description="Clinical reasoning and decisions")

    overall_nts_rating: Optional[SkillRating] = None


# ============================================================================
# Section 5: Crisis Resource Management (CRM)
# ============================================================================

class CRMReflection(BaseModel):
    """Section 5: Crisis Resource Management Reflection"""
    strengths: List[str] = Field(
        default_factory=list,
        description="CRM behaviors demonstrated well"
    )
    areas_for_development: List[str] = Field(
        default_factory=list,
        description="CRM areas needing improvement"
    )
    specific_observations: List[TimestampedObservation] = Field(
        default_factory=list,
        description="Specific timestamped CRM observations"
    )

    # CRM Principles (per PLAN reference to Park et al., 2010)
    knew_environment: Optional[bool] = Field(None, description="Knew the environment and available resources")
    mobilized_resources: Optional[bool] = Field(None, description="Mobilized all available resources early")
    prevented_fixation: Optional[bool] = Field(None, description="Prevented and managed fixation errors")
    cross_checked: Optional[bool] = Field(None, description="Cross-checked and double-checked medications")
    used_cognitive_aids: Optional[bool] = Field(None, description="Used cognitive aids and guidelines")
    re_evaluated: Optional[bool] = Field(None, description="Re-evaluated the patient repeatedly (10-for-10)")
    set_priorities: Optional[bool] = Field(None, description="Set priorities dynamically")


# ============================================================================
# Section 6: Learning Outcomes
# ============================================================================

class LearningOutcomes(BaseModel):
    """Section 6: Learning Outcomes and Action Plan"""
    key_achievements: List[str] = Field(
        default_factory=list,
        description="What the student did well"
    )
    areas_for_improvement: List[str] = Field(
        default_factory=list,
        description="Specific areas needing work"
    )
    recommended_focus: List[str] = Field(
        default_factory=list,
        description="Recommended focus areas for future practice"
    )
    action_plan: List[str] = Field(
        default_factory=list,
        description="Specific action items for improvement"
    )

    debrief_summary: Optional[str] = Field(
        None,
        description="Brief summary of key debrief points"
    )


# ============================================================================
# Section 7: Evidence Chain (Transparency)
# ============================================================================

class EvidenceLink(BaseModel):
    """Single evidence link in the audit trail"""
    moment_id: str = Field(..., description="ID of the critical moment")
    detection_source: EvidenceSource
    timestamp_start: float
    timestamp_end: float
    raw_data: Optional[Dict[str, Any]] = Field(
        None,
        description="Raw detection data (bbox, confidence, etc.)"
    )
    ai_interpretation: str = Field(..., description="How AI interpreted this evidence")
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    doctor_validated: bool = Field(default=False)
    validation_notes: Optional[str] = None


class EvidenceChain(BaseModel):
    """Section 7: Full evidence trail for transparency"""
    evidence_links: List[EvidenceLink] = Field(default_factory=list)

    total_moments_referenced: int = 0
    total_video_evidence: int = 0
    total_audio_evidence: int = 0
    total_vitals_evidence: int = 0

    def compute_stats(self):
        """Compute evidence statistics"""
        self.total_moments_referenced = len(set(e.moment_id for e in self.evidence_links))
        self.total_video_evidence = len([e for e in self.evidence_links if e.detection_source == EvidenceSource.VIDEO])
        self.total_audio_evidence = len([e for e in self.evidence_links if e.detection_source == EvidenceSource.AUDIO])
        self.total_vitals_evidence = len([e for e in self.evidence_links if e.detection_source == EvidenceSource.VITALS])


# ============================================================================
# Section 8: References
# ============================================================================

class Reference(BaseModel):
    """Clinical reference or citation"""
    citation: str = Field(..., description="Full citation text")
    url: Optional[str] = Field(None, description="URL if available")
    protocol_name: Optional[str] = Field(None, description="Name of referenced protocol")


# ============================================================================
# Complete Student Feedback (All 8 Sections)
# ============================================================================

class StudentFeedback(BaseModel):
    """
    Complete 8-section professional debrief feedback for a student.

    This is the main model that combines all feedback sections.
    """

    # Header
    id: Optional[str] = Field(None, description="Unique feedback ID")
    student_id: str = Field(..., description="ID of the student being evaluated")
    student_name: Optional[str] = Field(None, description="Student's name")
    student_role: str = Field(..., description="Role in simulation (e.g., 'Student Nurse (Primary)')")
    session_id: str = Field(..., description="Session ID")
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    version: int = Field(default=1, description="Feedback version number")
    status: FeedbackStatus = Field(default=FeedbackStatus.DRAFT)

    # Section 1: Scenario Context
    scenario_details: ScenarioDetails

    # Section 2: Professional Skills Assessment
    clinical_skills: List[ClinicalSkill] = Field(
        default_factory=list,
        description="Assessment of clinical skills demonstrated"
    )

    # Section 3: ABCDE Assessment (optional - depends on scenario)
    abcde_assessment: Optional[ABCDEAssessment] = None

    # Section 4: Non-Technical Skills
    non_technical_skills: NonTechnicalSkills

    # Section 5: Crisis Resource Management
    crm_reflection: CRMReflection

    # Section 6: Learning Outcomes
    learning_outcomes: LearningOutcomes

    # Section 7: Evidence Trail
    evidence_chain: EvidenceChain = Field(default_factory=EvidenceChain)

    # Section 8: References
    references: List[Reference] = Field(default_factory=list)

    # Metadata
    ai_model_version: Optional[str] = Field(None, description="AI model used for generation")
    doctor_reviewer_id: Optional[str] = Field(None, description="Doctor who reviewed")
    reviewed_at: Optional[datetime] = None

    class Config:
        use_enum_values = True


# ============================================================================
# Helper Functions
# ============================================================================

def create_empty_feedback(
    student_id: str,
    student_role: str,
    session_id: str,
    scenario_type: str = "General Clinical Simulation"
) -> StudentFeedback:
    """Create an empty feedback template with default structure."""

    return StudentFeedback(
        student_id=student_id,
        student_role=student_role,
        session_id=session_id,
        scenario_details=ScenarioDetails(
            patient_presentation="[To be filled]",
            clinical_context="[To be filled]",
            learning_objectives=[],
            scenario_type=scenario_type
        ),
        clinical_skills=[],
        non_technical_skills=NonTechnicalSkills(
            communication=NTSComponent(skill_name="Communication", rating=SkillRating.AVERAGE),
            teamwork=NTSComponent(skill_name="Teamwork", rating=SkillRating.AVERAGE),
            leadership=NTSComponent(skill_name="Leadership", rating=SkillRating.AVERAGE),
            situational_awareness=NTSComponent(skill_name="Situational Awareness", rating=SkillRating.AVERAGE),
            decision_making=NTSComponent(skill_name="Decision Making", rating=SkillRating.AVERAGE),
        ),
        crm_reflection=CRMReflection(),
        learning_outcomes=LearningOutcomes(),
        evidence_chain=EvidenceChain(),
        references=[]
    )


def format_timestamp(seconds: float) -> str:
    """Convert seconds to MM:SS format."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"
