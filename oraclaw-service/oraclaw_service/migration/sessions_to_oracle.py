import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SessionsMigrator:
    """Migrates sessions.json to Oracle ORACLAW_SESSIONS table."""

    def __init__(self, pool):
        self.pool = pool
        self._status = {
            "state": "idle",
            "sessions_total": 0,
            "sessions_migrated": 0,
            "errors": [],
        }

    @property
    def status(self) -> dict:
        return dict(self._status)

    async def migrate(self, sessions_path: str) -> dict:
        """Migrate sessions from a JSON file to Oracle."""
        self._status["state"] = "running"
        self._status["errors"] = []

        path = Path(sessions_path)
        if not path.exists():
            self._status["state"] = "error"
            self._status["errors"].append(f"Sessions file not found: {sessions_path}")
            return self._status

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            self._status["state"] = "error"
            self._status["errors"].append(f"Failed to read sessions file: {e}")
            return self._status

        # Handle both array format and object-with-sessions-key format
        sessions = []
        if isinstance(data, list):
            sessions = data
        elif isinstance(data, dict):
            sessions = data.get("sessions", data.get("entries", []))
            if not sessions and all(isinstance(v, dict) for v in data.values()):
                # Object keyed by session_key
                for key, value in data.items():
                    if isinstance(value, dict):
                        value.setdefault("session_key", key)
                        sessions.append(value)

        self._status["sessions_total"] = len(sessions)

        async with self.pool.acquire() as conn:
            for session in sessions:
                try:
                    session_key = session.get("session_key", session.get("sessionKey", ""))
                    session_id = session.get("session_id", session.get("sessionId", session_key))
                    agent_id = session.get("agent_id", session.get("agentId", "default"))
                    updated_at = session.get("updated_at", session.get("updatedAt", 0))
                    channel = session.get("channel")
                    label = session.get("label")

                    # session_data: could be nested or the entire object minus known keys
                    session_data = session.get("session_data", session.get("sessionData"))
                    if session_data is None:
                        known_keys = {
                            "session_key", "sessionKey", "session_id", "sessionId",
                            "agent_id", "agentId", "updated_at", "updatedAt",
                            "channel", "label",
                        }
                        session_data = {k: v for k, v in session.items() if k not in known_keys}

                    session_data_json = json.dumps(session_data) if isinstance(session_data, dict) else str(session_data)

                    if not session_key:
                        logger.warning("Skipping session with no key: %s", session)
                        continue

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
                            "session_key": session_key,
                            "session_id": session_id,
                            "agent_id": agent_id,
                            "updated_at": updated_at,
                            "session_data": session_data_json,
                            "channel": channel,
                            "label": label,
                        },
                    )
                    self._status["sessions_migrated"] += 1
                except Exception as e:
                    logger.error("Error migrating session: %s", e)
                    self._status["errors"].append(str(e))

            await conn.commit()

        self._status["state"] = "completed"
        return self._status
