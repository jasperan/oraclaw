"""Test configuration and shared fixtures for OracLaw service tests.

Uses mock services by default so tests can run without an Oracle database.
Set ORACLAW_TEST_LIVE=1 + provide Oracle credentials to run against a real DB.
"""

import os
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from oraclaw_service.config import OraclawSettings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Mock pool & connection
# ---------------------------------------------------------------------------

class MockCursor:
    def __init__(self, rows=None, rowcount=0):
        self._rows = rows or []
        self.rowcount = rowcount

    async def execute(self, sql, params=None):
        pass

    async def fetchall(self):
        return self._rows

    async def fetchone(self):
        return self._rows[0] if self._rows else None


class MockConnection:
    def __init__(self):
        self._execute_results = {}

    def cursor(self):
        return MockCursor()

    async def execute(self, sql, params=None):
        return MockCursor()

    async def commit(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class MockPool:
    def __init__(self):
        self.min = 1
        self.max = 2
        self.busy = 0
        self.opened = 1
        self._conn = MockConnection()

    def acquire(self):
        return self._conn

    async def close(self):
        pass


# ---------------------------------------------------------------------------
# Mock services
# ---------------------------------------------------------------------------

def make_mock_embedding_service():
    svc = AsyncMock()
    svc.mode = "onnx_db"
    svc.embed_query = AsyncMock(return_value=[0.1] * 384)
    svc.embed_texts = AsyncMock(return_value=[[0.1] * 384])
    svc.check_onnx_loaded = AsyncMock(return_value=True)
    svc.load_onnx_model = AsyncMock()
    svc.initialize = AsyncMock()
    svc._embeddings = MagicMock()
    return svc


def make_mock_memory_service():
    svc = AsyncMock()

    svc.search = AsyncMock(return_value=[
        {
            "path": "memory/notes.md",
            "startLine": 1,
            "endLine": 5,
            "snippet": "Test memory snippet",
            "score": 0.85,
            "source": "memory",
        }
    ])

    svc.store_chunk = AsyncMock(return_value={"id": "chunk-1", "stored": True})
    svc.store_chunks_batch = AsyncMock(return_value={"stored": 2, "errors": []})
    svc.delete_chunk = AsyncMock(return_value={"deleted": 1})
    svc.sync_files = AsyncMock(return_value={"upserted": 1})
    svc.get_status = AsyncMock(return_value={
        "chunk_count": 10,
        "file_count": 3,
        "memory_count": 5,
        "cache_count": 2,
    })
    svc.remember = AsyncMock(side_effect=lambda **kw: {
        "memory_id": str(uuid.uuid4()),
        "stored": True,
    })
    svc.recall = AsyncMock(return_value=[
        {
            "memory_id": "mem-1",
            "agent_id": "default",
            "text": "Recalled fact",
            "importance": 0.8,
            "category": "fact",
            "score": 0.9,
            "created_at": "2026-01-01 00:00:00",
            "accessed_at": "2026-01-01 00:00:00",
            "access_count": 1,
        }
    ])
    svc.forget = AsyncMock(return_value={"deleted": 1})
    svc.count_memories = AsyncMock(return_value={"agent_id": "default", "count": 5})
    svc.initialize = AsyncMock()

    return svc


def make_mock_session_service():
    svc = AsyncMock()

    _now_ms = int(time.time() * 1000)

    svc.get_sessions = AsyncMock(return_value=[
        {
            "session_key": "sk-1",
            "session_id": "sid-1",
            "agent_id": "default",
            "updated_at": _now_ms,
            "session_data": {"messages": []},
            "channel": "telegram",
            "label": "Test session",
        }
    ])
    svc.get_session = AsyncMock(return_value={
        "session_key": "sk-1",
        "session_id": "sid-1",
        "agent_id": "default",
        "updated_at": _now_ms,
        "session_data": {"messages": [{"role": "user", "text": "hello"}]},
        "channel": "telegram",
        "label": "Test session",
    })
    svc.upsert_session = AsyncMock(return_value={"session_key": "sk-1", "upserted": True})
    svc.update_session = AsyncMock(return_value={"session_key": "sk-1", "updated": True})
    svc.delete_session = AsyncMock(return_value={"deleted": 1})
    svc.prune_stale = AsyncMock(return_value={"pruned": 2, "agent_id": "default"})
    svc.cap_count = AsyncMock(return_value={"removed": 3, "agent_id": "default", "max_count": 100})

    return svc


def make_mock_transcript_service():
    svc = AsyncMock()

    svc.append = AsyncMock(side_effect=lambda **kw: {
        "id": str(uuid.uuid4()),
        "session_id": kw.get("session_id", "sess-1"),
        "sequence_num": 0,
        "event_type": kw.get("event_type", "message"),
    })
    svc.get_events = AsyncMock(return_value=[
        {
            "id": "ev-1",
            "session_id": "sess-1",
            "agent_id": "default",
            "sequence_num": 0,
            "event_type": "header",
            "event_data": {"title": "Test"},
            "created_at": "2026-01-01 00:00:00",
        },
        {
            "id": "ev-2",
            "session_id": "sess-1",
            "agent_id": "default",
            "sequence_num": 1,
            "event_type": "message",
            "event_data": {"role": "user", "text": "hello"},
            "created_at": "2026-01-01 00:00:01",
        },
    ])
    svc.get_header = AsyncMock(return_value={
        "id": "ev-1",
        "session_id": "sess-1",
        "agent_id": "default",
        "sequence_num": 0,
        "event_type": "header",
        "event_data": {"title": "Test"},
        "created_at": "2026-01-01 00:00:00",
    })
    svc.delete_session = AsyncMock(return_value={"deleted": 3, "session_id": "sess-1"})

    return svc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def settings():
    return _make_settings()


@pytest.fixture
def mock_pool():
    return MockPool()


@pytest.fixture
def mock_embedding_service():
    return make_mock_embedding_service()


@pytest.fixture
def mock_memory_service():
    return make_mock_memory_service()


@pytest.fixture
def mock_session_service():
    return make_mock_session_service()


@pytest.fixture
def mock_transcript_service():
    return make_mock_transcript_service()


@pytest_asyncio.fixture
async def app_no_db():
    """FastAPI app with pool=None (no database). Services unavailable (503)."""
    from oraclaw_service.main import app

    app.state.settings = _make_settings()
    app.state.pool = None
    app.state.embedding_service = None
    app.state.memory_service = None
    app.state.session_service = None
    app.state.transcript_service = None
    yield app


@pytest_asyncio.fixture
async def app_with_mocks():
    """FastAPI app with all services mocked."""
    from oraclaw_service.main import app

    app.state.settings = _make_settings()
    app.state.pool = MockPool()
    app.state.embedding_service = make_mock_embedding_service()
    app.state.memory_service = make_mock_memory_service()
    app.state.session_service = make_mock_session_service()
    app.state.transcript_service = make_mock_transcript_service()
    yield app


@pytest_asyncio.fixture
async def client_no_db(app_no_db):
    """AsyncClient hitting the app with no database."""
    transport = ASGITransport(app=app_no_db)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def client(app_with_mocks):
    """AsyncClient hitting the app with mocked services."""
    transport = ASGITransport(app=app_with_mocks)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
