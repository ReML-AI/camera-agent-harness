"""Feedback-related endpoints"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession
from pydantic import BaseModel
from typing import List, Optional
import json
import uuid

from ..database import get_db, FeedbackEvaluation

router = APIRouter()


class FeedbackItem(BaseModel):
    text: str
    type: str  # positive, negative, learning_point
    action: Optional[str] = None  # accept, edit, reject
    edited_text: Optional[str] = None


class RubricScores(BaseModel):
    team_communication: Optional[int] = None
    technical_skills: Optional[int] = None
    response_time: Optional[int] = None
    leadership: Optional[int] = None
    overall: Optional[int] = None


class SaveFeedbackRequest(BaseModel):
    session_id: str
    moment_id: int
    feedback_items: List[FeedbackItem]
    rubric_scores: RubricScores
    comments: Optional[str] = None
    evaluator_id: str


@router.post("/")
def save_feedback(request: SaveFeedbackRequest, db: DBSession = Depends(get_db)):
    """Save feedback evaluation"""
    feedback_id = str(uuid.uuid4())

    evaluation = FeedbackEvaluation(
        id=feedback_id,
        session_id=request.session_id,
        moment_id=request.moment_id,
        ai_feedback_json=json.dumps([item.model_dump() for item in request.feedback_items]),
        rubric_scores_json=json.dumps(request.rubric_scores.model_dump()),
        comments=request.comments,
        evaluator_id=request.evaluator_id
    )

    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)

    return {
        "id": feedback_id,
        "moment_id": request.moment_id,
        "status": "saved"
    }


@router.get("/session/{session_id}")
def get_session_feedback(session_id: str, db: DBSession = Depends(get_db)):
    """Get all feedback for a session"""
    evaluations = (
        db.query(FeedbackEvaluation)
        .filter(FeedbackEvaluation.session_id == session_id)
        .all()
    )

    return {
        "session_id": session_id,
        "evaluations": [
            {
                "id": e.id,
                "moment_id": e.moment_id,
                "feedback_items": json.loads(e.ai_feedback_json) if e.ai_feedback_json else [],
                "rubric_scores": json.loads(e.rubric_scores_json) if e.rubric_scores_json else {},
                "comments": e.comments,
                "evaluated_at": e.evaluated_at.isoformat() if e.evaluated_at else None
            }
            for e in evaluations
        ]
    }
