"""SQLAlchemy models matching the Alembic-managed database schema."""

from datetime import datetime, timezone
from functools import lru_cache

from fastapi import Depends
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

from app.core.config import Settings, get_settings
from app.core.database import resolve_database_url

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


@lru_cache
def _session_factory(settings: Settings):
    """Create one connection pool for each validated application configuration."""
    database_url = resolve_database_url(
        database_url=settings.database_url,
        secret_arn=settings.db_secret_arn,
        database_name=settings.db_name,
        region=settings.aws_region,
    )
    engine_options = {"pool_pre_ping": True, "pool_timeout": 3}
    if database_url.startswith(("postgresql://", "postgres://")):
        engine_options["connect_args"] = {
            "connect_timeout": 3,
            "options": "-c statement_timeout=2000",
        }
    engine = create_engine(database_url, **engine_options)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db(settings: Settings = Depends(get_settings)):
    """FastAPI dependency — yields a DB session, closes it when done."""
    db = _session_factory(settings)()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
