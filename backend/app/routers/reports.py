"""Report generation endpoints"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as DBSession
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import json
import uuid
import io

from ..database import get_db, Report
from ..services.report_generator import generate_debrief_report
from ..services.slide_generator import generate_presentation_slides, generate_student_presentation_slides
from ..services.pptx_exporter import export_to_powerpoint

router = APIRouter()


class GenerateReportRequest(BaseModel):
    session_id: str
    moments: List[Dict[str, Any]]
    evaluations: List[Dict[str, Any]]
    student_name: Optional[str] = "Student"
    evaluator_name: Optional[str] = "Dr. Evaluator"


@router.post("/generate")
def generate_report(request: GenerateReportRequest, db: DBSession = Depends(get_db)):
    """Generate a debrief report"""

    # Generate markdown report
    report_content = generate_debrief_report(
        session_id=request.session_id,
        moments=request.moments,
        evaluations=request.evaluations,
        student_name=request.student_name,
        evaluator_name=request.evaluator_name
    )

    # Save to database
    report_id = str(uuid.uuid4())
    report = Report(
        id=report_id,
        session_id=request.session_id,
        content_md=report_content
    )

    db.add(report)
    db.commit()
    db.refresh(report)

    return {
        "id": report_id,
        "session_id": request.session_id,
        "content": report_content,
        "status": "generated"
    }


@router.get("/{report_id}")
def get_report(report_id: str, db: DBSession = Depends(get_db)):
    """Get a generated report"""
    report = db.query(Report).filter(Report.id == report_id).first()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    return {
        "id": report.id,
        "session_id": report.session_id,
        "content": report.content_md,
        "generated_at": report.generated_at.isoformat() if report.generated_at else None
    }


@router.get("/session/{session_id}")
def get_session_reports(session_id: str, db: DBSession = Depends(get_db)):
    """Get all reports for a session"""
    reports = db.query(Report).filter(Report.session_id == session_id).all()

    return {
        "session_id": session_id,
        "reports": [
            {
                "id": r.id,
                "generated_at": r.generated_at.isoformat() if r.generated_at else None
            }
            for r in reports
        ]
    }


@router.post("/slides")
def generate_slides(request: GenerateReportRequest):
    """Generate presentation slides for debrief session"""
    from pathlib import Path

    # Load transcript if available
    transcript = None
    data_dir = Path(__file__).parent.parent.parent.parent / "data"
    transcript_file = data_dir / "processed" / "diarized_transcript_full.json"
    if transcript_file.exists():
        with open(transcript_file, 'r') as f:
            transcript = json.load(f)

    # Generate slides
    slides = generate_presentation_slides(
        session_id=request.session_id,
        moments=request.moments,
        evaluations=request.evaluations,
        student_name=request.student_name,
        evaluator_name=request.evaluator_name,
        transcript=transcript,
    )

    return {
        "session_id": request.session_id,
        "total_slides": len(slides),
        "slides": slides
    }


class ExportPPTXRequest(BaseModel):
    session_id: str
    slides: List[Dict[str, Any]]


@router.post("/export-pptx")
def export_pptx(request: ExportPPTXRequest):
    """Export slides to PowerPoint format"""

    # Generate PowerPoint file
    pptx_bytes = export_to_powerpoint(
        session_id=request.session_id,
        slides=request.slides
    )

    # Return as downloadable file
    return StreamingResponse(
        io.BytesIO(pptx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={
            "Content-Disposition": f"attachment; filename=clinical-debrief-{request.session_id}.pptx"
        }
    )


# ============================================================================
# Per-Student Presentation Endpoints (Phase 3)
# ============================================================================

class StudentSlidesRequest(BaseModel):
    """Request for generating per-student presentation slides"""
    session_id: str
    student_id: str


@router.post("/student-slides")
def generate_student_slides(request: StudentSlidesRequest):
    """
    Generate presentation slides for a specific student's debrief.

    Uses the 8-section rich feedback to create a professional presentation.
    """
    from pathlib import Path

    # Load student feedback
    data_dir = Path(__file__).parent.parent.parent.parent / "data"
    feedback_file = data_dir / "processed" / f"student_feedback_{request.session_id}.json"

    if not feedback_file.exists():
        raise HTTPException(status_code=404, detail="Student feedback not found")

    with open(feedback_file, 'r') as f:
        data = json.load(f)

    # Find student's feedback
    student_feedback = None
    for fb in data.get('student_feedback', []):
        if fb['student_id'] == request.student_id:
            student_feedback = fb
            break

    if not student_feedback:
        raise HTTPException(status_code=404, detail=f"Feedback not found for student {request.student_id}")

    # Load transcript if available
    transcript = None
    transcript_file = data_dir / "processed" / "diarized_transcript_full.json"
    if transcript_file.exists():
        with open(transcript_file, 'r') as f:
            transcript = json.load(f)

    # Generate slides using unified generator
    slides = generate_student_presentation_slides(
        feedback=student_feedback,
        transcript=transcript,
    )

    return {
        "session_id": request.session_id,
        "student_id": request.student_id,
        "total_slides": len(slides),
        "slides": slides
    }


@router.post("/student-pptx")
def export_student_pptx(request: StudentSlidesRequest):
    """Export per-student presentation to PowerPoint"""

    # First generate slides
    slides_response = generate_student_slides(request)
    slides = slides_response['slides']

    # Export to PPTX
    pptx_bytes = export_to_powerpoint(
        session_id=request.session_id,
        slides=slides
    )

    filename = f"debrief-{request.student_id}-{request.session_id}.pptx"

    return StreamingResponse(
        io.BytesIO(pptx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )
