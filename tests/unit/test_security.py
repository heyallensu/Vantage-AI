"""Authentication and production configuration boundary tests."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import ConfigurationError, Settings
from app.main import create_app


def test_protected_routes_require_valid_api_key(test_app) -> None:
    with TestClient(test_app) as unauthenticated_client:
        missing = unauthenticated_client.get("/records")
        invalid = unauthenticated_client.get(
            "/records",
            headers={"X-API-Key": "wrong-key"},
        )

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert missing.json()["detail"] == "Invalid or missing API key"


def test_health_and_readiness_do_not_require_api_key(test_app) -> None:
    with TestClient(test_app) as unauthenticated_client:
        health = unauthenticated_client.get("/health")
        readiness = unauthenticated_client.get("/ready")

    assert health.status_code == 200
    assert readiness.status_code == 200


def test_non_local_settings_fail_fast_when_required_values_are_missing() -> None:
    with pytest.raises(ConfigurationError, match="API_KEY, DOCUMENT_BUCKET, SQS_QUEUE_URL"):
        Settings.from_mapping(
            {
                "ENV": "production",
                "AWS_DEFAULT_REGION": "ap-southeast-2",
                "DATABASE_URL": "postgresql://service:secret@database/vantage",
            }
        )


def test_non_local_settings_accept_complete_runtime_configuration() -> None:
    settings = Settings.from_mapping(
        {
            "ENV": "production",
            "API_KEY": "portfolio-secret",
            "AWS_DEFAULT_REGION": "ap-southeast-2",
            "DATABASE_URL": "postgresql://service:secret@database/vantage",
            "DOCUMENT_BUCKET": "portfolio-documents",
            "SQS_QUEUE_URL": "https://sqs.example.test/jobs",
        }
    )

    application = create_app(settings)

    assert application.state.settings is settings
    assert "portfolio-secret" not in repr(settings)
    assert "service:secret" not in repr(settings)


def test_non_local_settings_do_not_fall_back_to_local_database_credentials() -> None:
    with pytest.raises(ConfigurationError, match="DATABASE_URL"):
        Settings.from_mapping(
            {
                "ENV": "production",
                "API_KEY": "portfolio-secret",
                "AWS_DEFAULT_REGION": "ap-southeast-2",
                "DOCUMENT_BUCKET": "portfolio-documents",
                "SQS_QUEUE_URL": "https://sqs.example.test/jobs",
            }
        )
