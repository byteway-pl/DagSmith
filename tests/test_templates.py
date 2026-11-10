"""Template creation uses draft permissions and rejects occupied paths."""

import ast

import pytest


@pytest.mark.parametrize("template_id", ["blank", "bash", "parallel", "taskflow"])
def test_create_template(api_client, template_id):
    response = api_client.post(
        "/api/v1/drafts",
        json={
            "bundle": "test",
            "rel_path": f"template_{template_id}.py",
            "template_id": template_id,
        },
    )
    assert response.status_code == 201, response.text
    draft = response.json()
    ast.parse(draft["source"])
    assert draft["head_version_no"] == 1
    assert draft["live_file_hash"] is None
    assert f"def template_{template_id}():" in draft["source"]


def test_template_rejects_existing_draft(api_client):
    body = {"bundle": "test", "rel_path": "occupied.py", "template_id": "bash"}
    assert api_client.post("/api/v1/drafts", json=body).status_code == 201
    assert api_client.post("/api/v1/drafts", json=body).status_code == 409


def test_unknown_template(api_client):
    response = api_client.post(
        "/api/v1/drafts",
        json={
            "bundle": "test",
            "rel_path": "unknown.py",
            "template_id": "unknown",
        },
    )
    assert response.status_code == 400


def test_custom_template_lifecycle(api_client):
    body = {
        "name": "My pipeline",
        "source": (
            'from airflow.sdk import dag\n'
            '@dag(dag_id="{{dag_id}}", tags={{tags}}, schedule=None)\n'
            'def {{dag_id}}():\n    data = {"key": 1}\n\n{{dag_id}}()\n'
        ),
    }
    created = api_client.post("/api/v1/templates", json=body)
    assert created.status_code == 201, created.text
    template_id = created.json()["id"]
    assert any(t["id"] == template_id for t in api_client.get("/api/v1/templates").json())
    response = api_client.post(
        "/api/v1/drafts",
        json={
            "bundle": "test",
            "rel_path": "custom_pipeline.py",
            "template_id": f"custom:{template_id}",
        },
    )
    assert response.status_code == 201, response.text
    source = response.json()["source"]
    ast.parse(source)
    assert 'dag_id="custom_pipeline"' in source
    assert '{"key": 1}' in source
    assert "{{tags}}" not in source
    body["name"] = "Renamed"
    assert api_client.put(f"/api/v1/templates/{template_id}", json=body).status_code == 200
    assert api_client.delete(f"/api/v1/templates/{template_id}").status_code == 204
    assert api_client.put(f"/api/v1/templates/{template_id}", json=body).status_code == 404


def test_invalid_custom_template(api_client):
    response = api_client.post("/api/v1/templates", json={"name": "Invalid", "source": "pass"})
    assert response.status_code == 400


def test_custom_templates_are_private(api_client):
    from dagsmith.api.security import ApiUser, require_edit

    body = {"name": "Private", "source": 'dag_id = "{{dag_id}}"\n'}
    response = api_client.post("/api/v1/templates", json=body)
    template_id = response.json()["id"]
    api_client.app.dependency_overrides[require_edit] = lambda: ApiUser("other", object())
    assert api_client.get("/api/v1/templates").json() == []
    assert api_client.put(f"/api/v1/templates/{template_id}", json=body).status_code == 404
    assert api_client.delete(f"/api/v1/templates/{template_id}").status_code == 404
    response = api_client.post(
        "/api/v1/drafts",
        json={
            "bundle": "test",
            "rel_path": "private_copy.py",
            "template_id": f"custom:{template_id}",
        },
    )
    assert response.status_code == 404
