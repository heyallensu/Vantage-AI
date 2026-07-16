"""Tests for CSV validation and document storage adapters."""

import hashlib
from unittest.mock import Mock

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from app.services.storage_service import (
    MAX_UPLOAD_BYTES,
    S3DocumentStorage,
    StorageError,
    UploadValidationError,
    validate_csv_upload,
)

VALID_CSV = b"date,description,amount,category\n2024-01-01,Service,42,Operations\n"


def test_validate_csv_upload_returns_text_and_checksum() -> None:
    validated = validate_csv_upload(VALID_CSV)

    assert validated.text.startswith("date,description")
    assert validated.checksum_sha256 == hashlib.sha256(VALID_CSV).hexdigest()


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"\xff\xfe", "valid UTF-8"),
        (b"date,amount\n2024-01-01,42\n", "Missing required CSV headers"),
        (b"x" * (MAX_UPLOAD_BYTES + 1), "1 MiB"),
    ],
    ids=["invalid-utf8", "missing-headers", "too-large"],
)
def test_validate_csv_upload_rejects_invalid_content(content: bytes, message: str) -> None:
    with pytest.raises(UploadValidationError, match=message):
        validate_csv_upload(content)


def test_s3_storage_uses_deterministic_private_encrypted_object() -> None:
    with mock_aws():
        client = boto3.client("s3", region_name="ap-southeast-2")
        client.create_bucket(
            Bucket="vantage-documents",
            CreateBucketConfiguration={"LocationConstraint": "ap-southeast-2"},
        )
        storage = S3DocumentStorage(bucket="vantage-documents", client=client)

        stored = storage.store("document-123", VALID_CSV)
        response = client.get_object(Bucket="vantage-documents", Key=stored.object_key)

        assert stored.object_key == "documents/document-123/source.csv"
        assert response["Body"].read() == VALID_CSV
        assert response["ServerSideEncryption"] == "AES256"
        assert response["Metadata"]["checksum-sha256"] == stored.checksum_sha256


def test_s3_storage_converts_client_failures_to_stable_error() -> None:
    client = Mock()
    client.put_object.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "denied"}},
        "PutObject",
    )
    storage = S3DocumentStorage(bucket="vantage-documents", client=client)

    with pytest.raises(StorageError, match="Unable to store document"):
        storage.store("document-123", VALID_CSV)
