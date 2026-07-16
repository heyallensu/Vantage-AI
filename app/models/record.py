"""SQLAlchemy models matching the Alembic-managed database schema."""

import os
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class Document(Base):
    """
    Tracks each uploaded file and its processing state.
    Status flow: pending → processing → completed | failed
    """
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_documents_status",
        ),
        Index("ix_documents_status", "status"),
        Index("ix_documents_created_at", "created_at"),
    )

    id = Column(String, primary_key=True)
    filename = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    object_key = Column(String, nullable=True)
    checksum_sha256 = Column(String(64), nullable=True)
    trace_id = Column(String, nullable=True)
    processing_attempts = Column(Integer, nullable=False, default=0)
    error_msg = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Record(Base):
    """
    A single extracted row from a processed document.
    Lambda writes these after parsing the CSV.
    """
    __tablename__ = "records"
    __table_args__ = (
        Index("ix_records_document_id", "document_id"),
        Index("ix_records_category", "category"),
        Index("ix_records_created_at", "created_at"),
    )

    id = Column(String, primary_key=True)
    document_id = Column(
        String,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    date = Column(String, nullable=True)
    description = Column(String, nullable=True)
    amount = Column(Float, nullable=True)
    category = Column(String, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


# ─── Database connection ──────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://vantage:vantage@db:5432/vantage")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI dependency — yields a DB session, closes it when done."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
