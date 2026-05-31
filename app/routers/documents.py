"""
Handles document upload and status checking.

POST /documents/upload  — accept a CSV file, save to DB, trigger SQS
GET  /documents/{id}/status — return current processing status
"""

from fastapi          import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm   import Session
from datetime         import datetime, timezone
import uuid

from app.models.record import Document, Record, get_db
from app.services.sqs_service import send_document_for_processing

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", status_code=202)
async def upload_document(
    file: UploadFile = File(...),
    db:   Session    = Depends(get_db),
):
    """
    1. Read the uploaded CSV content
    2. Save a Document row with status=pending
    3. Store the raw CSV in the DB (Lambda reads it from here)
    4. Send document_id to SQS
    5. Return 202 Accepted — processing happens asynchronously
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    content     = await file.read()
    document_id = str(uuid.uuid4())

    document = Document(
        id       = document_id,
        filename = file.filename,
        status   = "pending",
        raw_csv  = content.decode("utf-8"),
    )
    db.add(document)
    db.commit()

    # Trigger async processing via SQS
    # In local ENV, skip SQS (ENV=local)
    import os
    if os.getenv("ENV") != "local":
        send_document_for_processing(document_id, file.filename)
    else:
        # Local dev: parse inline so you can test without SQS
        _process_locally(document_id, db)

    return {
        "document_id": document_id,
        "status":      "pending",
        "message":     "Document accepted. Poll /documents/{id}/status for progress.",
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


def _process_locally(document_id: str, db: Session):
    """Local dev only — parse the CSV immediately without going through SQS/Lambda."""
    import csv, io
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        return
    try:
        reader = csv.DictReader(io.StringIO(doc.raw_csv))
        for row in reader:
            record = Record(
                id          = str(uuid.uuid4()),
                document_id = document_id,
                date        = row.get("date", ""),
                description = row.get("description", ""),
                amount      = float(row.get("amount", 0) or 0),
                category    = row.get("category", "Uncategorised"),
            )
            db.add(record)
        doc.status     = "completed"
        doc.updated_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as e:
        doc.status    = "failed"
        doc.error_msg = str(e)
        db.commit()
