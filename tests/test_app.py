
import sqlite3

import pytest

import app as placement_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a Flask test client with a separate temporary database."""
    test_database = tmp_path / "test_placementpro.db"

    monkeypatch.setattr(placement_app, "DATABASE", test_database)
    placement_app.app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SECRET_KEY="test-secret-key",
    )

    placement_app.init_db()

    with placement_app.app.test_client() as test_client:
        yield test_client


def test_login_page_loads(client):
    response = client.get("/login")

    assert response.status_code == 200


def test_registration_page_loads(client):
    response = client.get("/register")

    assert response.status_code == 200


def test_dashboard_redirects_logged_out_user(client):
    response = client.get("/")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
