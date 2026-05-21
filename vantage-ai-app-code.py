# =============================================================
# Vantage AI — Application Code
# This is the code a developer writes.
# DevOps deploys it. You need to understand what it does.
# =============================================================

# ─── File: app/models/record.py ──────────────────────────────
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


# ─── File: app/services/sqs_service.py ───────────────────────
"""
Sends messages to SQS.
The API calls this after saving a document — Lambda will pick it up.
"""

import boto3
import json
import os

sqs = boto3.client("sqs", region_name=os.getenv("AWS_DEFAULT_REGION", "ap-southeast-2"))

SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL", "")  # set in ECS task environment


def send_document_for_processing(document_id: str, filename: str) -> str:
    """
    Put a message on the SQS queue.
    Lambda will receive this and parse the document.
    Returns the SQS message ID.
    """
    message = {
        "document_id": document_id,
        "filename": filename,
    }
    response = sqs.send_message(
        QueueUrl=SQS_QUEUE_URL,
        MessageBody=json.dumps(message),
    )
    return response["MessageId"]


# ─── File: app/services/bedrock_service.py ───────────────────
"""
Calls Amazon Bedrock Claude Haiku.
Used by the /insights endpoints to analyse records.
"""

import boto3
import json
import os

bedrock = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_DEFAULT_REGION", "ap-southeast-2"))

MODEL_ID = "anthropic.claude-haiku-20240307-v1:0"


def ask_claude(prompt: str, max_tokens: int = 800) -> str:
    """Send a prompt to Claude Haiku and return the text response."""
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    })
    response = bedrock.invoke_model(modelId=MODEL_ID, body=body)
    result   = json.loads(response["body"].read())
    return result["content"][0]["text"]


def analyze_records(records: list[dict]) -> dict:
    """
    Ask Claude to analyse a list of transaction records.
    Instructs Claude to return structured JSON only — no extra text.
    """
    records_text = json.dumps(records, indent=2)
    prompt = f"""You are a financial analyst.
Analyse these records and respond ONLY with valid JSON:
{{
  "total_amount": <float>,
  "record_count": <int>,
  "top_categories": ["<category>", ...],
  "summary": "<2-3 sentence plain English summary>",
  "anomalies": ["<anomaly description>", ...]
}}
Records:
{records_text}"""
    raw = ask_claude(prompt)
    return json.loads(raw)


def generate_summary(records: list[dict]) -> str:
    """Ask Claude for a plain English summary of the dataset."""
    records_text = json.dumps(records[:50], indent=2)  # limit to avoid token overflow
    prompt = f"""Summarise these business records in 3-4 sentences. Focus on patterns, totals, and anything unusual.
Records:
{records_text}"""
    return ask_claude(prompt, max_tokens=400)


def find_anomalies(records: list[dict]) -> list[str]:
    """Ask Claude to identify anomalous records."""
    records_text = json.dumps(records, indent=2)
    prompt = f"""You are an auditor. Identify any anomalous or suspicious records from this dataset.
Return ONLY a JSON array of strings, each describing one anomaly. Example: ["Unusually large amount on 2024-01-15", ...]
If there are no anomalies, return an empty array: []
Records:
{records_text}"""
    raw = ask_claude(prompt)
    return json.loads(raw)


# ─── File: app/routers/documents.py ──────────────────────────
"""
Handles document upload and status checking.

POST /documents/upload  — accept a CSV file, save to DB, trigger SQS
GET  /documents/{id}/status — return current processing status
"""

from fastapi          import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm   import Session
from datetime         import datetime, timezone
import uuid

# from models.record    import Document, get_db          # uncomment in real project
# from services.sqs_service import send_document_for_processing

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
                amount      = float(row.get("amount", 0)),
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


# ─── File: app/routers/records.py ────────────────────────────
"""
Query extracted records.

GET /records           — list all records (with optional filters)
GET /records/{id}      — single record
"""

from fastapi        import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing         import Optional

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


# ─── File: app/routers/insights.py ───────────────────────────
"""
AI-powered analysis endpoints.

POST /insights/analyze    — full analysis of a document's records
GET  /insights/summary    — plain English summary
GET  /insights/anomalies  — AI-flagged anomalies
"""

from fastapi        import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing         import Optional

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
    return analyze_records(records)


