from fastapi.testclient import TestClient


def test_health_returns_versioned_ok_response(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1.0.0"}
