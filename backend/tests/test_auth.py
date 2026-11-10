"""Register / login / refresh / logout."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.models.enums import UserRole

REGISTRATION = {
    "email": "Ada@Example.com",
    "password": "correct-horse-battery",
    "profile": {
        "full_name": "Ada Lovelace",
        "country": "GB",
        "preferred_language": "en",
    },
}


def test_register_returns_tokens_and_creates_a_patient(client: TestClient) -> None:
    response = client.post("/api/v1/auth/register", json=REGISTRATION)
    assert response.status_code == 201, response.text
    tokens = response.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"] and tokens["refresh_token"]

    me = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.status_code == 200
    body = me.json()
    assert body["role"] == UserRole.PATIENT.value
    assert body["email"] == "ada@example.com"  # normalized
    assert body["profile"]["full_name"] == "Ada Lovelace"


def test_register_cannot_choose_a_privileged_role(client: TestClient) -> None:
    """A stray ``role`` in the body must not escalate; extra keys are ignored."""
    response = client.post("/api/v1/auth/register", json={**REGISTRATION, "role": "admin"})
    assert response.status_code == 201

    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
    )
    assert me.json()["role"] == UserRole.PATIENT.value


def test_register_rejects_duplicate_email_case_insensitively(client: TestClient) -> None:
    assert client.post("/api/v1/auth/register", json=REGISTRATION).status_code == 201
    duplicate = client.post(
        "/api/v1/auth/register", json={**REGISTRATION, "email": "ADA@example.com"}
    )
    assert duplicate.status_code == 409


def test_login_with_wrong_password_is_401(client: TestClient) -> None:
    client.post("/api/v1/auth/register", json=REGISTRATION)
    response = client.post(
        "/api/v1/auth/login", json={"email": REGISTRATION["email"], "password": "wrong"}
    )
    assert response.status_code == 401


def test_login_with_unknown_email_is_401(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever"}
    )
    assert response.status_code == 401


def test_me_requires_a_token(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_rejects_a_refresh_token_used_as_an_access_token(client: TestClient) -> None:
    tokens = client.post("/api/v1/auth/register", json=REGISTRATION).json()
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
    )
    assert response.status_code == 401


def test_me_rejects_a_garbage_token(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert response.status_code == 401


def test_refresh_rotates_and_invalidates_the_old_token(client: TestClient) -> None:
    tokens = client.post("/api/v1/auth/register", json=REGISTRATION).json()

    rotated = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert rotated.status_code == 200
    new_tokens = rotated.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    # The consumed token is single-use.
    replayed = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replayed.status_code == 401

    # The new one works.
    assert (
        client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {new_tokens['access_token']}"},
        ).status_code
        == 200
    )


def test_logout_revokes_the_refresh_token(client: TestClient) -> None:
    tokens = client.post("/api/v1/auth/register", json=REGISTRATION).json()

    logout = client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert logout.status_code == 204

    response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 401


def test_logout_is_idempotent(client: TestClient) -> None:
    tokens = client.post("/api/v1/auth/register", json=REGISTRATION).json()
    payload = {"refresh_token": tokens["refresh_token"]}
    assert client.post("/api/v1/auth/logout", json=payload).status_code == 204
    assert client.post("/api/v1/auth/logout", json=payload).status_code == 204


def test_refresh_rejects_an_access_token(client: TestClient) -> None:
    tokens = client.post("/api/v1/auth/register", json=REGISTRATION).json()
    response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}
    )
    assert response.status_code == 401


def test_deactivated_user_cannot_use_a_live_access_token(client: TestClient, db, patient) -> None:
    from app.models.user import User

    headers = client.post(
        "/api/v1/auth/login",
        json={"email": patient.email, "password": "correct-horse-battery"},
    ).json()
    auth = {"Authorization": f"Bearer {headers['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=auth).status_code == 200

    db.get(User, patient.id).is_active = False
    db.commit()

    assert client.get("/api/v1/auth/me", headers=auth).status_code == 403


def test_admin_can_provision_a_coordinator(client: TestClient, admin, auth_headers) -> None:
    response = client.post(
        "/api/v1/auth/users",
        headers=auth_headers(admin),
        json={
            "email": f"coord-{uuid.uuid4().hex[:6]}@example.com",
            "password": "correct-horse-battery",
            "role": "coordinator",
        },
    )
    assert response.status_code == 201
    assert response.json()["role"] == "coordinator"


def test_non_admin_cannot_provision_users(client: TestClient, patient, auth_headers) -> None:
    response = client.post(
        "/api/v1/auth/users",
        headers=auth_headers(patient),
        json={
            "email": "sneaky@example.com",
            "password": "correct-horse-battery",
            "role": "admin",
        },
    )
    assert response.status_code == 403
