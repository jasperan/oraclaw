import array
import json
import logging
import uuid
from datetime import datetime, timezone

import oracledb

logger = logging.getLogger(__name__)


def _to_vector(embedding: list[float]) -> array.array:
    """Convert a Python list of floats to an array.array for Oracle VECTOR binding."""
    return array.array('f', embedding)


async def _read_lob(val):
    """Read a LOB value to string, or return as-is if already a string."""
    if val is None:
        return None
    if isinstance(val, (oracledb.AsyncLOB,)):
        return await val.read()
    if hasattr(val, 'read'):
        result = val.read()
        if hasattr(result, '__await__'):
            return await result
        return result
    return val


class MemoryService:
    def __init__(self, pool, embedding_service, settings):
        self.pool = pool
        self.embedding_service = embedding_service
        self.settings = settings
        self._vector_store = None

    async def initialize(self):
        """Initialize the memory service.

        Note: We use direct SQL with VECTOR_DISTANCE for search rather than
        langchain-oracledb's OracleVS, because OracleVS requires synchronous
        connections while our pool is async. The direct SQL approach gives us
        full control over the query and is more efficient.
        """
        # Verify we can query the chunks table
        async with self.pool.acquire() as conn:
            cursor = conn.cursor()
            await cursor.execute("SELECT COUNT(*) FROM ORACLAW_CHUNKS")
            row = await cursor.fetchone()
            logger.info("MemoryService initialized (existing chunks: %d)", row[0] if row else 0)

    async def search(self, query: str, max_results: int = 6, min_score: float = 0.3,
                     source: str | None = None, hybrid: bool = True) -> list[dict]:
        """Search chunks using vector similarity (with optional source filter)."""
        results = []
        async with self.pool.acquire() as conn:
            # Generate query embedding
            query_embedding = await self.embedding_service.embed_query(query)

            # Build the SQL query
            sql = """
                SELECT chunk_id, path, start_line, end_line, text, source,
                       VECTOR_DISTANCE(embedding, :query_vec, COSINE) AS score
                FROM ORACLAW_CHUNKS
                WHERE embedding IS NOT NULL
            """
            params = {"query_vec": _to_vector(query_embedding), "max_results": max_results}

            if source:
                sql += " AND source = :source"
                params["source"] = source

            sql += " ORDER BY score ASC FETCH FIRST :max_results ROWS ONLY"

            cursor = conn.cursor()
            await cursor.execute(sql, params)
            rows = await cursor.fetchall()

            for row in rows:
                # COSINE distance: lower is more similar, convert to similarity score
                distance = float(row[6])
                similarity = 1.0 - distance
                if similarity < min_score:
                    continue
                text_val = await _read_lob(row[4])
                results.append({
                    "path": row[1],
                    "startLine": row[2],
                    "endLine": row[3],
                    "snippet": text_val[:500] if text_val else "",
                    "score": round(similarity, 4),
                    "source": row[5] or "memory",
                })

        return results

    async def store_chunk(self, chunk: dict) -> dict:
        """Store a single chunk with embedding."""
        async with self.pool.acquire() as conn:
            # Generate embedding for the text
            embedding = await self.embedding_service.embed_query(chunk["text"])

            cursor = conn.cursor()
            await cursor.execute(
                """
                MERGE INTO ORACLAW_CHUNKS c
                USING (SELECT :chunk_id AS chunk_id FROM DUAL) s
                ON (c.chunk_id = s.chunk_id)
                WHEN MATCHED THEN
                    UPDATE SET path = :path, source = :source,
                               start_line = :start_line, end_line = :end_line,
                               hash = :hash, model = :model, text = :text,
                               embedding = :embedding
                WHEN NOT MATCHED THEN
                    INSERT (chunk_id, path, source, start_line, end_line, hash, model, text, embedding)
                    VALUES (:chunk_id, :path, :source, :start_line, :end_line,
                            :hash, :model, :text, :embedding)
                """,
                {
                    "chunk_id": chunk["id"],
                    "path": chunk["path"],
                    "source": chunk.get("source", "memory"),
                    "start_line": chunk["start_line"],
                    "end_line": chunk["end_line"],
                    "hash": chunk.get("hash", ""),
                    "model": chunk.get("model", ""),
                    "text": chunk["text"],
                    "embedding": _to_vector(embedding),
                },
            )
            await conn.commit()

        return {"id": chunk["id"], "stored": True}

    async def store_chunks_batch(self, chunks: list[dict]) -> dict:
        """Batch store multiple chunks."""
        stored = 0
        errors = []
        for chunk in chunks:
            try:
                await self.store_chunk(chunk)
                stored += 1
            except Exception as e:
                errors.append({"id": chunk.get("id", "unknown"), "error": str(e)})
                logger.error("Error storing chunk %s: %s", chunk.get("id"), e)
        return {"stored": stored, "errors": errors}

    async def delete_chunk(self, chunk_id: str) -> dict:
        """Delete a chunk by ID."""
        async with self.pool.acquire() as conn:
            cursor = conn.cursor()
            await cursor.execute(
                "DELETE FROM ORACLAW_CHUNKS WHERE chunk_id = :chunk_id",
                {"chunk_id": chunk_id},
            )
            deleted = cursor.rowcount
            await conn.commit()
        return {"deleted": deleted}

    async def sync_files(self, files: list[dict]) -> dict:
        """Sync file metadata into ORACLAW_FILES."""
        upserted = 0
        async with self.pool.acquire() as conn:
            cursor = conn.cursor()
            for f in files:
                await cursor.execute(
                    """
                    MERGE INTO ORACLAW_FILES fl
                    USING (SELECT :file_id AS file_id FROM DUAL) s
                    ON (fl.file_id = s.file_id)
                    WHEN MATCHED THEN
                        UPDATE SET path = :path, source = :source, hash = :hash,
                                   chunk_count = :chunk_count, updated_at = CURRENT_TIMESTAMP
                    WHEN NOT MATCHED THEN
                        INSERT (file_id, path, source, hash, chunk_count)
                        VALUES (:file_id, :path, :source, :hash, :chunk_count)
                    """,
                    {
                        "file_id": f["file_id"],
                        "path": f["path"],
                        "source": f.get("source", "memory"),
                        "hash": f.get("hash"),
                        "chunk_count": f.get("chunk_count", 0),
                    },
                )
                upserted += 1
            await conn.commit()
        return {"upserted": upserted}

    async def get_status(self) -> dict:
        """Get memory status: chunk count, file count, etc."""
        async with self.pool.acquire() as conn:
            counts = {}
            cursor = conn.cursor()
            for table, key in [
                ("ORACLAW_CHUNKS", "chunk_count"),
                ("ORACLAW_FILES", "file_count"),
                ("ORACLAW_MEMORIES", "memory_count"),
                ("ORACLAW_EMBEDDING_CACHE", "cache_count"),
            ]:
                try:
                    await cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    row = await cursor.fetchone()
                    counts[key] = row[0] if row else 0
                except Exception:
                    counts[key] = 0
        return counts

    # ---- Long-term memory methods ----

    async def remember(self, text: str, agent_id: str = "default",
                       importance: float = 0.7, category: str = "other") -> dict:
        """Store a memory with auto-embedding."""
        memory_id = str(uuid.uuid4())
        embedding = await self.embedding_service.embed_query(text)

        async with self.pool.acquire() as conn:
            cursor = conn.cursor()
            await cursor.execute(
                """
                INSERT INTO ORACLAW_MEMORIES
                    (memory_id, agent_id, text, importance, category, embedding)
                VALUES (:memory_id, :agent_id, :text, :importance, :category, :embedding)
                """,
                {
                    "memory_id": memory_id,
                    "agent_id": agent_id,
                    "text": text,
                    "importance": importance,
                    "category": category,
                    "embedding": _to_vector(embedding),
                },
            )
            await conn.commit()

        return {"memory_id": memory_id, "stored": True}

    async def recall(self, query: str, agent_id: str = "default",
                     max_results: int = 5, min_score: float = 0.3) -> list[dict]:
        """Search memories by similarity."""
        query_embedding = await self.embedding_service.embed_query(query)

        async with self.pool.acquire() as conn:
            cursor = conn.cursor()
            await cursor.execute(
                """
                SELECT memory_id, agent_id, text, importance, category,
                       VECTOR_DISTANCE(embedding, :query_vec, COSINE) AS distance,
                       created_at, accessed_at, access_count
                FROM ORACLAW_MEMORIES
                WHERE agent_id = :agent_id AND embedding IS NOT NULL
                ORDER BY distance ASC
                FETCH FIRST :max_results ROWS ONLY
                """,
                {
                    "query_vec": _to_vector(query_embedding),
                    "agent_id": agent_id,
                    "max_results": max_results,
                },
            )
            rows = await cursor.fetchall()

            results = []
            memory_ids = []
            for row in rows:
                distance = float(row[5])
                similarity = 1.0 - distance
                if similarity < min_score:
                    continue
                text_val = await _read_lob(row[2])
                results.append({
                    "memory_id": row[0],
                    "agent_id": row[1],
                    "text": text_val,
                    "importance": float(row[3]),
                    "category": row[4],
                    "score": round(similarity, 4),
                    "created_at": str(row[6]),
                    "accessed_at": str(row[7]) if row[7] else None,
                    "access_count": row[8],
                })
                memory_ids.append(row[0])

            # Update access timestamps
            if memory_ids:
                placeholders = ", ".join(f":id{i}" for i in range(len(memory_ids)))
                params = {f"id{i}": mid for i, mid in enumerate(memory_ids)}
                update_cursor = conn.cursor()
                await update_cursor.execute(
                    f"""
                    UPDATE ORACLAW_MEMORIES
                    SET accessed_at = CURRENT_TIMESTAMP, access_count = access_count + 1
                    WHERE memory_id IN ({placeholders})
                    """,
                    params,
                )
                await conn.commit()

        return results

    async def forget(self, memory_id: str) -> dict:
        """Delete a memory by ID."""
        async with self.pool.acquire() as conn:
            cursor = conn.cursor()
            await cursor.execute(
                "DELETE FROM ORACLAW_MEMORIES WHERE memory_id = :memory_id",
                {"memory_id": memory_id},
            )
            deleted = cursor.rowcount
            await conn.commit()
        return {"deleted": deleted}

    async def count_memories(self, agent_id: str = "default") -> dict:
        """Count memories for an agent."""
        async with self.pool.acquire() as conn:
            cursor = conn.cursor()
            await cursor.execute(
                "SELECT COUNT(*) FROM ORACLAW_MEMORIES WHERE agent_id = :agent_id",
                {"agent_id": agent_id},
            )
            row = await cursor.fetchone()
        return {"agent_id": agent_id, "count": row[0] if row else 0}
