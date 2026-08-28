"""
Student Feedback Endpoints

Provides per-student feedback management with evidence transparency.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session as DBSession
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from enum import Enum
import json
import sys
import logging
from pathlib import Path

from ..database import get_db
from ._validation import require_session_id

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Pydantic Models
# ============================================================================

class FeedbackStatus(str, Enum):
    DRAFT = "draft"
    AI_GENERATED = "ai_generated"
    DOCTOR_REVIEWED = "doctor_reviewed"
    FINAL = "final"


class EvidenceSource(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"
    VITALS = "vitals"


class TimestampedObservation(BaseModel):
    description: str
    timestamp: str
    timestamp_start: Optional[float] = None
    timestamp_end: Optional[float] = None
    evidence_source: EvidenceSource
    moment_id: Optional[str] = None
    confidence: float = 1.0


class EvidenceLink(BaseModel):
    moment_id: str
    detection_source: EvidenceSource
    timestamp_start: float
    timestamp_end: float
    raw_data: Optional[Dict[str, Any]] = None
    ai_interpretation: str
    confidence_score: float
    doctor_validated: bool = False
    validation_notes: Optional[str] = None


class StudentSummary(BaseModel):
    student_id: str
    student_name: Optional[str] = None
    role: str
    thumbnail_url: Optional[str] = None
    feedback_status: FeedbackStatus
    total_observations: int = 0
    evidence_count: int = 0
    last_updated: Optional[datetime] = None


class StudentFeedbackResponse(BaseModel):
    student_id: str
    student_name: Optional[str] = None
    student_role: str
    session_id: str
    status: FeedbackStatus
    scenario_details: Dict[str, Any]
    clinical_skills: List[Dict[str, Any]]
    abcde_assessment: Optional[Dict[str, Any]] = None
    non_technical_skills: Dict[str, Any]
    crm_reflection: Dict[str, Any]
    learning_outcomes: Dict[str, Any]
    evidence_chain: Dict[str, Any]
    references: List[Dict[str, Any]]
    generated_at: Optional[datetime] = None
    ai_model_version: Optional[str] = None


class ValidateEvidenceRequest(BaseModel):
    evidence_id: str
    validated: bool
    notes: Optional[str] = None


class DoctorEditRequest(BaseModel):
    section: str
    field_path: str
    original_value: Any
    new_value: Any
    evaluator_id: str


# ============================================================================
# Data Directory
# ============================================================================

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"


def get_student_feedback_file(session_id: str) -> Path:
    """Get path to student feedback JSON file"""
    session_id = require_session_id(session_id)
    return DATA_DIR / "processed" / f"student_feedback_{session_id}.json"


def get_person_labels_file() -> Path:
    """Get path to person labels JSON file"""
    return DATA_DIR / "labeled" / "person_roles_per_camera.json"


def load_person_labels() -> Dict[str, Any]:
    """Load person labels from file"""
    labels_file = get_person_labels_file()
    if labels_file.exists():
        with open(labels_file, 'r') as f:
            data = json.load(f)
            # The labeling system saves as {"person_labels": {...}}
            return data.get('person_labels', {})
    return {}


# ============================================================================
# Student List Endpoints
# ============================================================================

@router.get("/session/{session_id}", response_model=List[StudentSummary])
def get_students_with_feedback(session_id: str):
    """
    Get all students in a session with their feedback status.

    Returns summary information for each student including:
    - Basic info (ID, name, role)
    - Feedback status
    - Observation counts
    """
    students = []

    # Load person labels to get role assignments
    labels = load_person_labels()

    # Load student feedback if exists
    feedback_file = get_student_feedback_file(session_id)
    feedback_data = {}
    if feedback_file.exists():
        with open(feedback_file, 'r') as f:
            data = json.load(f)
            for fb in data.get('student_feedback', []):
                feedback_data[fb['student_id']] = fb

    # Get thumbnails directory
    thumbnails_dir = DATA_DIR / "processed" / "thumbnails"

    # Build student list from labels
    # Labels are stored per-frame, so we need to aggregate by person
    person_map = {}  # Map person_key to label info

    for frame_key, label_info in labels.items():
        # Extract person key from frame key (e.g., "cam1_person_1_frame_0" -> "cam1_person_1")
        parts = frame_key.rsplit('_frame_', 1)
        if len(parts) == 2:
            person_key = parts[0]
        else:
            person_key = frame_key

        # Take the first label we find for this person
        if person_key not in person_map:
            person_map[person_key] = label_info

    for person_key, label_info in person_map.items():
        role = label_info.get('role', 'Unknown')

        # Only include students (not facilitators, patients, etc.)
        if 'student' in role.lower() and 'nurse' in role.lower():
            feedback = feedback_data.get(person_key, {})

            # Find thumbnail
            thumbnail_url = None
            for thumb in thumbnails_dir.glob(f"{person_key}*.jpg"):
                thumbnail_url = f"/api/thumbnails/{thumb.name}"
                break

            students.append(StudentSummary(
                student_id=person_key,
                student_name=label_info.get('name'),
                role=role,
                thumbnail_url=thumbnail_url,
                feedback_status=FeedbackStatus(feedback.get('status', 'draft')),
                total_observations=len(feedback.get('clinical_skills', [])),
                evidence_count=len(feedback.get('evidence_chain', {}).get('evidence_links', [])),
                last_updated=feedback.get('generated_at')
            ))

    return students


@router.get("/{student_id}/feedback", response_model=StudentFeedbackResponse)
def get_student_feedback(student_id: str, session_id: str = Query(...)):
    """
    Get complete 8-section feedback for a specific student.

    Returns the full professional debrief feedback structure.
    """
    feedback_file = get_student_feedback_file(session_id)

    if not feedback_file.exists():
        raise HTTPException(status_code=404, detail="Feedback not found for this session")

    with open(feedback_file, 'r') as f:
        data = json.load(f)

    # Find student's feedback
    for fb in data.get('student_feedback', []):
        if fb['student_id'] == student_id:
            return StudentFeedbackResponse(
                student_id=fb['student_id'],
                student_name=fb.get('student_name'),
                student_role=fb['student_role'],
                session_id=fb['session_id'],
                status=FeedbackStatus(fb.get('status', 'draft')),
                scenario_details=fb.get('scenario_details', {}),
                clinical_skills=fb.get('clinical_skills', []),
                abcde_assessment=fb.get('abcde_assessment'),
                non_technical_skills=fb.get('non_technical_skills', {}),
                crm_reflection=fb.get('crm_reflection', {}),
                learning_outcomes=fb.get('learning_outcomes', {}),
                evidence_chain=fb.get('evidence_chain', {}),
                references=fb.get('references', []),
                generated_at=fb.get('generated_at'),
                ai_model_version=fb.get('ai_model_version')
            )

    raise HTTPException(status_code=404, detail=f"Feedback not found for student {student_id}")


# ============================================================================
# Evidence Chain Endpoints
# ============================================================================

@router.get("/{student_id}/evidence", response_model=Dict[str, Any])
def get_feedback_evidence_chain(student_id: str, session_id: str = Query(...)):
    """
    Get full evidence chain for a student's feedback.

    Returns:
    - All evidence links with source data
    - Statistics (total by source type)
    - Validation status
    """
    feedback_file = get_student_feedback_file(session_id)

    if not feedback_file.exists():
        raise HTTPException(status_code=404, detail="Feedback not found")

    with open(feedback_file, 'r') as f:
        data = json.load(f)

    for fb in data.get('student_feedback', []):
        if fb['student_id'] == student_id:
            chain = fb.get('evidence_chain', {})

            # Compute additional stats
            links = chain.get('evidence_links', [])
            validated_count = sum(1 for l in links if l.get('doctor_validated', False))

            return {
                "student_id": student_id,
                "evidence_links": links,
                "stats": {
                    "total_links": len(links),
                    "video_evidence": chain.get('total_video_evidence', 0),
                    "audio_evidence": chain.get('total_audio_evidence', 0),
                    "vitals_evidence": chain.get('total_vitals_evidence', 0),
                    "validated_links": validated_count,
                    "pending_validation": len(links) - validated_count
                }
            }

    raise HTTPException(status_code=404, detail=f"Evidence not found for student {student_id}")


@router.get("/{student_id}/section/{section}")
def get_feedback_section(
    student_id: str,
    section: str,
    session_id: str = Query(...)
):
    """
    Get a specific section of feedback with linked moments.

    Sections: scenario_details, clinical_skills, abcde_assessment,
              non_technical_skills, crm_reflection, learning_outcomes
    """
    valid_sections = [
        'scenario_details', 'clinical_skills', 'abcde_assessment',
        'non_technical_skills', 'crm_reflection', 'learning_outcomes',
        'evidence_chain', 'references'
    ]

    if section not in valid_sections:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid section. Must be one of: {valid_sections}"
        )

    feedback_file = get_student_feedback_file(session_id)

    if not feedback_file.exists():
        raise HTTPException(status_code=404, detail="Feedback not found")

    with open(feedback_file, 'r') as f:
        data = json.load(f)

    for fb in data.get('student_feedback', []):
        if fb['student_id'] == student_id:
            section_data = fb.get(section)
            if section_data is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Section '{section}' not found"
                )

            # For sections with observations, enrich with moment data
            enriched_data = section_data
            if section == 'clinical_skills':
                enriched_data = _enrich_clinical_skills_with_moments(
                    section_data, session_id
                )

            return {
                "student_id": student_id,
                "section": section,
                "data": enriched_data
            }

    raise HTTPException(status_code=404, detail=f"Feedback not found for student {student_id}")


def _enrich_clinical_skills_with_moments(skills: List[Dict], session_id: str) -> List[Dict]:
    """Enrich clinical skills with linked moment data"""
    # Load critical moments
    moments_file = DATA_DIR / "processed" / "critical_moments.json"
    moments_index = {}

    if moments_file.exists():
        with open(moments_file, 'r') as f:
            moments_data = json.load(f)
            for m in moments_data.get('moments', []):
                moments_index[m.get('id')] = m

    # Enrich each skill's observations
    for skill in skills:
        for obs in skill.get('observations', []):
            moment_id = obs.get('moment_id')
            if moment_id and moment_id in moments_index:
                obs['linked_moment'] = moments_index[moment_id]

    return skills


# ============================================================================
# Doctor Validation Endpoints
# ============================================================================

@router.post("/{student_id}/validate-evidence")
def validate_evidence(
    student_id: str,
    request: ValidateEvidenceRequest,
    session_id: str = Query(...),
    db: DBSession = Depends(get_db)
):
    """
    Doctor validates or invalidates an evidence link.

    This action is tracked for preference learning.
    """
    feedback_file = get_student_feedback_file(session_id)

    if not feedback_file.exists():
        raise HTTPException(status_code=404, detail="Feedback not found")

    with open(feedback_file, 'r') as f:
        data = json.load(f)

    # Find and update the evidence link
    updated = False
    for fb in data.get('student_feedback', []):
        if fb['student_id'] == student_id:
            for link in fb.get('evidence_chain', {}).get('evidence_links', []):
                if link.get('moment_id') == request.evidence_id:
                    link['doctor_validated'] = request.validated
                    link['validation_notes'] = request.notes
                    updated = True
                    break
            break

    if not updated:
        raise HTTPException(status_code=404, detail="Evidence link not found")

    # Save updated feedback
    with open(feedback_file, 'w') as f:
        json.dump(data, f, indent=2, default=str)

    return {
        "status": "success",
        "evidence_id": request.evidence_id,
        "validated": request.validated
    }


@router.post("/{student_id}/edit")
def edit_feedback_section(
    student_id: str,
    request: DoctorEditRequest,
    session_id: str = Query(...),
    db: DBSession = Depends(get_db)
):
    """
    Doctor edits a feedback section.

    Tracks the edit for preference learning (DPO).
    """
    feedback_file = get_student_feedback_file(session_id)

    if not feedback_file.exists():
        raise HTTPException(status_code=404, detail="Feedback not found")

    with open(feedback_file, 'r') as f:
        data = json.load(f)

    student_found = False
    updated = False
    for fb in data.get('student_feedback', []):
        if fb['student_id'] == student_id:
            student_found = True
            # Navigate to the field and update
            section_data = fb.get(request.section)
            if section_data is None:
                raise HTTPException(status_code=404, detail=f"Section not found: {request.section}")

            # Simple field path parsing (supports dot notation like "key.subkey")
            path_parts = request.field_path.split('.')
            if not all(path_parts):
                raise HTTPException(status_code=400, detail="Invalid empty field path")
            target = section_data
            for part in path_parts[:-1]:
                if isinstance(target, dict):
                    if part not in target:
                        raise HTTPException(status_code=400, detail=f"Field not found: {part}")
                    target = target[part]
                elif isinstance(target, list) and part.isdigit():
                    index = int(part)
                    if index >= len(target):
                        raise HTTPException(status_code=400, detail=f"List index out of range: {part}")
                    target = target[index]
                else:
                    raise HTTPException(status_code=400, detail=f"Invalid field path at: {part}")

            final_key = path_parts[-1]
            if isinstance(target, dict):
                if final_key not in target:
                    raise HTTPException(status_code=400, detail=f"Field not found: {final_key}")
                target[final_key] = request.new_value
            elif isinstance(target, list) and final_key.isdigit():
                index = int(final_key)
                if index >= len(target):
                    raise HTTPException(status_code=400, detail=f"List index out of range: {final_key}")
                target[index] = request.new_value
            else:
                raise HTTPException(status_code=400, detail=f"Invalid final field: {final_key}")

            # Update status
            fb['status'] = 'doctor_reviewed'

            # Log the edit for preference learning
            # (In production, this would go to the preference_pairs table)

            updated = True
            break

    if not student_found:
        raise HTTPException(status_code=404, detail="Student feedback not found")
    if not updated:
        raise HTTPException(status_code=400, detail="Feedback field was not updated")

    # Save updated feedback
    with open(feedback_file, 'w') as f:
        json.dump(data, f, indent=2, default=str)

    return {
        "status": "success",
        "section": request.section,
        "field_path": request.field_path,
        "updated": True
    }


# ============================================================================
# Video Clip Endpoints
# ============================================================================

@router.get("/{student_id}/video-clips")
def get_student_video_clips(student_id: str, session_id: str = Query(...)):
    """
    Get video clip information for all moments related to a student.

    Returns start/end times and camera IDs for playback.
    """
    feedback_file = get_student_feedback_file(session_id)

    if not feedback_file.exists():
        raise HTTPException(status_code=404, detail="Feedback not found")

    with open(feedback_file, 'r') as f:
        data = json.load(f)

    clips = []

    for fb in data.get('student_feedback', []):
        if fb['student_id'] == student_id:
            for link in fb.get('evidence_chain', {}).get('evidence_links', []):
                clips.append({
                    "moment_id": link.get('moment_id'),
                    "camera_id": link.get('camera_id', 'cam1'),
                    "start_time": link.get('timestamp_start'),
                    "end_time": link.get('timestamp_end'),
                    "description": link.get('ai_interpretation'),
                    "source": link.get('detection_source'),
                    "confidence": link.get('confidence_score')
                })
            break

    return {
        "student_id": student_id,
        "clips": clips,
        "total_clips": len(clips)
    }


# ============================================================================
# Generate Feedback Endpoint
# ============================================================================

@router.post("/{student_id}/generate")
async def generate_student_feedback(
    student_id: str,
    session_id: str = Query(...),
    scenario_type: str = Query(default="Anaphylaxis")
):
    """
    Generate rich 8-section feedback for a student using the local LLM (Qwen 7B).

    Calls the RichFeedbackGenerator with moment/context data from the session.
    This is synchronous — takes 30-60 seconds per student.
    """
    project_root = Path(__file__).parent.parent.parent.parent

    # Add scripts to path for import
    scripts_dir = str(project_root / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    try:
        from feedback_generation.generate_student_feedback import RichFeedbackGenerator
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Cannot import feedback generator: {e}")

    # Load associations data
    assoc_path = project_root / "data" / "processed" / "moment_person_associations.json"
    if not assoc_path.exists():
        raise HTTPException(status_code=404, detail="Moment-person associations not found. Run association pipeline first.")

    with open(assoc_path) as f:
        associations = json.load(f)

    person_timelines = associations.get("person_timelines", {})

    # Identity must be exact. Substring matching can attribute one learner's
    # feedback to another similarly named track.
    if student_id not in person_timelines:
        raise HTTPException(status_code=404, detail="Student not found in associations")
    student_id_internal = student_id

    timeline = person_timelines[student_id_internal]
    role = timeline.get("role", "Student")

    # Load .env for LLM config
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")

    try:
        generator = RichFeedbackGenerator()

        feedback = generator.generate_student_feedback(
            student_id=student_id_internal,
            student_role=role,
            session_id=session_id,
            person_timeline=timeline,
            scenario_type=scenario_type
        )

        # Save to feedback file
        feedback_path = get_student_feedback_file(session_id)
        feedback_path.parent.mkdir(parents=True, exist_ok=True)

        if feedback_path.exists():
            with open(feedback_path) as f:
                existing = json.load(f)
        else:
            existing = {
                "session_id": session_id,
                "scenario_type": scenario_type,
                "model": generator.model,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "student_feedback": [],
                "summary": {"total_students": 0}
            }

        # Replace or append student feedback
        feedback_dict = feedback.model_dump()
        existing_students = existing.get("student_feedback", [])
        replaced = False
        for i, sf in enumerate(existing_students):
            if sf.get("student_id") == student_id_internal:
                existing_students[i] = feedback_dict
                replaced = True
                break
        if not replaced:
            existing_students.append(feedback_dict)

        existing["student_feedback"] = existing_students
        existing["summary"]["total_students"] = len(existing_students)
        existing["generated_at"] = datetime.now(timezone.utc).isoformat()

        with open(feedback_path, "w") as f:
            json.dump(existing, f, indent=2, default=str)

        logger.info(f"Generated feedback for {student_id_internal}, saved to {feedback_path}")

        return {
            "status": "completed",
            "student_id": student_id_internal,
            "session_id": session_id,
            "sections_generated": 8,
            "feedback": feedback_dict
        }

    except Exception as e:
        logger.exception(f"Feedback generation failed for {student_id}")
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")
