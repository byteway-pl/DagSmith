from __future__ import annotations

from fastapi.testclient import TestClient

from dagsmith import __version__
from dagsmith.api.app import create_app


def test_health_returns_ok_and_version() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_openapi_is_served() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "DagSmith"
