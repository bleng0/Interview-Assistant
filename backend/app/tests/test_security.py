"""
Security regression tests: authentication and per-user data isolation.

These pin down the fixes made before publishing the repo:
- user data routes require a login and only return the caller's own data
- a user_id parameter for another user is rejected (403)
- question-pool writes are admin-only
- debug/diagnostic endpoints are removed or locked down

Run with: pytest backend/app/tests/test_security.py -v
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

USER_A = {"id": "user-a", "email": "a@example.com", "full_name": "A", "email_verified": True}
USER_B_ID = "user-b"


@pytest.fixture
def app():
    from app.main import app
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def anon_client(app):
    return TestClient(app)


@pytest.fixture
def client_a(app):
    """Requests are made as USER_A."""
    from app.services.auth_service import get_current_user

    async def as_user_a():
        return USER_A

    app.dependency_overrides[get_current_user] = as_user_a
    return TestClient(app)


# ===========================================
# Login is required
# ===========================================

@pytest.mark.parametrize("method,url", [
    ("get", "/api/v1/history/attempts"),
    ("get", "/api/v1/history/attempts/1"),
    ("get", "/api/v1/history/skills/progress"),
    ("get", "/api/v1/history/improvement"),
    ("get", "/api/v1/history/dashboard"),
    ("get", "/api/v1/reports/list"),
    ("get", "/api/v1/reports/summary/quick"),
    ("post", "/api/v1/reports/generate"),
    ("get", "/api/v1/sessions"),
    ("get", "/api/v1/sessions/some-session"),
    ("get", "/api/v1/sessions/some-session/summary"),
    ("post", "/api/v1/sessions/some-session/complete"),
    ("get", "/api/v1/llm/keys/health"),
])
def test_user_routes_require_login(anon_client, method, url):
    response = getattr(anon_client, method)(url)
    assert response.status_code == 401, response.text


def test_submit_answer_requires_login(anon_client):
    response = anon_client.post("/api/v1/submit_answer", json={
        "question_id": 1, "transcript": "hello world answer",
        "user_id": USER_B_ID, "session_id": "s1"
    })
    assert response.status_code == 401


def test_create_session_requires_login(anon_client):
    response = anon_client.post("/api/v1/sessions/create", json={"user_id": USER_B_ID})
    assert response.status_code == 401


# ===========================================
# Users can't read or write other users' data
# ===========================================

@pytest.mark.parametrize("url", [
    f"/api/v1/history/attempts?user_id={USER_B_ID}",
    f"/api/v1/history/dashboard?user_id={USER_B_ID}",
    f"/api/v1/reports/list?user_id={USER_B_ID}",
    f"/api/v1/sessions?user_id={USER_B_ID}",
])
def test_other_users_data_is_forbidden(client_a, url):
    response = client_a.get(url)
    assert response.status_code == 403, response.text


@patch("app.api.history.count_user_attempts", new_callable=AsyncMock, return_value=0)
@patch("app.api.history.get_user_attempts", new_callable=AsyncMock, return_value=[])
def test_own_data_uses_token_identity(mock_attempts, mock_count, client_a):
    """Without a user_id parameter, the logged-in user's data is returned."""
    response = client_a.get("/api/v1/history/attempts")
    assert response.status_code == 200
    assert mock_attempts.await_args.args[0] == USER_A["id"]


@patch("app.api.history.get_attempt_by_id", new_callable=AsyncMock,
       return_value={"id": 7, "user_id": USER_B_ID, "transcript": "secret"})
def test_single_attempt_of_other_user_is_hidden(mock_get, client_a):
    response = client_a.get("/api/v1/history/attempts/7")
    assert response.status_code == 404
    assert "secret" not in response.text


@patch("app.services.supabase_db.get_session_by_id", new_callable=AsyncMock,
       return_value={"id": "s1", "user_id": USER_B_ID})
def test_cannot_submit_answer_into_other_users_session(mock_session, client_a):
    response = client_a.post("/api/v1/submit_answer", json={
        "question_id": 1, "transcript": "hello world answer",
        "user_id": USER_A["id"], "session_id": "s1"
    })
    assert response.status_code == 404


def test_cannot_submit_answer_as_other_user(client_a):
    response = client_a.post("/api/v1/submit_answer", json={
        "question_id": 1, "transcript": "hello world answer",
        "user_id": USER_B_ID, "session_id": "s1"
    })
    assert response.status_code == 403


# ===========================================
# Admin-only question pool writes
# ===========================================

@pytest.mark.parametrize("url", [
    "/api/v1/admin/questions/",
    "/api/v1/admin/questions/bulk",
    "/api/v1/questions/add",
])
def test_question_pool_writes_need_admin(client_a, url):
    with patch("app.config.settings.admin_emails", ""):
        response = client_a.post(url, json={})
    assert response.status_code == 403


def test_admin_email_passes_admin_check(client_a):
    with patch("app.config.settings.admin_emails", "someone@x.com, A@Example.com"):
        response = client_a.post("/api/v1/admin/questions/", json={})
    # Past the admin check; fails only on body validation
    assert response.status_code == 422


# ===========================================
# Debug and diagnostics
# ===========================================

def test_debug_db_endpoint_removed(anon_client):
    assert anon_client.get("/api/v1/debug/db").status_code == 404


def test_llm_status_never_calls_llm(anon_client):
    with patch("app.services.llm_bridge.test_llm_connection",
               side_effect=AssertionError("must not call the LLM")):
        response = anon_client.get("/api/v1/llm/status")
    assert response.status_code == 200
