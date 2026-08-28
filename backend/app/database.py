"""Database setup and models"""
from sqlalchemy import create_engine, Column, String, Float, Integer, Text, TIMESTAMP, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone
import os

# Database file location
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sessions.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class Session(Base):
    """Clinical simulation session"""
    __tablename__ = "sessions"

    id = Column(String, primary_key=True)
    date = Column(String, nullable=False)
    student_id = Column(String)
    evaluator_id = Column(String)
    status = Column(String, default="pending")
    created_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


class Moment(Base):
    """Critical moment in a session"""
    __tablename__ = "moments"

    id = Column(Integer, primary_key=True)
    session_id = Column(String)
    start_time = Column(Float)
    end_time = Column(Float)
    severity = Column(String)
    confidence = Column(Float)
    sources_json = Column(Text)
    summary = Column(Text)


class FeedbackEvaluation(Base):
    """Doctor's evaluation of AI-generated feedback"""
    __tablename__ = "feedback_evaluations"

    id = Column(String, primary_key=True)
    session_id = Column(String, index=True)
    moment_id = Column(Integer)
    ai_feedback_json = Column(Text)
    doctor_action = Column(String)  # accept, edit, reject
    edited_text = Column(Text)
    rubric_scores_json = Column(Text)
    comments = Column(Text)
    evaluated_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    evaluator_id = Column(String)


class Interaction(Base):
    """Implicit feedback from user interactions"""
    __tablename__ = "interactions"

    id = Column(String, primary_key=True)
    session_id = Column(String)
    moment_id = Column(Integer)
    interaction_type = Column(String)
    data_json = Column(Text)
    timestamp = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


class Student(Base):
    """Student profile"""
    __tablename__ = "students"

    id = Column(String, primary_key=True)
    name = Column(String)
    role = Column(String)
    profile_json = Column(Text)


class Report(Base):
    """Generated debrief report"""
    __tablename__ = "reports"

    id = Column(String, primary_key=True)
    session_id = Column(String)
    content_md = Column(Text)
    generated_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)
    # Preserve older local prototype databases created before feedback was scoped by
    # session. Existing rows remain unscoped and are intentionally not returned by a
    # session query.
    columns = {column["name"] for column in inspect(engine).get_columns("feedback_evaluations")}
    if "session_id" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE feedback_evaluations ADD COLUMN session_id VARCHAR"))
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_feedback_evaluations_session_id "
                    "ON feedback_evaluations (session_id)"
                )
            )


def get_db():
    """Dependency for FastAPI routes"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
