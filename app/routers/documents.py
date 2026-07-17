"""
Handles document upload and status checking.

POST /documents/upload  — accept a CSV file, save to DB, trigger SQS
GET  /documents/{id}/status — return current processing status
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.contracts.document_job import DocumentJob
from app.core.config import Settings, get_settings
from app.models.record import Document, Record, get_db
from app.services.csv_service import parse_financial_csv
from app.services.sqs_service import QueuePublishError, send_document_for_processing
from app.services.storage_service import (
    MAX_UPLOAD_BYTES,
    DocumentStorage,
    StorageError,
    UploadValidationError,
    build_object_key,
    get_document_storage,
    validate_csv_upload,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", status_code=202)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    storage: DocumentStorage = Depends(get_document_storage),
    settings: Settings = Depends(get_settings),
):
    """
    1. Read the uploaded CSV content
    2. Save a Document row with status=pending
    3. Store the validated source document through the configured adapter
    4. Publish a versioned document job to SQS
    5. Return 202 Accepted — processing happens asynchronously
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        validated = validate_csv_upload(content)
    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    document_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    object_key = build_object_key(document_id)

    document = Document(
        id=document_id,
        filename=file.filename,
        status="pending",
        object_key=object_key,
        checksum_sha256=validated.checksum_sha256,
        trace_id=trace_id,
    )
    db.add(document)
    db.commit()

    try:
        stored = await run_in_threadpool(storage.store, document_id, content)
        document.object_key = stored.object_key
        document.checksum_sha256 = stored.checksum_sha256
        db.commit()

        if not settings.is_local:
            await run_in_threadpool(
                send_document_for_processing,
                DocumentJob(
                    schema_version=1,
                    document_id=document_id,
                    bucket=storage.bucket_name,
                    object_key=stored.object_key,
                    checksum_sha256=stored.checksum_sha256,
                    trace_id=trace_id,
                ),
                queue_url=settings.sqs_queue_url,
                region=settings.aws_region,
            )
        else:
            _process_locally(document_id, db, storage)
    except (StorageError, QueuePublishError, RuntimeError) as exc:
        db.rollback()
        failed_document = db.query(Document).filter(Document.id == document_id).first()
        if failed_document:
            failed_document.status = "failed"
            failed_document.error_msg = str(exc)
            failed_document.updated_at = datetime.now(timezone.utc)
            db.commit()
        raise HTTPException(status_code=502, detail="Document processing could not be queued") from exc

    return {
        "document_id": document_id,
        "status": document.status,
        "message": "Document accepted. Poll /documents/{id}/status for progress.",
    }


@router.get("/{document_id}/status")
def get_status(document_id: str, db: Session = Depends(get_db)):
    """Return the current processing status of a document."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "document_id": doc.id,
        "filename":    doc.filename,
        "status":      doc.status,
        "error":       doc.error_msg,
        "created_at":  doc.created_at,
        "updated_at":  doc.updated_at,
    }


def _process_locally(document_id: str, db: Session, storage: DocumentStorage) -> None:
    """Local dev only — parse the CSV immediately without going through SQS/Lambda."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        return
    try:
        content = storage.read(doc.object_key or "")
        rows = parse_financial_csv(content.decode("utf-8"))
        db.query(Record).filter(Record.document_id == document_id).delete()
        for row in rows:
            record = Record(
                id          = str(uuid.uuid4()),
                document_id = document_id,
                date        = row["date"],
                description = row["description"],
                amount      = row["amount"],
                category    = row["category"],
            )
            db.add(record)
        doc.status = "completed"
        doc.processing_attempts += 1
        doc.updated_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        db.rollback()
        failed_document = db.query(Document).filter(Document.id == document_id).first()
        if not failed_document:
            return
        failed_document.status = "failed"
        failed_document.processing_attempts += 1
        failed_document.error_msg = str(exc)
        failed_document.updated_at = datetime.now(timezone.utc)
        db.commit()
