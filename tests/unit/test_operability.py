"""Readiness and structured access logging tests."""

import json
import logging

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.logging import JsonFormatter
from app.models.record import get_db


def test_readiness_returns_503_when_database_check_fails(test_app) -> None:
    class FailedSession:
        def execute(self, statement):
            del statement
            raise OperationalError("SELECT 1", {}, RuntimeError("database unavailable"))

    def failed_database():
        yield FailedSession()

    test_app.dependency_overrides[get_db] = failed_database
    with TestClient(test_app) as readiness_client:
        response = readiness_client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database is not ready"}


def test_json_formatter_emits_operational_fields_without_secrets() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="vantage.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request_completed",
        args=(),
        exc_info=None,
    )
    record.route = "/documents/document-123/status"
    record.status = 200
    record.duration_ms = 12.5
    record.request_id = "request-123"
    record.document_id = "document-123"
    record.api_key = "must-never-be-logged"

    payload = json.loads(formatter.format(record))

    assert payload["service"] == "vantage-ai-api"
    assert payload["level"] == "INFO"
    assert payload["document_id"] == "document-123"
    assert payload["duration_ms"] == 12.5
    assert "api_key" not in payload
    assert "must-never-be-logged" not in formatter.format(record)


def test_request_middleware_returns_request_id_and_logs_route(test_app) -> None:
    records = []

    class CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("vantage.access")
    handler = CaptureHandler()
    logger.addHandler(handler)
    try:
        with TestClient(test_app) as request_client:
            response = request_client.get(
                "/health",
                headers={"X-Request-ID": "portfolio-request"},
            )
    finally:
        logger.removeHandler(handler)

    access_record = next(record for record in records if record.getMessage() == "request_completed")
    assert response.headers["X-Request-ID"] == "portfolio-request"
    assert access_record.route == "/health"
    assert access_record.status == 200
