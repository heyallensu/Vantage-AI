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

import csv
import io
import json
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import unquote, urlparse

import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]  # set in Lambda environment variables


def get_connection():
    """Open a fresh PostgreSQL connection (Lambda is stateless, no connection pool)."""
    parsed = urlparse(DATABASE_URL)
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise ValueError("DATABASE_URL must use postgresql:// or postgres://")
    if not parsed.hostname or not parsed.path.lstrip("/"):
        raise ValueError("DATABASE_URL must include host and database name")

    user = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    host = parsed.hostname
    port = parsed.port or 5432
    dbname = parsed.path.lstrip("/")
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
        cur.execute("DELETE FROM records WHERE document_id = %s", (document_id,))
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
        body = {}
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
