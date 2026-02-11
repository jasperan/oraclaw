import json
import logging

import oracledb

logger = logging.getLogger(__name__)


async def _read_lob(val):
    """Read a LOB value to string, or return as-is if already a string."""
    if val is None:
        return None
    if isinstance(val, (oracledb.AsyncLOB,)):
        return await val.read()
    if hasattr(val, 'read') and not isinstance(val, str):
        result = val.read()
        if hasattr(result, '__await__'):
            return await result
        return result
    return val


class SessionService:
    def __init__(self, pool):
        self.pool = pool

    async def get_sessions(self, agent_id: str = "default") -> list[dict]:
        """Get all sessions for an agent."""
        async with self.pool.acquire() as conn:
            cursor = conn.cursor()
            await cursor.execute(
                """
                SELECT session_key, session_id, agent_id, updated_at,
                       session_data, channel, label
                FROM ORACLAW_SESSIONS
                WHERE agent_id = :agent_id
                ORDER BY updated_at DESC
                """,
                {"agent_id": agent_id},
            )
            rows = await cursor.fetchall()
            return [await _row_to_session(row) for row in rows]

    async def get_session(self, session_key: str) -> dict | None:
        """Get a single session by key."""
        async with self.pool.acquire() as conn:
            cursor = conn.cursor()
            await cursor.execute(
                """
                SELECT session_key, session_id, agent_id, updated_at,
                       session_data, channel, label
                FROM ORACLAW_SESSIONS
                WHERE session_key = :session_key
                """,
                {"session_key": session_key},
            )
            row = await cursor.fetchone()
            return (await _row_to_session(row)) if row else None

    async def upsert_session(self, session: dict) -> dict:
        """Upsert a session using MERGE INTO."""
        session_data_json = json.dumps(session.get("session_data", {}))
        async with self.pool.acquire() as conn:
            cursor = conn.cursor()
            await cursor.execute(
                """
                MERGE INTO ORACLAW_SESSIONS s
                USING (SELECT :session_key AS session_key FROM DUAL) src
                ON (s.session_key = src.session_key)
                WHEN MATCHED THEN
                    UPDATE SET session_id = :session_id, agent_id = :agent_id,
                               updated_at = :updated_at, session_data = :session_data,
                               channel = :channel, label = :label
                WHEN NOT MATCHED THEN
                    INSERT (session_key, session_id, agent_id, updated_at,
                            session_data, channel, label)
                    VALUES (:session_key, :session_id, :agent_id, :updated_at,
                            :session_data, :channel, :label)
                """,
                {
                    "session_key": session["session_key"],
                    "session_id": session["session_id"],
                    "agent_id": session.get("agent_id", "default"),
                    "updated_at": session["updated_at"],
                    "session_data": session_data_json,
                    "channel": session.get("channel"),
                    "label": session.get("label"),
                },
            )
            await conn.commit()
        return {"session_key": session["session_key"], "upserted": True}

    async def update_session(self, session_key: str, updates: dict) -> dict:
        """Partial update of a session."""
        set_clauses = []
        params = {"session_key": session_key}

        if "session_data" in updates:
            set_clauses.append("session_data = :session_data")
            params["session_data"] = json.dumps(updates["session_data"])
        if "updated_at" in updates:
            set_clauses.append("updated_at = :updated_at")
            params["updated_at"] = updates["updated_at"]
        if "channel" in updates:
            set_clauses.append("channel = :channel")
            params["channel"] = updates["channel"]
        if "label" in updates:
            set_clauses.append("label = :label")
            params["label"] = updates["label"]

        if not set_clauses:
            return {"session_key": session_key, "updated": False, "reason": "no fields to update"}

        sql = f"UPDATE ORACLAW_SESSIONS SET {', '.join(set_clauses)} WHERE session_key = :session_key"
        async with self.pool.acquire() as conn:
            cursor = conn.cursor()
            await cursor.execute(sql, params)
            updated = cursor.rowcount
            await conn.commit()
        return {"session_key": session_key, "updated": updated > 0}

    async def delete_session(self, session_key: str) -> dict:
        """Delete a session by key."""
        async with self.pool.acquire() as conn:
            cursor = conn.cursor()
            await cursor.execute(
                "DELETE FROM ORACLAW_SESSIONS WHERE session_key = :session_key",
                {"session_key": session_key},
            )
            deleted = cursor.rowcount
            await conn.commit()
        return {"deleted": deleted}

    async def prune_stale(self, agent_id: str = "default", max_age_ms: int = 2592000000) -> dict:
        """Remove sessions older than max_age_ms."""
        import time
        cutoff = int(time.time() * 1000) - max_age_ms

        async with self.pool.acquire() as conn:
            cursor = conn.cursor()
            await cursor.execute(
                """
                DELETE FROM ORACLAW_SESSIONS
                WHERE agent_id = :agent_id AND updated_at < :cutoff
                """,
                {"agent_id": agent_id, "cutoff": cutoff},
            )
            pruned = cursor.rowcount
            await conn.commit()
        return {"pruned": pruned, "agent_id": agent_id}

    async def cap_count(self, agent_id: str = "default", max_count: int = 500) -> dict:
        """Keep only the most recent max_count sessions."""
        async with self.pool.acquire() as conn:
            cursor = conn.cursor()
            await cursor.execute(
                """
                DELETE FROM ORACLAW_SESSIONS
                WHERE agent_id = :agent_id
                  AND session_key NOT IN (
                      SELECT session_key FROM (
                          SELECT session_key FROM ORACLAW_SESSIONS
                          WHERE agent_id = :agent_id
                          ORDER BY updated_at DESC
                          FETCH FIRST :max_count ROWS ONLY
                      )
                  )
                """,
                {"agent_id": agent_id, "max_count": max_count},
            )
            removed = cursor.rowcount
            await conn.commit()
        return {"removed": removed, "agent_id": agent_id, "max_count": max_count}


async def _row_to_session(row) -> dict:
    """Convert a database row to a session dict."""
    session_data_raw = await _read_lob(row[4])
    if isinstance(session_data_raw, str):
        try:
            session_data = json.loads(session_data_raw)
        except (json.JSONDecodeError, TypeError):
            session_data = {}
    elif session_data_raw is None:
        session_data = {}
    else:
        session_data = session_data_raw

    return {
        "session_key": row[0],
        "session_id": row[1],
        "agent_id": row[2],
        "updated_at": row[3],
        "session_data": session_data,
        "channel": row[5],
        "label": row[6],
    }
