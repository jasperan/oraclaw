import logging
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from ..migration.sqlite_to_oracle import SqliteToOracleMigrator
from ..migration.sessions_to_oracle import SessionsMigrator
from ..migration.transcripts_to_oracle import TranscriptsMigrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/migrate")

# Track migrators at module level for status polling
_active_migrators: dict[str, object] = {}


class SqliteMigrateRequest(BaseModel):
    sqlite_path: str
    agent_id: Optional[str] = None


class SessionsMigrateRequest(BaseModel):
    sessions_path: str


class TranscriptsMigrateRequest(BaseModel):
    path: str
    mode: str = "file"  # "file" or "directory"


def _ensure_pool(request: Request):
    pool = request.app.state.pool
    if not pool:
        raise HTTPException(status_code=503, detail="Database pool not available")
    return pool


@router.post("/sqlite")
async def migrate_sqlite(request: Request, body: SqliteMigrateRequest):
    """Trigger SQLite to Oracle migration."""
    pool = _ensure_pool(request)
    embedding_service = request.app.state.embedding_service
    settings = request.app.state.settings

    if not embedding_service:
        raise HTTPException(status_code=503, detail="Embedding service not available (required for re-embedding)")

    migrator = SqliteToOracleMigrator(pool, embedding_service, settings)
    _active_migrators["sqlite"] = migrator

    result = await migrator.migrate(body.sqlite_path)
    return result


@router.post("/sessions")
async def migrate_sessions(request: Request, body: SessionsMigrateRequest):
    """Trigger sessions.json migration."""
    pool = _ensure_pool(request)

    migrator = SessionsMigrator(pool)
    _active_migrators["sessions"] = migrator

    result = await migrator.migrate(body.sessions_path)
    return result


@router.post("/transcripts")
async def migrate_transcripts(request: Request, body: TranscriptsMigrateRequest):
    """Trigger transcript JSONL migration."""
    pool = _ensure_pool(request)

    migrator = TranscriptsMigrator(pool)
    _active_migrators["transcripts"] = migrator

    if body.mode == "directory":
        result = await migrator.migrate_directory(body.path)
    else:
        result = await migrator.migrate(body.path)
    return result


@router.get("/status")
async def migration_status():
    """Get migration progress for all active migrators."""
    statuses = {}
    for name, migrator in _active_migrators.items():
        statuses[name] = migrator.status
    if not statuses:
        return {"status": "no active migrations"}
    return statuses
