import hashlib
import json
import logging
import os
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


class SqliteToOracleMigrator:
    """Migrates data from OpenClaw's SQLite memory DB to Oracle."""

    def __init__(self, pool, embedding_service, settings):
        self.pool = pool
        self.embedding_service = embedding_service
        self.settings = settings
        self._status = {
            "state": "idle",
            "files_total": 0,
            "files_migrated": 0,
            "chunks_total": 0,
            "chunks_migrated": 0,
            "cache_total": 0,
            "cache_migrated": 0,
            "errors": [],
        }

    @property
    def status(self) -> dict:
        return dict(self._status)

    def find_sqlite_dbs(self, base_path: str | None = None) -> list[Path]:
        """Find all SQLite memory databases."""
        if base_path is None:
            base_path = os.path.expanduser("~/.openclaw/agents")
        base = Path(base_path)
        if not base.exists():
            return []
        return list(base.glob("*/memory/*.sqlite"))

    async def migrate(self, sqlite_path: str) -> dict:
        """Run full migration from a single SQLite database."""
        self._status["state"] = "running"
        self._status["errors"] = []
        db_path = Path(sqlite_path)

        if not db_path.exists():
            self._status["state"] = "error"
            self._status["errors"].append(f"SQLite database not found: {sqlite_path}")
            return self._status

        try:
            conn_sqlite = sqlite3.connect(str(db_path))
            conn_sqlite.row_factory = sqlite3.Row

            await self._migrate_files(conn_sqlite)
            await self._migrate_chunks(conn_sqlite)
            await self._migrate_embedding_cache(conn_sqlite)

            conn_sqlite.close()
            self._status["state"] = "completed"
        except Exception as e:
            logger.error("Migration failed: %s", e)
            self._status["state"] = "error"
            self._status["errors"].append(str(e))

        return self._status

    async def _migrate_files(self, conn_sqlite: sqlite3.Connection):
        """Migrate files table to ORACLAW_FILES."""
        try:
            cursor = conn_sqlite.execute("SELECT * FROM files")
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            logger.info("No 'files' table found in SQLite DB, skipping")
            return

        self._status["files_total"] = len(rows)

        async with self.pool.acquire() as conn_ora:
            for row in rows:
                try:
                    file_id = row["id"] if "id" in row.keys() else row["file_id"]
                    path = row["path"] if "path" in row.keys() else ""
                    source = row.get("source", "memory") if hasattr(row, "get") else "memory"
                    file_hash = row["hash"] if "hash" in row.keys() else None
                    chunk_count = row["chunk_count"] if "chunk_count" in row.keys() else 0

                    await conn_ora.execute(
                        """
                        MERGE INTO ORACLAW_FILES f
                        USING (SELECT :file_id AS file_id FROM DUAL) s
                        ON (f.file_id = s.file_id)
                        WHEN MATCHED THEN
                            UPDATE SET path = :path, source = :source, hash = :hash,
                                       chunk_count = :chunk_count, updated_at = CURRENT_TIMESTAMP
                        WHEN NOT MATCHED THEN
                            INSERT (file_id, path, source, hash, chunk_count)
                            VALUES (:file_id, :path, :source, :hash, :chunk_count)
                        """,
                        {
                            "file_id": file_id,
                            "path": path,
                            "source": source,
                            "hash": file_hash,
                            "chunk_count": chunk_count,
                        },
                    )
                    self._status["files_migrated"] += 1
                except Exception as e:
                    logger.error("Error migrating file %s: %s", row, e)
                    self._status["errors"].append(f"file: {e}")

            await conn_ora.commit()

    async def _migrate_chunks(self, conn_sqlite: sqlite3.Connection):
        """Migrate chunks table to ORACLAW_CHUNKS, re-embedding with ONNX."""
        try:
            cursor = conn_sqlite.execute("SELECT * FROM chunks")
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            logger.info("No 'chunks' table found in SQLite DB, skipping")
            return

        self._status["chunks_total"] = len(rows)

        # Process in batches for embedding
        batch_size = 50
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            texts = []
            batch_data = []

            for row in batch:
                chunk_id = row["id"] if "id" in row.keys() else row["chunk_id"]
                text = row["text"] if "text" in row.keys() else ""
                path = row["path"] if "path" in row.keys() else ""
                file_id = row.get("file_id", None) if hasattr(row, "get") else None
                source = row.get("source", "memory") if hasattr(row, "get") else "memory"
                start_line = row["start_line"] if "start_line" in row.keys() else 0
                end_line = row["end_line"] if "end_line" in row.keys() else 0
                chunk_hash = row["hash"] if "hash" in row.keys() else ""
                model = self.settings.oracle_onnx_model

                texts.append(text)
                batch_data.append({
                    "chunk_id": chunk_id,
                    "file_id": file_id,
                    "path": path,
                    "source": source,
                    "start_line": start_line,
                    "end_line": end_line,
                    "hash": chunk_hash,
                    "model": model,
                    "text": text,
                })

            # Re-embed with ONNX (dimensions differ: 1536 OpenAI → 384 ONNX)
            try:
                embeddings = await self.embedding_service.embed_texts(texts)
            except Exception as e:
                logger.error("Embedding batch failed: %s", e)
                self._status["errors"].append(f"embedding batch {i}: {e}")
                continue

            async with self.pool.acquire() as conn_ora:
                for data, embedding in zip(batch_data, embeddings):
                    try:
                        await conn_ora.execute(
                            """
                            MERGE INTO ORACLAW_CHUNKS c
                            USING (SELECT :chunk_id AS chunk_id FROM DUAL) s
                            ON (c.chunk_id = s.chunk_id)
                            WHEN MATCHED THEN
                                UPDATE SET file_id = :file_id, path = :path, source = :source,
                                           start_line = :start_line, end_line = :end_line,
                                           hash = :hash, model = :model, text = :text,
                                           embedding = :embedding
                            WHEN NOT MATCHED THEN
                                INSERT (chunk_id, file_id, path, source, start_line, end_line,
                                        hash, model, text, embedding)
                                VALUES (:chunk_id, :file_id, :path, :source, :start_line,
                                        :end_line, :hash, :model, :text, :embedding)
                            """,
                            {
                                **data,
                                "embedding": str(embedding),
                            },
                        )
                        self._status["chunks_migrated"] += 1
                    except Exception as e:
                        logger.error("Error migrating chunk %s: %s", data["chunk_id"], e)
                        self._status["errors"].append(f"chunk {data['chunk_id']}: {e}")

                await conn_ora.commit()

    async def _migrate_embedding_cache(self, conn_sqlite: sqlite3.Connection):
        """Migrate embedding_cache table to ORACLAW_EMBEDDING_CACHE."""
        try:
            cursor = conn_sqlite.execute("SELECT * FROM embedding_cache")
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            logger.info("No 'embedding_cache' table found in SQLite DB, skipping")
            return

        self._status["cache_total"] = len(rows)

        async with self.pool.acquire() as conn_ora:
            for row in rows:
                try:
                    cache_key = row["id"] if "id" in row.keys() else row["cache_key"]
                    text_hash = row["text_hash"] if "text_hash" in row.keys() else ""
                    model = row["model"] if "model" in row.keys() else ""
                    embedding_raw = row["embedding"] if "embedding" in row.keys() else None

                    # Parse embedding if stored as JSON string
                    embedding_str = None
                    if embedding_raw:
                        if isinstance(embedding_raw, str):
                            try:
                                embedding_str = embedding_raw
                            except Exception:
                                embedding_str = None
                        elif isinstance(embedding_raw, bytes):
                            embedding_str = embedding_raw.decode("utf-8", errors="replace")

                    await conn_ora.execute(
                        """
                        MERGE INTO ORACLAW_EMBEDDING_CACHE ec
                        USING (SELECT :cache_key AS cache_key FROM DUAL) s
                        ON (ec.cache_key = s.cache_key)
                        WHEN MATCHED THEN
                            UPDATE SET text_hash = :text_hash, model = :model,
                                       embedding = :embedding
                        WHEN NOT MATCHED THEN
                            INSERT (cache_key, text_hash, model, embedding)
                            VALUES (:cache_key, :text_hash, :model, :embedding)
                        """,
                        {
                            "cache_key": cache_key,
                            "text_hash": text_hash,
                            "model": model,
                            "embedding": embedding_str,
                        },
                    )
                    self._status["cache_migrated"] += 1
                except Exception as e:
                    logger.error("Error migrating cache entry: %s", e)
                    self._status["errors"].append(f"cache: {e}")

            await conn_ora.commit()
