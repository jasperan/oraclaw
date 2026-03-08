"""Tests for /api/transcripts/* endpoints."""

import pytest


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Append events
# ---------------------------------------------------------------------------

async def test_append_event(client, app_with_mocks):
    """POST /api/transcripts/ appends a transcript event."""
    resp = await client.post("/api/transcripts/", json={
        "session_id": "sess-1",
        "agent_id": "default",
        "event_type": "message",
        "event_data": {"role": "user", "text": "hello"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["session_id"] == "sess-1"
    assert data["event_type"] == "message"
    assert "sequence_num" in data


async def test_append_header_event(client, app_with_mocks):
    """Append a header event (sequence 0 by convention)."""
    resp = await client.post("/api/transcripts/", json={
        "session_id": "sess-new",
        "agent_id": "default",
        "event_type": "header",
        "event_data": {"title": "My session", "model": "opus"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["event_type"] == "header"


async def test_append_service_unavailable(client_no_db):
    """POST /api/transcripts/ returns 503 without service."""
    resp = await client_no_db.post("/api/transcripts/", json={
        "session_id": "x",
        "agent_id": "default",
        "event_type": "message",
        "event_data": {},
    })
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Read with ordering
# ---------------------------------------------------------------------------

async def test_get_events(client, app_with_mocks):
    """GET /api/transcripts/{session_id} returns ordered events."""
    resp = await client.get("/api/transcripts/sess-1")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert "count" in data
    assert data["count"] == 2

    events = data["events"]
    assert events[0]["sequence_num"] == 0
    assert events[1]["sequence_num"] == 1
    # Verify ordering: sequence_num should be ascending
    for i in range(1, len(events)):
        assert events[i]["sequence_num"] > events[i - 1]["sequence_num"]


async def test_get_events_with_pagination(client, app_with_mocks):
    """GET /api/transcripts/{session_id} supports offset and limit."""
    resp = await client.get("/api/transcripts/sess-1", params={"offset": 1, "limit": 10})
    assert resp.status_code == 200

    svc = app_with_mocks.state.transcript_service
    svc.get_events.assert_awaited_with("sess-1", offset=1, limit=10)


async def test_get_events_empty_session(client, app_with_mocks):
    """GET /api/transcripts/{session_id} returns empty for unknown session."""
    app_with_mocks.state.transcript_service.get_events.return_value = []
    resp = await client.get("/api/transcripts/nonexistent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["events"] == []


# ---------------------------------------------------------------------------
# Verify sequence numbers
# ---------------------------------------------------------------------------

async def test_sequence_numbers_are_integers(client):
    """All returned events have integer sequence_num."""
    resp = await client.get("/api/transcripts/sess-1")
    data = resp.json()
    for event in data["events"]:
        assert isinstance(event["sequence_num"], int)


async def test_sequence_numbers_start_at_zero(client):
    """First event in a session should have sequence_num 0."""
    resp = await client.get("/api/transcripts/sess-1")
    data = resp.json()
    if data["events"]:
        assert data["events"][0]["sequence_num"] == 0


# ---------------------------------------------------------------------------
# Get header
# ---------------------------------------------------------------------------

async def test_get_header(client, app_with_mocks):
    """GET /api/transcripts/{session_id}/header returns sequence 0 event."""
    resp = await client.get("/api/transcripts/sess-1/header")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sequence_num"] == 0
    assert data["event_type"] == "header"


async def test_get_header_not_found(client, app_with_mocks):
    """GET /api/transcripts/{session_id}/header returns 404 when missing."""
    app_with_mocks.state.transcript_service.get_header.return_value = None
    resp = await client.get("/api/transcripts/nonexistent/header")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete all events
# ---------------------------------------------------------------------------

async def test_delete_transcript(client, app_with_mocks):
    """DELETE /api/transcripts/{session_id} removes all events."""
    resp = await client.delete("/api/transcripts/sess-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] == 3
    assert data["session_id"] == "sess-1"

    svc = app_with_mocks.state.transcript_service
    svc.delete_session.assert_awaited_once_with("sess-1")


async def test_delete_nonexistent_transcript(client, app_with_mocks):
    """DELETE /api/transcripts/{session_id} for unknown session returns deleted=0."""
    app_with_mocks.state.transcript_service.delete_session.return_value = {
        "deleted": 0,
        "session_id": "none",
    }
    resp = await client.delete("/api/transcripts/none")
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] == 0


# ---------------------------------------------------------------------------
# Event data integrity
# ---------------------------------------------------------------------------

async def test_event_data_is_dict(client):
    """event_data in returned events should be a proper dict."""
    resp = await client.get("/api/transcripts/sess-1")
    data = resp.json()
    for event in data["events"]:
        assert isinstance(event["event_data"], dict)


async def test_append_complex_event_data(client, app_with_mocks):
    """POST with nested event_data passes through correctly."""
    complex_data = {
        "role": "assistant",
        "text": "Here is the answer",
        "metadata": {
            "tokens": 150,
            "model": "claude-opus-4-6",
            "latency_ms": 320,
        },
        "attachments": [{"type": "image", "url": "data:image/png;base64,abc"}],
    }
    resp = await client.post("/api/transcripts/", json={
        "session_id": "sess-complex",
        "agent_id": "default",
        "event_type": "message",
        "event_data": complex_data,
    })
    assert resp.status_code == 200

    svc = app_with_mocks.state.transcript_service
    svc.append.assert_awaited_with(
        session_id="sess-complex",
        agent_id="default",
        event_type="message",
        event_data=complex_data,
    )
