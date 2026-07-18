"""Centralized runtime configuration with fail-fast production validation."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache

DEFAULT_DATABASE_URL = "postgresql://vantage:vantage@db:5432/vantage"
DEFAULT_BEDROCK_MODEL_ID = "au.anthropic.claude-haiku-4-5-20251001-v1:0"


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is incomplete."""


@dataclass(frozen=True)
class Settings:
    """Validated settings shared by API adapters and service boundaries."""

    environment: str
    api_key: str = field(repr=False)
    aws_region: str
    database_url: str = field(repr=False)
    db_secret_arn: str = field(repr=False)
    db_name: str
    document_bucket: str
    sqs_queue_url: str
    bedrock_model_id: str

    @property
    def is_local(self) -> bool:
        return self.environment == "local"

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "Settings":
        environment = values.get("ENV", "local").strip().lower()
        settings = cls(
            environment=environment,
            api_key=values.get(
                "API_KEY",
                "local-development-only" if environment == "local" else "",
            ).strip(),
            aws_region=values.get("AWS_DEFAULT_REGION", "").strip(),
            database_url=values.get(
                "DATABASE_URL",
                DEFAULT_DATABASE_URL if environment == "local" else "",
            ).strip(),
            db_secret_arn=values.get("DB_SECRET_ARN", "").strip(),
            db_name=values.get("DB_NAME", "vantage").strip(),
            document_bucket=values.get("DOCUMENT_BUCKET", "").strip(),
            sqs_queue_url=values.get("SQS_QUEUE_URL", "").strip(),
            bedrock_model_id=values.get(
                "BEDROCK_MODEL_ID",
                DEFAULT_BEDROCK_MODEL_ID,
            ).strip(),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        missing = []
        required = {
            "API_KEY": self.api_key,
            "AWS_DEFAULT_REGION": self.aws_region,
            "DOCUMENT_BUCKET": self.document_bucket,
            "SQS_QUEUE_URL": self.sqs_queue_url,
        }
        if self.is_local:
            required = {"API_KEY": self.api_key, "DATABASE_URL": self.database_url}
        missing.extend(name for name, value in required.items() if not value)
        if missing:
            raise ConfigurationError(
                f"Missing required runtime configuration: {', '.join(sorted(missing))}"
            )
        if not self.is_local and not (self.database_url or self.db_secret_arn):
            raise ConfigurationError(
                "Missing required runtime configuration: DATABASE_URL or DB_SECRET_ARN"
            )


@lru_cache
def get_settings() -> Settings:
    """Load and validate the process environment once."""
    return Settings.from_mapping(os.environ)
