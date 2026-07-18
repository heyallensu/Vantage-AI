"""SQS-triggered Lambda processor for versioned S3 document jobs."""

import csv
import hashlib
import io
import json
import math
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

import boto3
import psycopg2

JOB_FIELDS = {
    "schema_version",
    "document_id",
    "bucket",
    "object_key",
    "checksum_sha256",
    "trace_id",
}
REQUIRED_HEADERS = {"date", "description", "amount", "category"}
s3 = boto3.client("s3", region_name=os.getenv("AWS_DEFAULT_REGION", "ap-southeast-2"))


def get_connection():
    """Open a fresh PostgreSQL connection from the Lambda runtime configuration."""
    return psycopg2.connect(resolve_database_url())


def resolve_database_url(*, client=None) -> str:
    """Resolve local DATABASE_URL or assemble one from the managed RDS secret."""
    database_url = os.getenv("DATABASE_URL", "")
    if database_url:
        return database_url

    secret_arn = os.getenv("DB_SECRET_ARN", "")
    if not secret_arn:
        raise RuntimeError("DATABASE_URL or DB_SECRET_ARN is required")
    secrets_client = client or boto3.client(
        "secretsmanager",
        region_name=os.getenv("AWS_DEFAULT_REGION", "ap-southeast-2"),
    )
    response = secrets_client.get_secret_value(SecretId=secret_arn)
    try:
        secret = json.loads(response["SecretString"])
        username = str(secret["username"])
        password = str(secret["password"])
        host = str(secret.get("host") or os.getenv("DB_HOST", ""))
        port = int(secret.get("port", os.getenv("DB_PORT", "5432")))
        database = str(
            secret.get("dbname") or secret.get("database") or os.getenv("DB_NAME", "")
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Database secret does not match the expected RDS JSON contract") from exc
    if not all((username, password, host, database)):
        raise RuntimeError("Database secret is missing required connection fields")
    return (
        f"postgresql://{quote(username, safe='')}:{quote(password, safe='')}@"
        f"{host}:{port}/{quote(database, safe='')}"
    )


def parse_job(message_body: str) -> dict:
    """Parse and strictly validate the supported v1 queue contract."""
    job = json.loads(message_body)
    if not isinstance(job, dict) or set(job) != JOB_FIELDS:
        raise ValueError("Document job must contain exactly the v1 contract fields")
    if job["schema_version"] != 1:
        raise ValueError("Unsupported document job schema_version")
    for field in JOB_FIELDS - {"schema_version"}:
        if not isinstance(job[field], str) or not job[field]:
            raise ValueError(f"Document job field {field} must be a non-empty string")
    checksum = job["checksum_sha256"]
    if len(checksum) != 64 or any(character not in "0123456789abcdef" for character in checksum):
        raise ValueError("Document job checksum_sha256 must be a lowercase SHA-256 digest")
    return job


def fetch_csv(job: dict) -> str:
    """Download the source object and verify its checksum and encoding."""
    response = s3.get_object(Bucket=job["bucket"], Key=job["object_key"])
    content = response["Body"].read()
    actual_checksum = hashlib.sha256(content).hexdigest()
    if actual_checksum != job["checksum_sha256"]:
        raise ValueError("Document checksum does not match the queue contract")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Stored document must contain valid UTF-8") from exc


def parse_csv(raw_csv: str, document_id: str) -> list[dict]:
    """Validate and parse the expected financial operations CSV schema."""
    reader = csv.DictReader(io.StringIO(raw_csv))
    normalized_headers = [
        header.strip() if header is not None else ""
        for header in (reader.fieldnames or [])
    ]
    if not normalized_headers or any(not header for header in normalized_headers):
        raise ValueError("CSV headers must be non-empty")
    if len(normalized_headers) != len(set(normalized_headers)):
        raise ValueError("CSV headers must be unique after whitespace normalization")
    reader.fieldnames = normalized_headers
    headers = set(normalized_headers)
    missing_headers = sorted(REQUIRED_HEADERS - headers)
    if missing_headers:
        raise ValueError(f"Missing required CSV headers: {', '.join(missing_headers)}")

    records = []
    for row_number, row in enumerate(reader, start=2):
        try:
            amount = float(row.get("amount", 0) or 0)
        except ValueError as exc:
            raise ValueError(f"Invalid amount on row {row_number}") from exc
        if not math.isfinite(amount):
            raise ValueError(f"Amount must be finite on row {row_number}")
        records.append(
            {
                "id": str(uuid.uuid4()),
                "document_id": document_id,
                "date": row.get("date", "").strip(),
                "description": row.get("description", "").strip(),
                "amount": amount,
                "category": row.get("category", "Uncategorised").strip(),
                "created_at": datetime.now(timezone.utc),
            }
        )
    return records


def process_document(job: dict, connection) -> int:
    """Replace one document's records and status in a single transaction."""
    raw_csv = fetch_csv(job)
    records = parse_csv(raw_csv, job["document_id"])
    cursor = connection.cursor()
    try:
        cursor.execute(
            """UPDATE documents
               SET status = %s,
                   processing_attempts = processing_attempts + 1,
                   error_msg = NULL,
                   updated_at = %s
               WHERE id = %s""",
            ("processing", datetime.now(timezone.utc), job["document_id"]),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"Document {job['document_id']} not found")

        cursor.execute("DELETE FROM records WHERE document_id = %s", (job["document_id"],))
        if records:
            cursor.executemany(
                """INSERT INTO records
                   (id, document_id, date, description, amount, category, created_at)
                   VALUES
                   (%(id)s, %(document_id)s, %(date)s, %(description)s,
                    %(amount)s, %(category)s, %(created_at)s)""",
                records,
            )
        cursor.execute(
            "UPDATE documents SET status = %s, updated_at = %s WHERE id = %s",
            ("completed", datetime.now(timezone.utc), job["document_id"]),
        )
        connection.commit()
        return len(records)
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def mark_document_failed(connection, document_id: str, error: Exception) -> None:
    """Persist a failed attempt after rolling back the processing transaction."""
    cursor = connection.cursor()
    try:
        cursor.execute(
            """UPDATE documents
               SET status = %s,
                   processing_attempts = processing_attempts + 1,
                   error_msg = %s,
                   updated_at = %s
               WHERE id = %s""",
            ("failed", str(error)[:1000], datetime.now(timezone.utc), document_id),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def handler(event, context):
    """Process an SQS batch and return failures for item-level retry."""
    del context
    batch_failures = []

    for record in event.get("Records", []):
        message_id = record["messageId"]
        connection = None
        job = None
        try:
            job = parse_job(record["body"])
            connection = get_connection()
            record_count = process_document(job, connection)
            print(
                f"document_processed message_id={message_id} "
                f"document_id={job['document_id']} trace_id={job['trace_id']} "
                f"record_count={record_count}"
            )
        except Exception as error:
            print(f"document_failed message_id={message_id} error={error}")
            if connection is not None and job is not None:
                try:
                    connection.rollback()
                    mark_document_failed(connection, job["document_id"], error)
                except Exception as database_error:
                    print(
                        f"failure_status_update_failed message_id={message_id} "
                        f"document_id={job['document_id']} error={database_error}"
                    )
            batch_failures.append({"itemIdentifier": message_id})
        finally:
            if connection is not None:
                connection.close()

    return {"batchItemFailures": batch_failures}
