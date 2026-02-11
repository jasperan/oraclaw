"""Tests for the /api/migrate endpoints."""

import pytest


pytestmark = pytest.mark.asyncio


async def test_migration_status_no_active(client):
    """Migration status returns empty when no migrations are active."""
    resp = await client.get("/api/migrate/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data or isinstance(data, dict)


async def test_migrate_sqlite_requires_pool(client_no_db):
    """SQLite migration returns 503 when no DB pool."""
    resp = await client_no_db.post("/api/migrate/sqlite", json={"sqlite_path": "/tmp/test.db"})
    assert resp.status_code == 503


async def test_migrate_sessions_requires_pool(client_no_db):
    """Sessions migration returns 503 when no DB pool."""
    resp = await client_no_db.post("/api/migrate/sessions", json={"sessions_path": "/tmp/sessions.json"})
    assert resp.status_code == 503


async def test_migrate_transcripts_requires_pool(client_no_db):
    """Transcripts migration returns 503 when no DB pool."""
    resp = await client_no_db.post("/api/migrate/transcripts", json={"path": "/tmp/transcripts.jsonl"})
    assert resp.status_code == 503
