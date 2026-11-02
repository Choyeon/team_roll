"""Shared fixtures: every test run gets its own database, static dir and admin account."""

from __future__ import annotations

import itertools
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="team-roll-test-"))
_STATIC = _TMP / "static"
_STATIC.mkdir()
(_STATIC / "index.html").write_text(
    "<!doctype html><html><head><!--seo-slot--></head>"
    '<body><div id="app"></div><!--shell-script--></body></html>',
    encoding="utf-8",
)

os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{(_TMP / 'test.db').as_posix()}",
        "STATIC_DIR": str(_STATIC),
        "SPA_SHELL": str(_STATIC / "index.html"),
        "ENVIRONMENT": "test",
        "DEBUG": "false",
        "SECRET_KEY": "test-secret-key",
        "BOOTSTRAP_ADMIN_USERNAME": "boss",
        "BOOTSTRAP_ADMIN_PASSWORD": "sup3r-secret-password",
        # Keep the sliding-window limiters out of the golden-path tests.
        "LOGIN_RATE_LIMIT": "200",
        "ROLL_RATE_LIMIT": "200",
        "DATABASE_AUTO_MIGRATE": "true",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import get_engine, get_sessionmaker  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture(scope="session")
def app():
    return create_app(get_settings())


@pytest.fixture(scope="session", autouse=True)
def _prepared_database(app):
    """Migrate and seed once per run, so cookie-less tests see the same schema the app does."""
    from app.db import migrate
    from app.services import admins as admin_service

    settings = app.state.settings
    migrate.ensure_schema(settings, get_engine(settings))
    admin_service.bootstrap_admin(get_sessionmaker()(), settings)
    return app


@pytest.fixture(scope="session")
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def anon_client(app):
    """A cookie-free client, for the not-logged-in and cross-account cases."""
    yield TestClient(app)


@pytest.fixture(scope="session")
def admin_client(app) -> TestClient:
    """The run's superuser. Only this account stays logged in, because opening a
    session revokes the same admin's previous ones."""
    test_client = TestClient(app)
    test_client.__enter__()
    response = test_client.post("/api/v1/auth/login", json={"username": "boss", "password": "sup3r-secret-password"})
    assert response.status_code == 200, response.text
    test_client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    yield test_client
    test_client.__exit__(None, None, None)


@pytest.fixture
def login_as(admin_client, app):
    """Create a throwaway admin and return a client authenticated as it."""
    clients: list[TestClient] = []
    counter = itertools.count(1)

    def _login(role: str = "super", password: str = "another-secret-password") -> TestClient:
        username = f"user{next(counter)}-{role}"
        created = admin_client.post(
            "/api/v1/admin/admins",
            json={"username": username, "password": password, "role": role, "display_name": username},
        )
        assert created.status_code == 201, created.text
        client = TestClient(app)
        client.__enter__()
        login = client.post("/api/v1/auth/login", json={"username": username, "password": password})
        assert login.status_code == 200, login.text
        client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        client.admin_id = created.json()["id"]
        clients.append(client)
        return client

    yield _login

    for client in clients:
        client.__exit__(None, None, None)
        admin_client.delete(f"/api/v1/admin/admins/{client.admin_id}")


@pytest.fixture(scope="session")
def activity_id(admin_client) -> str:
    response = admin_client.post(
        "/api/v1/admin/activities",
        json={"name": "测试活动", "description": "用于自动化测试", "roll_min": 1, "roll_max": 10, "max_participations": 1},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]
