"""Tests for bearer token authentication middleware."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from oraclaw_service.config import OraclawSettings


pytestmark = pytest.mark.asyncio


def _make_settings(**overrides) -> OraclawSettings:
    defaults = {
        "oracle_mode": "freepdb",
        "oracle_user": "test",
        "oracle_password": "test",
        "oracle_host": "localhost",
        "oracle_port": 1521,
        "oracle_service": "FREEPDB1",
        "oracle_pool_min": 1,
        "oracle_pool_max": 2,
        "oracle_onnx_model": "ALL_MINILM_L12_V2",
        "auto_init": False,
    }
    defaults.update(overrides)
    return OraclawSettings(**defaults)


@pytest_asyncio.fixture
async def app_with_token():
    """FastAPI app with bearer token required."""
    from oraclaw_service.main import app

    app.state.settings = _make_settings(oraclaw_service_token="test-secret-token")
    app.state.pool = None
    app.state.embedding_service = None
    app.state.memory_service = None
    app.state.session_service = None
    app.state.transcript_service = None
    yield app


@pytest_asyncio.fixture
async def client_with_token(app_with_token):
    transport = ASGITransport(app=app_with_token)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_request_without_token_is_rejected(client_with_token):
    """Requests without Authorization header are rejected when token is set."""
    resp = await client_with_token.get("/api/health")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized"


async def test_request_with_wrong_token_is_rejected(client_with_token):
    """Requests with wrong token are rejected."""
    resp = await client_with_token.get(
        "/api/health",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 401


async def test_request_with_correct_token_is_allowed(client_with_token):
    """Requests with correct token are allowed through."""
    resp = await client_with_token.get(
        "/api/health",
        headers={"Authorization": "Bearer test-secret-token"},
    )
    assert resp.status_code == 200


async def test_no_token_config_allows_all(client_no_db):
    """When no token is configured, all requests are allowed."""
    resp = await client_no_db.get("/api/health")
    assert resp.status_code == 200


def test_onnx_model_validation_accepts_valid():
    """Valid model names are accepted."""
    s = _make_settings(oracle_onnx_model="ALL_MINILM_L12_V2")
    assert s.oracle_onnx_model == "ALL_MINILM_L12_V2"


def test_onnx_model_validation_rejects_sql_injection():
    """Model names with SQL injection chars are rejected."""
    with pytest.raises(Exception):
        _make_settings(oracle_onnx_model="model; DROP TABLE users--")


def test_onnx_model_validation_rejects_special_chars():
    """Model names with special characters are rejected."""
    with pytest.raises(Exception):
        _make_settings(oracle_onnx_model="model'name")