@router_insights.get("/summary")
def summary(
    document_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Return a plain English summary of the dataset."""
    records = _get_records_for_analysis(document_id, db)
    return {"summary": generate_summary(records)}


@router_insights.get("/anomalies")
def anomalies(
    document_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Return a list of anomalies flagged by AI."""
    records = _get_records_for_analysis(document_id, db)
    return {"anomalies": find_anomalies(records)}


# ─── File: app/main.py ───────────────────────────────────────
"""
FastAPI entry point.
Registers all routers and creates DB tables on startup.
"""

from fastapi import FastAPI

app = FastAPI(
    title       = "Vantage AI API",
    description = "Intelligent Document Processing Platform",
    version     = "1.0.0",
)

# Create DB tables on startup (idempotent — safe to call every time)
@app.on_event("startup")
def startup():
    create_tables()

# Register routers
app.include_router(router)           # /documents
app.include_router(router_records)   # /records
app.include_router(router_insights)  # /insights

@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


# ─── File: lambda/processor/handler.py ───────────────────────
"""
Lambda function — triggered by SQS.

Flow:
1. SQS sends a batch of messages (each = one document to process)
2. Lambda reads document_id from message body
3. Fetches the raw CSV from RDS
4. Parses CSV rows → inserts Record rows into RDS
5. Updates document status to completed (or failed)

Why Lambda instead of doing this in the API?
→ Decoupled: API never waits for parsing to finish
→ Retry: SQS retries failed messages automatically
→ Scale: Lambda scales independently from ECS
"""

import json
import csv
import io
import os
import uuid
import psycopg2
from datetime import datetime, timezone


DATABASE_URL = os.environ["DATABASE_URL"]  # set in Lambda environment variables


def get_connection():
    """Open a fresh PostgreSQL connection (Lambda is stateless, no connection pool)."""
    import re
    # Parse postgresql://user:pass@host:port/dbname
    match = re.match(r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", DATABASE_URL)
    user, password, host, port, dbname = match.groups()
    return psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)


def parse_csv(raw_csv: str, document_id: str) -> list[dict]:
    """
    Parse the raw CSV content into a list of record dicts.
    Expects columns: date, description, amount, category
    Missing columns get sensible defaults.
    """
    reader  = csv.DictReader(io.StringIO(raw_csv))
    records = []
    for row in reader:
        records.append({
            "id":          str(uuid.uuid4()),
            "document_id": document_id,
            "date":        row.get("date", "").strip(),
            "description": row.get("description", "").strip(),
            "amount":      float(row.get("amount", 0) or 0),
            "category":    row.get("category", "Uncategorised").strip(),
            "created_at":  datetime.now(timezone.utc).isoformat(),
        })
    return records


def process_document(document_id: str, conn) -> None:
    """
    Fetch document from DB, parse its CSV, insert records, update status.
    Raises an exception if anything goes wrong — SQS will retry.
    """
    cur = conn.cursor()

    # 1. Mark as processing
    cur.execute(
        "UPDATE documents SET status = %s, updated_at = %s WHERE id = %s",
        ("processing", datetime.now(timezone.utc), document_id)
    )
    conn.commit()

    # 2. Read raw CSV
    cur.execute("SELECT raw_csv FROM documents WHERE id = %s", (document_id,))
    row = cur.fetchone()
    if not row or not row[0]:
        raise ValueError(f"Document {document_id} not found or has no CSV content")

    raw_csv = row[0]

    # 3. Parse CSV → insert records
    records = parse_csv(raw_csv, document_id)
    if records:
        cur.executemany(
            """INSERT INTO records (id, document_id, date, description, amount, category, created_at)
               VALUES (%(id)s, %(document_id)s, %(date)s, %(description)s, %(amount)s, %(category)s, %(created_at)s)
               ON CONFLICT (id) DO NOTHING""",
            records
        )

    # 4. Mark as completed
    cur.execute(
        "UPDATE documents SET status = %s, updated_at = %s WHERE id = %s",
        ("completed", datetime.now(timezone.utc), document_id)
    )
    conn.commit()
    cur.close()

    print(f"[OK] document_id={document_id} → {len(records)} records inserted")


def handler(event, context):
    """
    Lambda entry point.

    SQS delivers messages in batches. We process each one.
    If a record fails, we raise an exception so SQS can retry it.
    Use 'batchItemFailures' to only retry failed messages (not the whole batch).
    """
    conn             = get_connection()
    batch_failures   = []

    for record in event.get("Records", []):
        message_id = record["messageId"]
        try:
            body        = json.loads(record["body"])
            document_id = body["document_id"]
            process_document(document_id, conn)

        except Exception as e:
            print(f"[ERROR] messageId={message_id} failed: {e}")

            # Mark document as failed in DB
            try:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE documents SET status = %s, error_msg = %s, updated_at = %s WHERE id = %s",
                    ("failed", str(e), datetime.now(timezone.utc), body.get("document_id", "unknown"))
                )
                conn.commit()
                cur.close()
            except Exception:
                pass

            # Tell SQS to retry only this message
            batch_failures.append({"itemIdentifier": message_id})

    conn.close()
    return {"batchItemFailures": batch_failures}


# ─── File: app/requirements.txt ──────────────────────────────
REQUIREMENTS_APP = """
fastapi==0.110.0
uvicorn==0.29.0
boto3==1.34.0
sqlalchemy==2.0.29
psycopg2-binary==2.9.9
python-multipart==0.0.9
""".strip()

# ─── File: lambda/processor/requirements.txt ─────────────────
REQUIREMENTS_LAMBDA = """
psycopg2-binary==2.9.9
""".strip()

# ─── Sample test CSV ─────────────────────────────────────────
SAMPLE_CSV = """date,description,amount,category
2024-01-05,AWS Cloud Services,1250.00,Technology
2024-01-08,Office Supplies,89.50,Operations
2024-01-10,Team Lunch,320.00,Entertainment
2024-01-15,Software Licences,499.00,Technology
2024-01-18,Marketing Campaign,5000.00,Marketing
2024-01-20,Office Supplies,45.00,Operations
2024-01-22,Consulting Fee,12000.00,Professional Services
2024-01-25,AWS Cloud Services,980.00,Technology
2024-01-28,Team Lunch,150.00,Entertainment
2024-01-30,Unexpected Transfer,75000.00,Unknown
""".strip()

# Save sample CSV separately
print("All code blocks above — split into their respective files.")
print("Sample CSV content available for testing.")
