"""Tests for /api/memory/* endpoints."""

import pytest


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

async def test_search(client, app_with_mocks):
    """POST /api/memory/search returns results."""
    resp = await client.post("/api/memory/search", json={
        "query": "test query",
        "max_results": 5,
        "min_score": 0.3,
        "hybrid": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert "count" in data
    assert data["count"] == 1
    assert data["results"][0]["score"] == 0.85

    svc = app_with_mocks.state.memory_service
    svc.search.assert_awaited_once_with(
        query="test query", max_results=5, min_score=0.3, source=None, hybrid=True,
    )


async def test_search_with_source_filter(client, app_with_mocks):
    """POST /api/memory/search with source filter."""
    resp = await client.post("/api/memory/search", json={
        "query": "filtered",
        "source": "sessions",
    })
    assert resp.status_code == 200

    svc = app_with_mocks.state.memory_service
    svc.search.assert_awaited_with(
        query="filtered", max_results=6, min_score=0.3, source="sessions", hybrid=True,
    )


async def test_search_service_unavailable(client_no_db):
    """POST /api/memory/search returns 503 without service."""
    resp = await client_no_db.post("/api/memory/search", json={"query": "test"})
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Store chunk
# ---------------------------------------------------------------------------

async def test_store_single_chunk(client, app_with_mocks):
    """POST /api/memory/chunks stores a chunk."""
    chunk = {
        "id": "chunk-1",
        "path": "src/main.py",
        "source": "memory",
        "start_line": 1,
        "end_line": 10,
        "hash": "abc123",
        "model": "ALL_MINILM_L12_V2",
        "text": "def main(): pass",
    }
    resp = await client.post("/api/memory/chunks", json=chunk)
    assert resp.status_code == 200
    data = resp.json()
    assert data["stored"] is True
    assert data["id"] == "chunk-1"


async def test_store_chunks_batch(client, app_with_mocks):
    """POST /api/memory/chunks/batch stores multiple chunks."""
    chunks = [
        {
            "id": f"chunk-{i}",
            "path": f"file-{i}.py",
            "source": "memory",
            "start_line": 1,
            "end_line": 5,
            "hash": f"hash-{i}",
            "model": "model",
            "text": f"content {i}",
        }
        for i in range(2)
    ]
    resp = await client.post("/api/memory/chunks/batch", json=chunks)
    assert resp.status_code == 200
    data = resp.json()
    assert data["stored"] == 2
    assert data["errors"] == []


# ---------------------------------------------------------------------------
# Delete chunk
# ---------------------------------------------------------------------------

async def test_delete_chunk(client, app_with_mocks):
    """DELETE /api/memory/chunks/{id} deletes a chunk."""
    resp = await client.delete("/api/memory/chunks/chunk-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] == 1

    app_with_mocks.state.memory_service.delete_chunk.assert_awaited_once_with("chunk-1")


# ---------------------------------------------------------------------------
# Sync files
# ---------------------------------------------------------------------------

async def test_sync_files(client, app_with_mocks):
    """POST /api/memory/files/sync upserts file metadata."""
    files = [
        {
            "file_id": "f-1",
            "path": "/src/app.py",
            "source": "memory",
            "hash": "deadbeef",
            "chunk_count": 3,
        }
    ]
    resp = await client.post("/api/memory/files/sync", json=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["upserted"] == 1


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

async def test_memory_status(client):
    """GET /api/memory/status returns counts."""
    resp = await client.get("/api/memory/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["chunk_count"] == 10
    assert data["file_count"] == 3
    assert data["memory_count"] == 5
    assert data["cache_count"] == 2


# ---------------------------------------------------------------------------
# Remember / Recall / Forget (long-term memory)
# ---------------------------------------------------------------------------

async def test_remember(client, app_with_mocks):
    """POST /api/memory/remember stores a long-term memory."""
    resp = await client.post("/api/memory/remember", json={
        "text": "The database password is rotated weekly",
        "agent_id": "default",
        "importance": 0.9,
        "category": "fact",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["stored"] is True
    assert "memory_id" in data


async def test_remember_defaults(client, app_with_mocks):
    """POST /api/memory/remember with minimal payload uses defaults."""
    resp = await client.post("/api/memory/remember", json={
        "text": "Something important",
    })
    assert resp.status_code == 200
    svc = app_with_mocks.state.memory_service
    svc.remember.assert_awaited_with(
        text="Something important", agent_id="default", importance=0.7, category="other",
    )


async def test_recall(client, app_with_mocks):
    """POST /api/memory/recall searches long-term memories."""
    resp = await client.post("/api/memory/recall", json={
        "query": "database password",
        "max_results": 3,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["results"][0]["text"] == "Recalled fact"
    assert data["results"][0]["score"] == 0.9


async def test_forget(client, app_with_mocks):
    """DELETE /api/memory/forget/{id} deletes a long-term memory."""
    resp = await client.delete("/api/memory/forget/mem-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] == 1
    app_with_mocks.state.memory_service.forget.assert_awaited_once_with("mem-1")


async def test_count_memories(client):
    """GET /api/memory/count returns memory count for an agent."""
    resp = await client.get("/api/memory/count", params={"agent_id": "default"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 5
    assert data["agent_id"] == "default"
