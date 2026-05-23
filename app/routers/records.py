"""
Query extracted records.

GET /records           — list all records (with optional filters)
GET /records/{id}      — single record
"""

from fastapi        import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing         import Optional

from app.models.record import Record, get_db

router_records = APIRouter(prefix="/records", tags=["records"])


@router_records.get("")
def list_records(
    document_id: Optional[str] = Query(None, description="Filter by document"),
    category:    Optional[str] = Query(None, description="Filter by category"),
    limit:       int           = Query(100, le=1000),
    db:          Session       = Depends(get_db),
):
    """Return extracted records. Optionally filter by document or category."""
    query = db.query(Record)
    if document_id:
        query = query.filter(Record.document_id == document_id)
    if category:
        query = query.filter(Record.category == category)
    records = query.limit(limit).all()

    return [
        {
            "id":          r.id,
            "document_id": r.document_id,
            "date":        r.date,
            "description": r.description,
            "amount":      r.amount,
            "category":    r.category,
        }
        for r in records
    ]


@router_records.get("/{record_id}")
def get_record(record_id: str, db: Session = Depends(get_db)):
    """Return a single record by ID."""
    record = db.query(Record).filter(Record.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record
