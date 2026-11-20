"""Cross-account authorization regression tests."""
import os


def test_user_cannot_read_or_mutate_another_users_project(client, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("BUILDSCOPE_AUTH_SECRET", "authorization-test-secret")

    a = client.post("/api/auth/register", json={"email": "a@example.com", "password": "password-a"})
    b = client.post("/api/auth/register", json={"email": "b@example.com", "password": "password-b"})
    assert a.status_code == 200 and b.status_code == 200

    token_a = a.json()["access_token"]
    token_b = b.json()["access_token"]
    project = client.post(
        "/api/projects",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Private A", "description": "A private investigation description"},
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    headers_b = {"Authorization": f"Bearer {token_b}"}
    assert client.get(f"/api/projects/{project_id}", headers=headers_b).status_code == 404
    assert client.post(f"/api/projects/{project_id}/research", headers=headers_b).status_code == 404
    assert client.get(f"/api/projects/{project_id}/requirements", headers=headers_b).status_code == 404

    # The collection endpoint must not leak the private project either.
    listed = client.get("/api/projects", headers=headers_b)
    assert listed.status_code == 200
    assert all(row["id"] != project_id for row in listed.json())


def test_protected_routes_reject_missing_and_malformed_tokens(client, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("BUILDSCOPE_AUTH_SECRET", "authorization-test-secret")
    assert client.get("/api/projects").status_code == 401
    assert client.get("/api/projects", headers={"Authorization": "Bearer malformed"}).status_code == 401
