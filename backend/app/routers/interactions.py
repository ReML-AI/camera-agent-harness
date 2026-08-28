"""Basic educator interaction audit endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession
from pydantic import BaseModel
from typing import Optional, Dict, Any
import json
import uuid
from datetime import datetime

from ..database import get_db, Interaction

router = APIRouter()


class LogInteractionRequest(BaseModel):
    session_id: str
    moment_id: Optional[int] = None
    interaction_type: str
    data: Dict[str, Any]


@router.post("/")
def log_interaction(request: LogInteractionRequest, db: DBSession = Depends(get_db)):
    """Log a user interaction without invoking a learning or deployment path."""
    interaction_id = str(uuid.uuid4())

    interaction = Interaction(
        id=interaction_id,
        session_id=request.session_id,
        moment_id=request.moment_id,
        interaction_type=request.interaction_type,
        data_json=json.dumps(request.data),
        timestamp=datetime.utcnow()
    )

    db.add(interaction)
    db.commit()

    return {"id": interaction_id, "status": "logged"}


@router.get("/export")
def export_interactions(db: DBSession = Depends(get_db)):
    """Export the educator audit trail."""
    interactions = db.query(Interaction).all()

    return {
        "total_interactions": len(interactions),
        "interactions": [
            {
                "id": i.id,
                "session_id": i.session_id,
                "moment_id": i.moment_id,
                "type": i.interaction_type,
                "data": json.loads(i.data_json) if i.data_json else {},
                "timestamp": i.timestamp.isoformat() if i.timestamp else None
            }
            for i in interactions
        ]
    }
