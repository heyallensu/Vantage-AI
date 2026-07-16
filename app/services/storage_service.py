"""Validated document storage adapters for local development and Amazon S3."""

import csv
import hashlib
import io
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import boto3
from botocore.exceptions import BotoCoreError, ClientError

MAX_UPLOAD_BYTES = 1024 * 1024
REQUIRED_HEADERS = {"date", "description", "amount", "category"}


class UploadValidationError(ValueError):
    """Raised when an upload cannot be accepted as a supported financial CSV."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class StorageError(RuntimeError):
    """Stable application error for storage provider failures."""


@dataclass(frozen=True)
class ValidatedUpload:
    text: str
    checksum_sha256: str


@dataclass(frozen=True)
class StoredDocument:
    object_key: str
    checksum_sha256: str


class DocumentStorage(Protocol):
    bucket_name: str

    def store(self, document_id: str, content: bytes) -> StoredDocument: ...

    def read(self, object_key: str) -> bytes: ...


def build_object_key(document_id: str) -> str:
    return f"documents/{document_id}/source.csv"


def validate_csv_upload(content: bytes) -> ValidatedUpload:
    """Validate upload size, encoding, and required financial CSV headers."""
    if len(content) > MAX_UPLOAD_BYTES:
        raise UploadValidationError("CSV uploads must not exceed 1 MiB", status_code=413)

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UploadValidationError("CSV upload must contain valid UTF-8") from exc

    reader = csv.DictReader(io.StringIO(text))
    headers = {header.strip() for header in (reader.fieldnames or []) if header}
    missing_headers = sorted(REQUIRED_HEADERS - headers)
    if missing_headers:
        raise UploadValidationError(
            f"Missing required CSV headers: {', '.join(missing_headers)}"
        )

    return ValidatedUpload(
        text=text,
        checksum_sha256=hashlib.sha256(content).hexdigest(),
    )


class InMemoryDocumentStorage:
    """Non-persistent adapter used only by the documented local inline mode."""

    bucket_name = "local-memory"

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    def store(self, document_id: str, content: bytes) -> StoredDocument:
        validated = validate_csv_upload(content)
        object_key = build_object_key(document_id)
        self._objects[object_key] = content
        return StoredDocument(object_key, validated.checksum_sha256)

    def read(self, object_key: str) -> bytes:
        try:
            return self._objects[object_key]
        except KeyError as exc:
            raise StorageError("Stored document is not available") from exc


class S3DocumentStorage:
    """Private encrypted S3 storage implementation."""

    def __init__(self, *, bucket: str, client=None) -> None:
        if not bucket:
            raise ValueError("Document bucket is required")
        self.bucket_name = bucket
        self._client = client or boto3.client(
            "s3",
            region_name=os.getenv("AWS_DEFAULT_REGION", "ap-southeast-2"),
        )

    def store(self, document_id: str, content: bytes) -> StoredDocument:
        validated = validate_csv_upload(content)
        object_key = build_object_key(document_id)
        try:
            self._client.put_object(
                Bucket=self.bucket_name,
                Key=object_key,
                Body=content,
                ContentType="text/csv",
                ServerSideEncryption="AES256",
                Metadata={"checksum-sha256": validated.checksum_sha256},
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("Unable to store document") from exc
        return StoredDocument(object_key, validated.checksum_sha256)

    def read(self, object_key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self.bucket_name, Key=object_key)
            return response["Body"].read()
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("Unable to read document") from exc


@lru_cache
def get_document_storage() -> DocumentStorage:
    if os.getenv("ENV", "local") == "local":
        return InMemoryDocumentStorage()
    return S3DocumentStorage(bucket=os.getenv("DOCUMENT_BUCKET", ""))
