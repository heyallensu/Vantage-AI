"""Publish versioned document jobs to SQS."""

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.contracts.document_job import DocumentJob
from app.core.config import get_settings


class QueuePublishError(RuntimeError):
    """Stable application error for SQS provider failures."""


def send_document_for_processing(
    job: DocumentJob,
    *,
    client=None,
    queue_url: str | None = None,
) -> str:
    """Publish one strict v1 job and return the provider message ID."""
    settings = get_settings()
    resolved_queue_url = queue_url or settings.sqs_queue_url
    if not resolved_queue_url:
        raise RuntimeError("SQS_QUEUE_URL is required outside local development")
    resolved_client = client or boto3.client(
        "sqs",
        region_name=settings.aws_region,
    )
    try:
        response = resolved_client.send_message(
            QueueUrl=resolved_queue_url,
            MessageBody=job.model_dump_json(),
        )
    except (BotoCoreError, ClientError) as exc:
        raise QueuePublishError("Unable to publish document job") from exc
    return response["MessageId"]
