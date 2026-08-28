from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.routers.feedback import (
    FeedbackItem,
    RubricScores,
    SaveFeedbackRequest,
    get_session_feedback,
    save_feedback,
)


def test_feedback_is_scoped_to_its_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        for session_id, moment_id in (("session_a", 1), ("session_b", 2)):
            save_feedback(
                SaveFeedbackRequest(
                    session_id=session_id,
                    moment_id=moment_id,
                    feedback_items=[FeedbackItem(text="reviewed", type="positive")],
                    rubric_scores=RubricScores(overall=4),
                    evaluator_id="reviewer",
                ),
                db,
            )

        result = get_session_feedback("session_a", db)
        assert [item["moment_id"] for item in result["evaluations"]] == [1]
    finally:
        db.close()
