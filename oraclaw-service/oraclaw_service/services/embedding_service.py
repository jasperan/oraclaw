import asyncio
import logging
from functools import partial

import oracledb

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Embedding service with two modes:

    1. "database" mode: Uses Oracle's in-database ONNX model via VECTOR_EMBEDDING()
    2. "python" mode (fallback): Uses sentence-transformers locally

    If the ONNX model is loaded and working, database mode is preferred.
    Otherwise, falls back to Python-side embeddings.
    """

    def __init__(self, settings):
        self.settings = settings
        self._model = None
        self._mode = None  # "database" or "python"
        self._sync_conn: oracledb.Connection | None = None

    def _create_sync_connection(self) -> oracledb.Connection:
        """Create a synchronous connection for Oracle operations."""
        return oracledb.connect(
            user=self.settings.oracle_user,
            password=self.settings.oracle_password,
            dsn=self.settings.get_dsn(),
        )

    async def initialize(self):
        """Initialize embeddings - try database mode first, fallback to Python."""
        loop = asyncio.get_event_loop()

        # Try database mode first
        if await self.check_onnx_loaded():
            try:
                self._sync_conn = await loop.run_in_executor(
                    None, self._create_sync_connection
                )
                # Test that VECTOR_EMBEDDING actually works
                test_result = await loop.run_in_executor(
                    None, self._test_db_embedding, self._sync_conn
                )
                if test_result:
                    self._mode = "database"
                    logger.info("EmbeddingService initialized in DATABASE mode (model: %s)",
                                self.settings.oracle_onnx_model)
                    return
                else:
                    self._sync_conn.close()
                    self._sync_conn = None
            except Exception as e:
                logger.debug("Database embedding test failed: %s", e)
                if self._sync_conn:
                    self._sync_conn.close()
                    self._sync_conn = None

        # Fallback to Python mode
        logger.info("Falling back to Python-side embeddings (sentence-transformers)")
        try:
            self._model = await loop.run_in_executor(
                None, self._load_sentence_transformer
            )
            self._mode = "python"
            logger.info("EmbeddingService initialized in PYTHON mode (all-MiniLM-L12-v2)")
        except Exception as e:
            logger.error("Failed to initialize any embedding mode: %s", e)
            raise

    def _test_db_embedding(self, conn) -> bool:
        """Test if VECTOR_EMBEDDING works with the loaded model."""
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT VECTOR_EMBEDDING({self.settings.oracle_onnx_model} "
                "USING 'test' AS DATA) FROM DUAL"
            )
            row = cursor.fetchone()
            return row is not None and row[0] is not None
        except Exception:
            return False

    def _load_sentence_transformer(self):
        """Load sentence-transformers model."""
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer("all-MiniLM-L12-v2")

    async def close(self):
        """Release resources."""
        if self._sync_conn:
            try:
                self._sync_conn.close()
            except Exception:
                pass
            self._sync_conn = None
        self._model = None

    async def load_onnx_model(self):
        """Load ONNX model into database (one-time setup)."""
        loop = asyncio.get_event_loop()
        conn = await loop.run_in_executor(None, self._create_sync_connection)
        try:
            from langchain_oracledb import OracleEmbeddings

            await loop.run_in_executor(
                None,
                partial(
                    OracleEmbeddings.load_onnx_model,
                    conn=conn,
                    dir="ORACLAW_ONNX_DIR",
                    onnx_file="all_MiniLM_L12_v2.onnx",
                    model_name=self.settings.oracle_onnx_model,
                ),
            )
            conn.commit()
            logger.info("ONNX model %s loaded into database", self.settings.oracle_onnx_model)
        except Exception as e:
            logger.warning("ONNX model load failed (will use Python fallback): %s", e)
        finally:
            conn.close()

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts."""
        if self._mode == "database":
            return await self._embed_texts_db(texts)
        elif self._mode == "python":
            return await self._embed_texts_python(texts)
        else:
            raise RuntimeError("EmbeddingService not initialized")

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query text."""
        results = await self.embed_texts([text])
        return results[0]

    async def _embed_texts_db(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using Oracle's in-database ONNX model."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._embed_texts_db_sync, texts)

    def _embed_texts_db_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronous database embedding."""
        results = []
        cursor = self._sync_conn.cursor()
        for text in texts:
            cursor.execute(
                f"SELECT VECTOR_EMBEDDING({self.settings.oracle_onnx_model} "
                "USING :text AS DATA) FROM DUAL",
                {"text": text[:512]},  # Truncate to model's max length
            )
            row = cursor.fetchone()
            if row and row[0]:
                results.append(list(row[0]))
            else:
                results.append([0.0] * 384)
        return results

    async def _embed_texts_python(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using sentence-transformers in Python."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._embed_texts_python_sync, texts)

    def _embed_texts_python_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronous Python embedding."""
        embeddings = self._model.encode(texts, show_progress_bar=False)
        return [emb.tolist() for emb in embeddings]

    async def check_onnx_loaded(self) -> bool:
        """Check if ONNX model is loaded in the database."""
        try:
            loop = asyncio.get_event_loop()
            conn = await loop.run_in_executor(None, self._create_sync_connection)
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM USER_MINING_MODELS WHERE MODEL_NAME = :model_name",
                    {"model_name": self.settings.oracle_onnx_model},
                )
                row = cursor.fetchone()
                return row[0] > 0 if row else False
            finally:
                conn.close()
        except Exception as e:
            logger.debug("ONNX model check failed: %s", e)
            return False

    @property
    def mode(self) -> str | None:
        return self._mode

    @property
    def dimensions(self) -> int:
        return 384  # all-MiniLM-L12-v2 produces 384-dim vectors
