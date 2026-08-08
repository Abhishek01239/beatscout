"""Pytest configuration: isolated temp DB + clean storage per test session."""
from __future__ import annotations

import os
import sys
import tempfile

# Must be set before any `app.*` import so pydantic-settings picks them up.
_TMP = tempfile.mkdtemp(prefix="beatscout_tests_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
os.environ["TESTING"] = "1"
os.environ["SEED_DEMO"] = "0"
os.environ["AUTO_RUN_WORKER"] = "0"
os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")
os.environ["RATE_LIMIT_ENABLED"] = "0"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _init_app():
    from app.database import init_db
    init_db()
    yield


@pytest.fixture()
def db():
    """Function-scoped session."""
    from app.database import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture(scope="session")
def demo_user():
    """A persisted demo user shared across tests (email demo@beatscout.dev)."""
    from app.database import SessionLocal
    from app.models import User
    from app.security import hash_password

    s = SessionLocal()
    try:
        u = (
            s.query(User)
            .filter(User.email == "demo@beatscout.dev")
            .first()
        )
        if u is None:
            u = User(
                email="demo@beatscout.dev",
                password_hash=hash_password("demo-pass-123"),
                name="Demo User",
            )
            s.add(u)
            s.commit()
            s.refresh(u)
        return u
    finally:
        s.close()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_headers(client, demo_user):
    r = client.post(
        "/api/auth/login",
        json={"email": "demo@beatscout.dev", "password": "demo-pass-123"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']['access_token']}"}