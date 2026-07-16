"""
AI-powered analysis endpoints.

POST /insights/analyze    — full analysis of a document's records
GET  /insights/summary    — plain English summary
GET  /insights/anomalies  — AI-flagged anomalies
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.models.record import Record, get_db
from app.services.bedrock_service import (
    BedrockServiceError,
    analyze_records,
    find_anomalies,
    generate_summary,
)

router_insights = APIRouter(prefix="/insights", tags=["insights"])


def _get_records_for_analysis(document_id: Optional[str], db: Session) -> list[dict]:
    """Fetch records from DB, return as list of dicts for Bedrock."""
    query = db.query(Record)
    if document_id:
        query = query.filter(Record.document_id == document_id)
    records = query.limit(200).all()
    if not records:
        raise HTTPException(status_code=404, detail="No records found. Has the document been processed?")
    return [
        {"date": r.date, "description": r.description, "amount": r.amount, "category": r.category}
        for r in records
    ]


@router_insights.post("/analyze")
def analyze(
    document_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Run a full AI analysis on all records for a document.
    Returns: totals, top categories, summary, anomalies.
    """
    records = _get_records_for_analysis(document_id, db)
    try:
        return analyze_records(records)
    except BedrockServiceError as exc:
        raise _bedrock_http_error() from exc


@router_insights.get("/summary")
def summary(
    document_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Return a plain English summary of the dataset."""
    records = _get_records_for_analysis(document_id, db)
    try:
        return {"summary": generate_summary(records)}
    except BedrockServiceError as exc:
        raise _bedrock_http_error() from exc


@router_insights.get("/anomalies")
def anomalies(
    document_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Return a list of anomalies flagged by AI."""
    records = _get_records_for_analysis(document_id, db)
    try:
        return {"anomalies": find_anomalies(records)}
    except BedrockServiceError as exc:
        raise _bedrock_http_error() from exc


def _bedrock_http_error() -> HTTPException:
    return HTTPException(status_code=502, detail="AI analysis is temporarily unavailable")
