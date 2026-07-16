"""
Sends messages to SQS.
The API calls this after saving a document — Lambda will pick it up.
"""

import json
import os

import boto3

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
    if not SQS_QUEUE_URL:
        raise RuntimeError("SQS_QUEUE_URL is required outside local development")
    response = sqs.send_message(
        QueueUrl=SQS_QUEUE_URL,
        MessageBody=json.dumps(message),
    )
    return response["MessageId"]
