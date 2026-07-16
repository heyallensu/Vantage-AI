from pathlib import Path

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy.orm import Session

from app.models.record import Document
from app.services.storage_service import (
    InMemoryDocumentStorage,
    StorageError,
    get_document_storage,
)

SAMPLE_DATA = Path(__file__).parents[2] / "sample-data.csv"


def upload_sample(client: TestClient) -> str:
    response = client.post(
        "/documents/upload",
        files={"file": ("sample-data.csv", SAMPLE_DATA.read_bytes(), "text/csv")},
    )

    assert response.status_code == 202
    return response.json()["document_id"]


def test_upload_processes_sample_and_exposes_records(client: TestClient) -> None:
    document_id = upload_sample(client)

    status_response = client.get(f"/documents/{document_id}/status")
    records_response = client.get("/records", params={"document_id": document_id})

    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"
    assert records_response.status_code == 200
    assert len(records_response.json()) == 10


def test_upload_rejects_non_csv_file(client: TestClient) -> None:
    response = client.post(
        "/documents/upload",
        files={"file": ("report.txt", b"not csv", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only CSV files are supported"


def test_missing_document_and_record_return_404(client: TestClient) -> None:
    document_response = client.get("/documents/missing/status")
    record_response = client.get("/records/missing")

    assert document_response.status_code == 404
    assert record_response.status_code == 404


def test_record_filters_and_single_record_lookup(client: TestClient) -> None:
    document_id = upload_sample(client)

    technology_response = client.get(
        "/records",
        params={"document_id": document_id, "category": "Technology"},
    )
    technology_records = technology_response.json()
    record_response = client.get(f"/records/{technology_records[0]['id']}")

    assert technology_response.status_code == 200
    assert len(technology_records) == 3
    assert record_response.status_code == 200
    assert record_response.json()["category"] == "Technology"


def test_insight_endpoints_use_processed_records(
    client: TestClient,
    monkeypatch: MonkeyPatch,
) -> None:
    document_id = upload_sample(client)
    monkeypatch.setattr(
        "app.routers.insights.analyze_records",
        lambda records: {"record_count": len(records), "summary": "ok", "anomalies": []},
    )
    monkeypatch.setattr("app.routers.insights.generate_summary", lambda records: "summary")
    monkeypatch.setattr(
        "app.routers.insights.find_anomalies",
        lambda records: ["Unexpected Transfer"],
    )

    analyze_response = client.post("/insights/analyze", params={"document_id": document_id})
    summary_response = client.get("/insights/summary", params={"document_id": document_id})
    anomaly_response = client.get("/insights/anomalies", params={"document_id": document_id})

    assert analyze_response.status_code == 200
    assert analyze_response.json()["record_count"] == 10
    assert summary_response.json() == {"summary": "summary"}
    assert anomaly_response.json() == {"anomalies": ["Unexpected Transfer"]}


def test_insights_return_404_when_no_records_exist(client: TestClient) -> None:
    response = client.get("/insights/summary")

    assert response.status_code == 404


class FailingStorage:
    bucket_name = "test-failure"

    def store(self, document_id: str, content: bytes):
        del document_id, content
        raise StorageError("simulated storage failure")

    def read(self, object_key: str) -> bytes:
        del object_key
        raise StorageError("simulated storage failure")


def test_storage_failure_marks_document_failed(
    client: TestClient,
    test_app,
    db_session: Session,
) -> None:
    test_app.dependency_overrides[get_document_storage] = FailingStorage

    response = client.post(
        "/documents/upload",
        files={"file": ("sample-data.csv", SAMPLE_DATA.read_bytes(), "text/csv")},
    )

    document = db_session.query(Document).one()
    assert response.status_code == 502
    assert document.status == "failed"
    assert document.error_msg == "simulated storage failure"


def test_queue_failure_marks_document_failed(
    client: TestClient,
    test_app,
    db_session: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    test_app.dependency_overrides[get_document_storage] = InMemoryDocumentStorage
    monkeypatch.setenv("ENV", "portfolio")
    monkeypatch.setattr(
        "app.routers.documents.send_document_for_processing",
        lambda job: (_ for _ in ()).throw(RuntimeError("simulated queue failure")),
    )

    response = client.post(
        "/documents/upload",
        files={"file": ("sample-data.csv", SAMPLE_DATA.read_bytes(), "text/csv")},
    )

    document = db_session.query(Document).one()
    assert response.status_code == 502
    assert document.status == "failed"
    assert document.error_msg == "simulated queue failure"
