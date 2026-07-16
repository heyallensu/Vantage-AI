"""End-to-end tests for S3-to-Lambda document processing."""

import hashlib
import importlib
import json
from pathlib import Path

import boto3
import sqlalchemy as sa
from moto import mock_aws
from pytest import MonkeyPatch
from sqlalchemy import create_engine

from scripts.database.migrate import upgrade_database

SAMPLE_DATA = Path(__file__).parents[2] / "sample-data.csv"


def test_replaying_document_job_replaces_records_idempotently(
    migration_database_url: str,
    monkeypatch: MonkeyPatch,
) -> None:
    upgrade_database(database_url=migration_database_url)
    content = SAMPLE_DATA.read_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    document_id = "document-replay-test"
    object_key = f"documents/{document_id}/source.csv"

    with mock_aws():
        s3_client = boto3.client("s3", region_name="ap-southeast-2")
        s3_client.create_bucket(
            Bucket="vantage-documents",
            CreateBucketConfiguration={"LocationConstraint": "ap-southeast-2"},
        )
        s3_client.put_object(Bucket="vantage-documents", Key=object_key, Body=content)

        engine = create_engine(migration_database_url)
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO documents "
                    "(id, filename, status, object_key, checksum_sha256, trace_id, "
                    "processing_attempts, created_at, updated_at) "
                    "VALUES (:id, 'sample-data.csv', 'pending', :key, :checksum, "
                    "'trace-replay', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"id": document_id, "key": object_key, "checksum": checksum},
            )

        monkeypatch.setenv("DATABASE_URL", migration_database_url)
        handler_module = importlib.import_module("lambda.processor.handler")
        monkeypatch.setattr(handler_module, "s3", s3_client)
        event = {
            "Records": [
                {
                    "messageId": "message-123",
                    "body": json.dumps(
                        {
                            "schema_version": 1,
                            "document_id": document_id,
                            "bucket": "vantage-documents",
                            "object_key": object_key,
                            "checksum_sha256": checksum,
                            "trace_id": "trace-replay",
                        }
                    ),
                }
            ]
        }

        assert handler_module.handler(event, None) == {"batchItemFailures": []}
        assert handler_module.handler(event, None) == {"batchItemFailures": []}

        with engine.connect() as connection:
            assert (
                connection.execute(
                    sa.text("SELECT count(*) FROM records WHERE document_id = :id"),
                    {"id": document_id},
                ).scalar_one()
                == 10
            )
            status, attempts = connection.execute(
                sa.text(
                    "SELECT status, processing_attempts FROM documents WHERE id = :id"
                ),
                {"id": document_id},
            ).one()
            assert status == "completed"
            assert attempts == 2
        engine.dispose()
