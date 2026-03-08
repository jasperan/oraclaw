import json
import logging
import uuid

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


class TranscriptService:
    def __init__(self, pool):
        self.pool = pool

    async def append(self, session_id: str, agent_id: str, event_type: str,
                     event_data: dict) -> dict:
        """Append event with auto-incrementing sequence_num."""
        event_id = str(uuid.uuid4())
        event_data_json = json.dumps(event_data)

        async with self.pool.acquire() as conn:
            # Get next sequence number for this session
            cursor = conn.cursor()
            await cursor.execute(
                """
                SELECT COALESCE(MAX(sequence_num), -1) + 1
                FROM ORACLAW_TRANSCRIPTS
                WHERE session_id = :session_id
                """,
                {"session_id": session_id},
            )
            row = await cursor.fetchone()
            seq_num = row[0] if row else 0

            await cursor.execute(
                """
                INSERT INTO ORACLAW_TRANSCRIPTS
                    (id, session_id, agent_id, sequence_num, event_type, event_data)
                VALUES (:id, :session_id, :agent_id, :sequence_num, :event_type, :event_data)
                """,
                {
                    "id": event_id,
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "sequence_num": seq_num,
                    "event_type": event_type,
                    "event_data": event_data_json,
                },
            )
            await conn.commit()

        return {
            "id": event_id,
            "session_id": session_id,
            "sequence_num": seq_num,
            "event_type": event_type,
        }

    async def get_events(self, session_id: str, offset: int = 0,
                         limit: int = 100) -> list[dict]:
        """Read events with ordering."""
        async with self.pool.acquire() as conn:
            cursor = conn.cursor()
            await cursor.execute(
                """
                SELECT id, session_id, agent_id, sequence_num, event_type,
                       event_data, created_at
                FROM ORACLAW_TRANSCRIPTS
                WHERE session_id = :session_id
                ORDER BY sequence_num ASC
                OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
                """,
                {"session_id": session_id, "offset": offset, "limit": limit},
            )
            rows = await cursor.fetchall()
            return [await _row_to_event(row) for row in rows]

    async def get_header(self, session_id: str) -> dict | None:
        """Get session header (sequence 0)."""
        async with self.pool.acquire() as conn:
            cursor = conn.cursor()
            await cursor.execute(
                """
                SELECT id, session_id, agent_id, sequence_num, event_type,
                       event_data, created_at
                FROM ORACLAW_TRANSCRIPTS
                WHERE session_id = :session_id AND sequence_num = 0
                """,
                {"session_id": session_id},
            )
            row = await cursor.fetchone()
            return (await _row_to_event(row)) if row else None

    async def delete_session(self, session_id: str) -> dict:
        """Delete all events for a session."""
        async with self.pool.acquire() as conn:
            cursor = conn.cursor()
            await cursor.execute(
                "DELETE FROM ORACLAW_TRANSCRIPTS WHERE session_id = :session_id",
                {"session_id": session_id},
            )
            deleted = cursor.rowcount
            await conn.commit()
        return {"deleted": deleted, "session_id": session_id}


async def _row_to_event(row) -> dict:
    """Convert a database row to an event dict."""
    event_data_raw = await _read_lob(row[5])
    if isinstance(event_data_raw, str):
        try:
            event_data = json.loads(event_data_raw)
        except (json.JSONDecodeError, TypeError):
            event_data = {}
    elif event_data_raw is None:
        event_data = {}
    else:
        event_data = event_data_raw

    return {
        "id": row[0],
        "session_id": row[1],
        "agent_id": row[2],
        "sequence_num": row[3],
        "event_type": row[4],
        "event_data": event_data,
        "created_at": str(row[6]) if row[6] else "",
    }
