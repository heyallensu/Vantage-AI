"""
SQLAlchemy models — define the database tables.
Run create_tables() on startup to create them if they don't exist.
"""

from sqlalchemy import Column, String, Float, DateTime, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone
import os

Base = declarative_base()


class Document(Base):
    """
    Tracks each uploaded file and its processing state.
    Status flow: pending → processing → completed | failed
    """
    __tablename__ = "documents"

    id          = Column(String, primary_key=True)   # UUID
    filename    = Column(String, nullable=False)
    status      = Column(String, default="pending")  # pending | processing | completed | failed
    raw_csv     = Column(Text, nullable=True)         # stored temporarily until Lambda processes it
    error_msg   = Column(Text, nullable=True)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Record(Base):
    """
    A single extracted row from a processed document.
    Lambda writes these after parsing the CSV.
    """
    __tablename__ = "records"

    id          = Column(String, primary_key=True)   # UUID
    document_id = Column(String, nullable=False)      # FK to documents.id
    date        = Column(String, nullable=True)
    description = Column(String, nullable=True)
    amount      = Column(Float,  nullable=True)
    category    = Column(String, nullable=True)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ─── Database connection ──────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@db:5432/vantage")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def create_tables():
    """Call this once on app startup to create tables if they don't exist."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency — yields a DB session, closes it when done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
