"""Database credential resolution tests for managed runtime secrets."""

import json
from unittest.mock import Mock

import pytest

from app.core.config import ConfigurationError, Settings
from app.core.database import build_database_url, resolve_database_url


def test_settings_accept_managed_database_secret_in_production() -> None:
    settings = Settings.from_mapping(
        {
            "ENV": "portfolio",
            "API_KEY": "runtime-api-key",
            "AWS_DEFAULT_REGION": "ap-southeast-2",
            "DB_SECRET_ARN": "arn:aws:secretsmanager:ap-southeast-2:123456789012:secret:db",
            "DB_NAME": "vantage",
            "DOCUMENT_BUCKET": "documents",
            "SQS_QUEUE_URL": "https://sqs.example/queue",
        }
    )

    assert settings.database_url == ""
    assert settings.db_secret_arn.endswith(":secret:db")


def test_settings_require_database_url_or_secret_in_production() -> None:
    with pytest.raises(ConfigurationError, match="DATABASE_URL or DB_SECRET_ARN"):
        Settings.from_mapping(
            {
                "ENV": "portfolio",
                "API_KEY": "runtime-api-key",
                "AWS_DEFAULT_REGION": "ap-southeast-2",
                "DOCUMENT_BUCKET": "documents",
                "SQS_QUEUE_URL": "https://sqs.example/queue",
            }
        )


def test_build_database_url_escapes_managed_secret_credentials() -> None:
    url = build_database_url(
        {
            "username": "vantage@example.com",
            "password": "p@ss/word?",
            "host": "db.internal",
            "port": 5432,
            "dbname": "vantage",
        }
    )

    assert url == (
        "postgresql://vantage%40example.com:p%40ss%2Fword%3F@"
        "db.internal:5432/vantage"
    )


def test_resolve_database_url_reads_secret_string() -> None:
    client = Mock()
    client.get_secret_value.return_value = {
        "SecretString": json.dumps(
            {
                "username": "vantage",
                "password": "managed-password",
                "host": "db.internal",
                "port": 5432,
            }
        )
    }

    resolved = resolve_database_url(
        database_url="",
        secret_arn="arn:aws:secretsmanager:ap-southeast-2:123456789012:secret:db",
        database_name="vantage",
        client=client,
    )

    assert resolved == "postgresql://vantage:managed-password@db.internal:5432/vantage"
    client.get_secret_value.assert_called_once()


def test_resolve_database_url_preserves_local_explicit_url() -> None:
    client = Mock()

    resolved = resolve_database_url(
        database_url="postgresql://local:local@db:5432/vantage",
        secret_arn="",
        database_name="vantage",
        client=client,
    )

    assert resolved == "postgresql://local:local@db:5432/vantage"
    client.get_secret_value.assert_not_called()
