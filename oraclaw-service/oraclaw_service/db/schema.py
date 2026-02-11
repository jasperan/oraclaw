import logging

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "0.1.0"

DDL_STATEMENTS = [
    # ---- ORACLAW_META ----
    """
    CREATE TABLE ORACLAW_META (
        meta_key   VARCHAR2(100)  PRIMARY KEY,
        meta_value VARCHAR2(4000) NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # ---- ORACLAW_FILES ----
    """
    CREATE TABLE ORACLAW_FILES (
        file_id    VARCHAR2(200)  PRIMARY KEY,
        path       VARCHAR2(4000) NOT NULL,
        source     VARCHAR2(50)   DEFAULT 'memory',
        hash       VARCHAR2(128),
        chunk_count NUMBER(10)     DEFAULT 0,
        indexed_at TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP      DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # ---- ORACLAW_CHUNKS ----
    """
    CREATE TABLE ORACLAW_CHUNKS (
        chunk_id   VARCHAR2(200)  PRIMARY KEY,
        file_id    VARCHAR2(200)  REFERENCES ORACLAW_FILES(file_id) ON DELETE CASCADE,
        path       VARCHAR2(4000) NOT NULL,
        source     VARCHAR2(50)   DEFAULT 'memory',
        start_line NUMBER(10)     NOT NULL,
        end_line   NUMBER(10)     NOT NULL,
        hash       VARCHAR2(128),
        model      VARCHAR2(200),
        text       CLOB,
        embedding  VECTOR,
        created_at TIMESTAMP      DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # ---- ORACLAW_MEMORIES ----
    """
    CREATE TABLE ORACLAW_MEMORIES (
        memory_id  VARCHAR2(200)  PRIMARY KEY,
        agent_id   VARCHAR2(100)  DEFAULT 'default',
        text       CLOB           NOT NULL,
        importance NUMBER(3,2)    DEFAULT 0.7,
        category   VARCHAR2(100)  DEFAULT 'other',
        embedding  VECTOR,
        created_at TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
        accessed_at TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
        access_count NUMBER(10)   DEFAULT 0
    )
    """,
    # ---- ORACLAW_EMBEDDING_CACHE ----
    """
    CREATE TABLE ORACLAW_EMBEDDING_CACHE (
        cache_key  VARCHAR2(200)  PRIMARY KEY,
        text_hash  VARCHAR2(128)  NOT NULL,
        model      VARCHAR2(200)  NOT NULL,
        embedding  VECTOR,
        created_at TIMESTAMP      DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # ---- ORACLAW_SESSIONS ----
    """
    CREATE TABLE ORACLAW_SESSIONS (
        session_key  VARCHAR2(200)  PRIMARY KEY,
        session_id   VARCHAR2(200)  NOT NULL,
        agent_id     VARCHAR2(100)  DEFAULT 'default',
        updated_at   NUMBER(20)     NOT NULL,
        session_data CLOB,
        channel      VARCHAR2(100),
        label        VARCHAR2(500)
    )
    """,
    # ---- ORACLAW_TRANSCRIPTS ----
    """
    CREATE TABLE ORACLAW_TRANSCRIPTS (
        id           VARCHAR2(200)  PRIMARY KEY,
        session_id   VARCHAR2(200)  NOT NULL,
        agent_id     VARCHAR2(100)  DEFAULT 'default',
        sequence_num NUMBER(10)     NOT NULL,
        event_type   VARCHAR2(100)  NOT NULL,
        event_data   CLOB,
        created_at   TIMESTAMP      DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # ---- ORACLAW_CONFIG ----
    """
    CREATE TABLE ORACLAW_CONFIG (
        config_key   VARCHAR2(200)  PRIMARY KEY,
        config_value CLOB,
        description  VARCHAR2(1000),
        updated_at   TIMESTAMP      DEFAULT CURRENT_TIMESTAMP
    )
    """,
]

INDEX_STATEMENTS = [
    "CREATE INDEX IDX_CHUNKS_FILE ON ORACLAW_CHUNKS(file_id)",
    "CREATE INDEX IDX_CHUNKS_PATH ON ORACLAW_CHUNKS(path)",
    "CREATE INDEX IDX_MEMORIES_AGENT ON ORACLAW_MEMORIES(agent_id)",
    "CREATE INDEX IDX_SESSIONS_AGENT ON ORACLAW_SESSIONS(agent_id)",
    "CREATE INDEX IDX_TRANSCRIPTS_SESSION ON ORACLAW_TRANSCRIPTS(session_id, sequence_num)",
    "CREATE INDEX IDX_CACHE_HASH ON ORACLAW_EMBEDDING_CACHE(text_hash, model)",
]

VECTOR_INDEX_STATEMENTS = [
    """
    CREATE VECTOR INDEX IDX_CHUNKS_VEC ON ORACLAW_CHUNKS(embedding)
    ORGANIZATION NEIGHBOR PARTITIONS
    DISTANCE COSINE
    WITH TARGET ACCURACY 95
    """,
    """
    CREATE VECTOR INDEX IDX_MEMORIES_VEC ON ORACLAW_MEMORIES(embedding)
    ORGANIZATION NEIGHBOR PARTITIONS
    DISTANCE COSINE
    WITH TARGET ACCURACY 95
    """,
]

ALL_TABLES = [
    "ORACLAW_META",
    "ORACLAW_FILES",
    "ORACLAW_CHUNKS",
    "ORACLAW_MEMORIES",
    "ORACLAW_EMBEDDING_CACHE",
    "ORACLAW_SESSIONS",
    "ORACLAW_TRANSCRIPTS",
    "ORACLAW_CONFIG",
]


async def init_schema(pool) -> dict:
    """Create all tables and indexes idempotently. Returns status dict."""
    tables_created = []
    indexes_created = []
    errors = []

    async with pool.acquire() as conn:
        # Create tables
        for ddl in DDL_STATEMENTS:
            table_name = _extract_table_name(ddl)
            try:
                cursor = conn.cursor()
                await cursor.execute(ddl)
                tables_created.append(table_name)
                logger.info("Created table %s", table_name)
            except Exception as e:
                if "ORA-00955" in str(e):
                    logger.debug("Table %s already exists", table_name)
                else:
                    logger.error("Error creating table %s: %s", table_name, e)
                    errors.append({"table": table_name, "error": str(e)})

        # Create regular indexes
        for idx_ddl in INDEX_STATEMENTS:
            idx_name = _extract_index_name(idx_ddl)
            try:
                cursor = conn.cursor()
                await cursor.execute(idx_ddl)
                indexes_created.append(idx_name)
                logger.info("Created index %s", idx_name)
            except Exception as e:
                if "ORA-00955" in str(e) or "ORA-01408" in str(e):
                    logger.debug("Index %s already exists", idx_name)
                else:
                    logger.error("Error creating index %s: %s", idx_name, e)
                    errors.append({"index": idx_name, "error": str(e)})

        # Create vector indexes
        for vidx_ddl in VECTOR_INDEX_STATEMENTS:
            idx_name = _extract_index_name(vidx_ddl)
            try:
                cursor = conn.cursor()
                await cursor.execute(vidx_ddl)
                indexes_created.append(idx_name)
                logger.info("Created vector index %s", idx_name)
            except Exception as e:
                if "ORA-00955" in str(e) or "ORA-01408" in str(e):
                    logger.debug("Vector index %s already exists", idx_name)
                else:
                    logger.warning("Vector index %s error (may need manual setup): %s", idx_name, e)
                    errors.append({"index": idx_name, "error": str(e)})

        # Set schema version
        await set_schema_version(pool, SCHEMA_VERSION)

        await conn.commit()

    return {
        "tables_created": tables_created,
        "indexes_created": indexes_created,
        "errors": errors,
    }


async def check_tables_exist(pool) -> dict[str, bool]:
    """Check which tables exist."""
    result = {}
    async with pool.acquire() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            "SELECT table_name FROM user_tables WHERE table_name LIKE 'ORACLAW_%'"
        )
        rows = await cursor.fetchall()
        existing = {row[0] for row in rows}
        for table in ALL_TABLES:
            result[table] = table in existing
    return result


async def get_schema_version(pool) -> str:
    """Get current schema version from ORACLAW_META."""
    try:
        async with pool.acquire() as conn:
            cursor = conn.cursor()
            await cursor.execute(
                "SELECT meta_value FROM ORACLAW_META WHERE meta_key = 'schema_version'"
            )
            row = await cursor.fetchone()
            return row[0] if row else "unknown"
    except Exception:
        return "unknown"


async def set_schema_version(pool, version: str):
    """Set schema version in ORACLAW_META."""
    async with pool.acquire() as conn:
        cursor = conn.cursor()
        await cursor.execute(
            """
            MERGE INTO ORACLAW_META m
            USING (SELECT 'schema_version' AS meta_key FROM DUAL) s
            ON (m.meta_key = s.meta_key)
            WHEN MATCHED THEN
                UPDATE SET meta_value = :val, updated_at = CURRENT_TIMESTAMP
            WHEN NOT MATCHED THEN
                INSERT (meta_key, meta_value) VALUES ('schema_version', :val)
            """,
            {"val": version},
        )
        await conn.commit()


def _extract_table_name(ddl: str) -> str:
    """Extract table name from CREATE TABLE statement."""
    parts = ddl.strip().split()
    for i, p in enumerate(parts):
        if p.upper() == "TABLE" and i + 1 < len(parts):
            return parts[i + 1].strip("(").upper()
    return "UNKNOWN"


def _extract_index_name(ddl: str) -> str:
    """Extract index name from CREATE INDEX statement."""
    parts = ddl.strip().split()
    for i, p in enumerate(parts):
        if p.upper() == "INDEX" and i + 1 < len(parts):
            name = parts[i + 1].strip().upper()
            if name == "IF":
                continue
            return name
    return "UNKNOWN"
