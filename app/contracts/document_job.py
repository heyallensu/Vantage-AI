"""Strict queue contract for asynchronous document-processing jobs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DocumentJob(BaseModel):
    """Version 1 payload published by the API and consumed by Lambda."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1]
    document_id: str = Field(min_length=1)
    bucket: str = Field(min_length=1)
    object_key: str = Field(min_length=1)
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    trace_id: str = Field(min_length=1)
