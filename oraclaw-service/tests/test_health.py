"""Tests for the /api/health endpoint."""

import pytest


pytestmark = pytest.mark.asyncio


async def test_health_with_mocked_db(client):
    """Health endpoint returns expected structure when pool is available."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "ok"

    # Pool info present
    assert "pool" in data
    pool = data["pool"]
    assert "min" in pool
    assert "max" in pool
    assert "busy" in pool
    assert "open" in pool

    # ONNX model info
    assert "onnx_model" in data
    assert data["onnx_model"]["name"] == "ALL_MINILM_L12_V2"

    # Tables dict
    assert "tables" in data

    # Schema version
    assert "schema_version" in data


async def test_health_without_db(client_no_db):
    """Health endpoint returns degraded info when no DB pool."""
    resp = await client_no_db.get("/api/health")
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "ok"

    # Pool should show zeros
    pool = data["pool"]
    assert pool["min"] == 0
    assert pool["max"] == 0

    # ONNX not loaded
    assert data["onnx_model"]["loaded"] is False


async def test_health_returns_correct_pool_stats(client, app_with_mocks):
    """Verify pool stats reflect the mock pool values."""
    resp = await client.get("/api/health")
    data = resp.json()

    mock_pool = app_with_mocks.state.pool
    assert data["pool"]["min"] == mock_pool.min
    assert data["pool"]["max"] == mock_pool.max
