"""Auth endpoint tests: register, login, me, wrong password, bad token."""

from __future__ import annotations


def test_register_login_flow(client):
    r = client.post(
        "/api/auth/register",
        json={"email": "new@user.dev", "password": "Secret-123", "name": "New"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["token"]["access_token"]
    assert body["token"]["expires_in"] > 0
    assert body["user"]["email"] == "new@user.dev"

    # duplicate registration rejected
    r2 = client.post(
        "/api/auth/register",
        json={"email": "new@user.dev", "password": "Secret-123", "name": "New"},
    )
    assert r2.status_code == 409

    r3 = client.post(
        "/api/auth/login", json={"email": "new@user.dev", "password": "Secret-123"}
    )
    assert r3.status_code == 200
    assert r3.json()["token"]["access_token"]


def test_login_rejects_bad_password(client, demo_user):
    r = client.post(
        "/api/auth/login", json={"email": "demo@beatscout.dev", "password": "nope"}
    )
    assert r.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer bogus"}).status_code == 401


def test_me_with_token(client, auth_headers, demo_user):
    r = client.get("/api/auth/me", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["email"] == "demo@beatscout.dev"


def test_register_validates_email(client):
    r = client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": "SecretPass123", "name": "X"},
    )
    assert r.status_code == 422