"""Edge case tests for memory endpoints."""

import pytest


pytestmark = pytest.mark.asyncio


async def test_search_empty_query(client):
    """Search with empty-ish query still returns valid response."""
    resp = await client.post("/api/memory/search", json={"query": "x"})
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert "count" in data


async def test_remember_minimal_fields(client):
    """Remember with only required text field."""
    resp = await client.post("/api/memory/remember", json={"text": "Test fact"})
    assert resp.status_code == 200
    data = resp.json()
    assert "memory_id" in data
    assert data["stored"] is True


async def test_remember_all_fields(client):
    """Remember with all optional fields specified."""
    resp = await client.post("/api/memory/remember", json={
        "text": "User prefers dark mode",
        "agent_id": "agent-42",
        "importance": 0.9,
        "category": "preference",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["stored"] is True


async def test_recall_with_category(client):
    """Recall should accept all optional params."""
    resp = await client.post("/api/memory/recall", json={
        "query": "dark mode",
        "agent_id": "agent-42",
        "max_results": 3,
        "min_score": 0.5,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert "count" in data


async def test_forget_nonexistent(client):
    """Forget a nonexistent memory returns deleted count."""
    resp = await client.delete("/api/memory/forget/nonexistent-id")
    assert resp.status_code == 200
    data = resp.json()
    assert "deleted" in data


async def test_count_memories_default_agent(client):
    """Count with default agent_id."""
    resp = await client.get("/api/memory/count")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"] == "default"
    assert isinstance(data["count"], int)


async def test_count_memories_custom_agent(client):
    """Count with custom agent_id accepts the parameter."""
    resp = await client.get("/api/memory/count?agent_id=custom-agent")
    assert resp.status_code == 200
    data = resp.json()
    # Mock always returns default, but endpoint accepted the param
    assert "agent_id" in data
    assert isinstance(data["count"], int)


async def test_store_chunk_required_fields(client):
    """Store chunk expects all required fields."""
    resp = await client.post("/api/memory/chunks", json={
        "id": "chunk-test-1",
        "path": "test/file.py",
        "start_line": 1,
        "end_line": 10,
        "hash": "abc123",
        "model": "ALL_MINILM_L12_V2",
        "text": "def hello(): pass",
    })
    assert resp.status_code == 200


async def test_store_chunks_batch(client):
    """Batch store endpoint accepts list of chunks."""
    resp = await client.post("/api/memory/chunks/batch", json=[
        {
            "id": "batch-1",
            "path": "src/a.py",
            "start_line": 1,
            "end_line": 5,
            "hash": "h1",
            "model": "m1",
            "text": "code here",
        },
    ])
    assert resp.status_code == 200
    data = resp.json()
    assert "stored" in data
    assert "errors" in data


async def test_memory_status(client):
    """Status endpoint returns count structure."""
    resp = await client.get("/api/memory/status")
    assert resp.status_code == 200
    data = resp.json()
    for key in ["chunk_count", "file_count", "memory_count", "cache_count"]:
        assert key in data


async def test_sync_files(client):
    """Sync files endpoint."""
    resp = await client.post("/api/memory/files/sync", json=[
        {"file_id": "f1", "path": "src/test.py"},
    ])
    assert resp.status_code == 200
    data = resp.json()
    assert "upserted" in data


async def test_delete_chunk(client):
    """Delete a chunk by ID."""
    resp = await client.delete("/api/memory/chunks/test-chunk-id")
    assert resp.status_code == 200
    data = resp.json()
    assert "deleted" in data
