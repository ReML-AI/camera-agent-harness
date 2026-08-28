"""
Feedback Generation Package

Provides rich, evidence-based feedback generation for clinical simulations.
"""

from .feedback_schema import (
    StudentFeedback,
    ScenarioDetails,
    ClinicalSkill,
    ABCDEAssessment,
    NonTechnicalSkills,
    CRMReflection,
    LearningOutcomes,
    EvidenceChain,
    TimestampedObservation,
    EvidenceLink,
    Reference,
    EvidenceSource,
    SkillRating,
    FeedbackStatus,
    create_empty_feedback,
    format_timestamp
)

from .clinical_protocols import (
    ProtocolRegistry,
    ABCDEProtocol,
    CRMProtocol,
    NTSFramework,
    TreatmentProtocol,
    AnaphylaxisProtocol,
    format_abcde_for_prompt,
    format_crm_for_prompt,
    format_treatment_for_prompt,
    STANDARD_REFERENCES
)

from .evidence_linker import (
    EvidenceLinker,
    EvidenceChainBuilder,
    CriticalMoment,
    MomentType,
    verify_evidence_chain
)

__all__ = [
    # Schema
    "StudentFeedback",
    "ScenarioDetails",
    "ClinicalSkill",
    "ABCDEAssessment",
    "NonTechnicalSkills",
    "CRMReflection",
    "LearningOutcomes",
    "EvidenceChain",
    "TimestampedObservation",
    "EvidenceLink",
    "Reference",
    "EvidenceSource",
    "SkillRating",
    "FeedbackStatus",
    "create_empty_feedback",
    "format_timestamp",
    # Protocols
    "ProtocolRegistry",
    "ABCDEProtocol",
    "CRMProtocol",
    "NTSFramework",
    "TreatmentProtocol",
    "AnaphylaxisProtocol",
    "format_abcde_for_prompt",
    "format_crm_for_prompt",
    "format_treatment_for_prompt",
    "STANDARD_REFERENCES",
    # Evidence
    "EvidenceLinker",
    "EvidenceChainBuilder",
    "CriticalMoment",
    "MomentType",
    "verify_evidence_chain"
]
