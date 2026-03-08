"""Tests for /api/sessions/* endpoints."""

import time

import pytest


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# List / Get
# ---------------------------------------------------------------------------

async def test_list_sessions(client, app_with_mocks):
    """GET /api/sessions/ returns session list."""
    resp = await client.get("/api/sessions/", params={"agent_id": "default"})
    assert resp.status_code == 200
    data = resp.json()
    assert "sessions" in data
    assert "count" in data
    assert data["count"] == 1
    assert data["sessions"][0]["session_key"] == "sk-1"


async def test_get_session(client, app_with_mocks):
    """GET /api/sessions/{key} returns a single session."""
    resp = await client.get("/api/sessions/sk-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_key"] == "sk-1"
    assert data["session_id"] == "sid-1"
    assert "session_data" in data
    assert isinstance(data["session_data"], dict)


async def test_get_session_not_found(client, app_with_mocks):
    """GET /api/sessions/{key} returns 404 for unknown key."""
    app_with_mocks.state.session_service.get_session = pytest.importorskip(
        "unittest.mock"
    ).AsyncMock(return_value=None)
    resp = await client.get("/api/sessions/nonexistent")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def test_upsert_session(client, app_with_mocks):
    """PUT /api/sessions/ creates or updates a session."""
    now_ms = int(time.time() * 1000)
    body = {
        "session_key": "sk-new",
        "session_id": "sid-new",
        "agent_id": "default",
        "updated_at": now_ms,
        "session_data": {"messages": [{"role": "user", "text": "hi"}]},
        "channel": "discord",
        "label": "New session",
    }
    resp = await client.put("/api/sessions/", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["upserted"] is True


async def test_update_session_partial(client, app_with_mocks):
    """PATCH /api/sessions/{key} does partial update."""
    resp = await client.patch("/api/sessions/sk-1", json={
        "label": "Updated label",
        "channel": "slack",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["updated"] is True

    svc = app_with_mocks.state.session_service
    svc.update_session.assert_awaited_once_with("sk-1", {
        "label": "Updated label",
        "channel": "slack",
    })


async def test_delete_session(client, app_with_mocks):
    """DELETE /api/sessions/{key} deletes a session."""
    resp = await client.delete("/api/sessions/sk-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] == 1


# ---------------------------------------------------------------------------
# Prune stale sessions
# ---------------------------------------------------------------------------

async def test_prune_stale(client, app_with_mocks):
    """POST /api/sessions/prune removes old sessions."""
    resp = await client.post("/api/sessions/prune", json={
        "agent_id": "default",
        "max_age_ms": 86400000,  # 1 day
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["pruned"] == 2


async def test_prune_stale_defaults(client, app_with_mocks):
    """POST /api/sessions/prune uses default max_age_ms (30 days)."""
    resp = await client.post("/api/sessions/prune", json={
        "agent_id": "default",
    })
    assert resp.status_code == 200
    svc = app_with_mocks.state.session_service
    svc.prune_stale.assert_awaited_with(agent_id="default", max_age_ms=2592000000)


# ---------------------------------------------------------------------------
# Cap entry count
# ---------------------------------------------------------------------------

async def test_cap_count(client, app_with_mocks):
    """POST /api/sessions/cap keeps only N newest sessions."""
    resp = await client.post("/api/sessions/cap", json={
        "agent_id": "default",
        "max_count": 100,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["removed"] == 3
    assert data["max_count"] == 100


# ---------------------------------------------------------------------------
# JSON column integrity
# ---------------------------------------------------------------------------

async def test_session_data_is_dict(client, app_with_mocks):
    """Session data returned from GET is a proper dict, not a JSON string."""
    resp = await client.get("/api/sessions/sk-1")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["session_data"], dict)
    assert "messages" in data["session_data"]


async def test_upsert_preserves_nested_json(client, app_with_mocks):
    """PUT with nested session_data passes dict correctly."""
    now_ms = int(time.time() * 1000)
    nested = {
        "messages": [
            {"role": "user", "text": "hello"},
            {"role": "assistant", "text": "world"},
        ],
        "metadata": {"temperature": 0.7, "model": "opus"},
    }
    body = {
        "session_key": "sk-nested",
        "session_id": "sid-nested",
        "agent_id": "default",
        "updated_at": now_ms,
        "session_data": nested,
    }
    resp = await client.put("/api/sessions/", json=body)
    assert resp.status_code == 200

    svc = app_with_mocks.state.session_service
    call_args = svc.upsert_session.call_args[0][0]
    assert call_args["session_data"] == nested


# ---------------------------------------------------------------------------
# Service unavailable
# ---------------------------------------------------------------------------

async def test_sessions_service_unavailable(client_no_db):
    """Session endpoints return 503 without service."""
    resp = await client_no_db.get("/api/sessions/")
    assert resp.status_code == 503

    resp = await client_no_db.put("/api/sessions/", json={
        "session_key": "x",
        "session_id": "y",
        "agent_id": "default",
        "updated_at": 0,
        "session_data": {},
    })
    assert resp.status_code == 503
