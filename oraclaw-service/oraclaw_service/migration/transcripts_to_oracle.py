import json
import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


class TranscriptsMigrator:
    """Migrates JSONL transcript files to Oracle ORACLAW_TRANSCRIPTS table."""

    def __init__(self, pool):
        self.pool = pool
        self._status = {
            "state": "idle",
            "files_total": 0,
            "files_processed": 0,
            "events_total": 0,
            "events_migrated": 0,
            "errors": [],
        }

    @property
    def status(self) -> dict:
        return dict(self._status)

    def find_transcript_files(self, base_path: str | None = None) -> list[Path]:
        """Find all JSONL transcript files."""
        if base_path is None:
            base_path = Path.home() / ".openclaw" / "agents"
        base = Path(base_path)
        if not base.exists():
            return []
        return sorted(base.glob("*/transcripts/*.jsonl"))

    async def migrate(self, transcript_path: str) -> dict:
        """Migrate a single JSONL transcript file to Oracle."""
        self._status["state"] = "running"
        self._status["errors"] = []

        path = Path(transcript_path)
        if not path.exists():
            self._status["state"] = "error"
            self._status["errors"].append(f"Transcript file not found: {transcript_path}")
            return self._status

        # Derive session_id from filename (e.g., "session-abc123.jsonl" → "abc123")
        session_id = path.stem
        self._status["files_total"] = 1

        try:
            events = []
            with open(path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        events.append(event)
                    except json.JSONDecodeError as e:
                        logger.warning("Skipping malformed line %d in %s: %s", line_num, path, e)
                        self._status["errors"].append(f"line {line_num}: {e}")

            self._status["events_total"] = len(events)
            await self._insert_events(session_id, events)
            self._status["files_processed"] = 1
            self._status["state"] = "completed"
        except Exception as e:
            logger.error("Migration failed for %s: %s", path, e)
            self._status["state"] = "error"
            self._status["errors"].append(str(e))

        return self._status

    async def migrate_directory(self, dir_path: str) -> dict:
        """Migrate all JSONL files in a directory."""
        self._status["state"] = "running"
        self._status["errors"] = []

        path = Path(dir_path)
        if not path.exists():
            self._status["state"] = "error"
            self._status["errors"].append(f"Directory not found: {dir_path}")
            return self._status

        files = sorted(path.glob("*.jsonl"))
        self._status["files_total"] = len(files)

        for jsonl_file in files:
            session_id = jsonl_file.stem
            try:
                events = []
                with open(jsonl_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

                self._status["events_total"] += len(events)
                await self._insert_events(session_id, events)
                self._status["files_processed"] += 1
            except Exception as e:
                logger.error("Error migrating %s: %s", jsonl_file, e)
                self._status["errors"].append(f"{jsonl_file.name}: {e}")

        self._status["state"] = "completed"
        return self._status

    async def _insert_events(self, session_id: str, events: list[dict]):
        """Insert events for a session with proper sequence numbering."""
        async with self.pool.acquire() as conn:
            # Check existing max sequence for this session
            cursor = conn.cursor()
            await cursor.execute(
                """
                SELECT COALESCE(MAX(sequence_num), -1)
                FROM ORACLAW_TRANSCRIPTS
                WHERE session_id = :session_id
                """,
                {"session_id": session_id},
            )
            row = await cursor.fetchone()
            next_seq = (row[0] + 1) if row else 0

            for i, event in enumerate(events):
                try:
                    event_id = event.get("id", str(uuid.uuid4()))
                    agent_id = event.get("agent_id", event.get("agentId", "default"))
                    event_type = event.get("event_type", event.get("type", event.get("eventType", "unknown")))

                    # event_data: the full event or a nested data field
                    event_data = event.get("event_data", event.get("data", event.get("eventData")))
                    if event_data is None:
                        known_keys = {"id", "agent_id", "agentId", "event_type", "type",
                                      "eventType", "sequence", "sequenceNum", "sequence_num"}
                        event_data = {k: v for k, v in event.items() if k not in known_keys}

                    event_data_json = json.dumps(event_data) if isinstance(event_data, dict) else str(event_data)
                    seq_num = next_seq + i

                    insert_cursor = conn.cursor()
                    await insert_cursor.execute(
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
                    self._status["events_migrated"] += 1
                except Exception as e:
                    logger.error("Error inserting event %d for session %s: %s", i, session_id, e)
                    self._status["errors"].append(f"event {i} in {session_id}: {e}")

            await conn.commit()
