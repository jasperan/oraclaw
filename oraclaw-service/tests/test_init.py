"""Tests for the /api/init endpoint."""

import pytest

pytestmark = pytest.mark.asyncio


async def test_init_with_mocked_db(client):
    """Init endpoint creates schema and loads ONNX model."""
    resp = await client.post("/api/init", json={})
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "initialized"
    assert "tables_created" in data
    assert "indexes_created" in data
    assert "errors" in data
    assert "onnx_loaded" in data


async def test_init_without_db(client_no_db):
    """Init endpoint returns 503 when pool is None."""
    resp = await client_no_db.post("/api/init", json={})
    assert resp.status_code == 503
    assert "not available" in resp.json()["detail"].lower()
