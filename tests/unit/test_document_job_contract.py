"""Tests for the versioned document-processing queue contract."""

import json
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError
from pydantic import ValidationError

from app.contracts.document_job import DocumentJob
from app.services.sqs_service import (
    QueuePublishError,
    send_document_for_processing,
)

VALID_JOB = {
    "schema_version": 1,
    "document_id": "document-123",
    "bucket": "vantage-documents",
    "object_key": "documents/document-123/source.csv",
    "checksum_sha256": "a" * 64,
    "trace_id": "trace-123",
}


def test_document_job_serializes_exact_v1_schema() -> None:
    job = DocumentJob.model_validate(VALID_JOB)

    assert json.loads(job.model_dump_json()) == VALID_JOB
    assert set(job.model_dump()) == {
        "schema_version",
        "document_id",
        "bucket",
        "object_key",
        "checksum_sha256",
        "trace_id",
    }


@pytest.mark.parametrize(
    "invalid_job",
    [
        {**VALID_JOB, "schema_version": 2},
        {**VALID_JOB, "unexpected": "field"},
        {key: value for key, value in VALID_JOB.items() if key != "schema_version"},
        {key: value for key, value in VALID_JOB.items() if key != "trace_id"},
    ],
)
def test_document_job_rejects_unsupported_extra_or_missing_fields(invalid_job: dict) -> None:
    with pytest.raises(ValidationError):
        DocumentJob.model_validate(invalid_job)


def test_sqs_publisher_sends_only_the_versioned_contract() -> None:
    client = Mock()
    client.send_message.return_value = {"MessageId": "message-123"}
    job = DocumentJob.model_validate(VALID_JOB)

    message_id = send_document_for_processing(
        job,
        client=client,
        queue_url="https://sqs.example.test/queue",
    )

    assert message_id == "message-123"
    assert json.loads(client.send_message.call_args.kwargs["MessageBody"]) == VALID_JOB


def test_sqs_publisher_converts_provider_failure_to_stable_error() -> None:
    client = Mock()
    client.send_message.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "denied"}},
        "SendMessage",
    )

    with pytest.raises(QueuePublishError, match="Unable to publish document job"):
        send_document_for_processing(
            DocumentJob.model_validate(VALID_JOB),
            client=client,
            queue_url="https://sqs.example.test/queue",
        )


def test_sqs_publisher_uses_the_callers_region(monkeypatch) -> None:
    client = Mock()
    client.send_message.return_value = {"MessageId": "message-123"}
    boto3_client = Mock(return_value=client)
    monkeypatch.setattr("app.services.sqs_service.boto3.client", boto3_client)
    monkeypatch.setattr(
        "app.services.sqs_service.get_settings",
        lambda: pytest.fail("explicit queue configuration must not reload process settings"),
    )

    send_document_for_processing(
        DocumentJob.model_validate(VALID_JOB),
        queue_url="https://sqs.example.test/queue",
        region="us-east-1",
    )

    boto3_client.assert_called_once_with("sqs", region_name="us-east-1")
