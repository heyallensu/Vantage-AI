"""Publish versioned document jobs to SQS."""

import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.contracts.document_job import DocumentJob


class QueuePublishError(RuntimeError):
    """Stable application error for SQS provider failures."""


def send_document_for_processing(
    job: DocumentJob,
    *,
    client=None,
    queue_url: str | None = None,
) -> str:
    """Publish one strict v1 job and return the provider message ID."""
    resolved_queue_url = queue_url or os.getenv("SQS_QUEUE_URL", "")
    if not resolved_queue_url:
        raise RuntimeError("SQS_QUEUE_URL is required outside local development")
    resolved_client = client or boto3.client(
        "sqs",
        region_name=os.getenv("AWS_DEFAULT_REGION", "ap-southeast-2"),
    )
    try:
        response = resolved_client.send_message(
            QueueUrl=resolved_queue_url,
            MessageBody=job.model_dump_json(),
        )
    except (BotoCoreError, ClientError) as exc:
        raise QueuePublishError("Unable to publish document job") from exc
    return response["MessageId"]
