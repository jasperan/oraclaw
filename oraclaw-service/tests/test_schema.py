"""Tests for the database schema module."""

from oraclaw_service.db.schema import (
    SCHEMA_VERSION,
    ALL_TABLES,
    DDL_STATEMENTS,
    INDEX_STATEMENTS,
    VECTOR_INDEX_STATEMENTS,
    _extract_table_name,
    _extract_index_name,
)


def test_schema_version():
    """Schema version follows semver."""
    assert SCHEMA_VERSION == "0.1.0"
    parts = SCHEMA_VERSION.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


def test_all_tables_count():
    """All 8 tables are defined."""
    assert len(ALL_TABLES) == 8
    expected = {
        "ORACLAW_META", "ORACLAW_FILES", "ORACLAW_CHUNKS",
        "ORACLAW_MEMORIES", "ORACLAW_EMBEDDING_CACHE",
        "ORACLAW_SESSIONS", "ORACLAW_TRANSCRIPTS", "ORACLAW_CONFIG",
    }
    assert set(ALL_TABLES) == expected


def test_ddl_count_matches_tables():
    """Each table has a DDL statement."""
    assert len(DDL_STATEMENTS) == len(ALL_TABLES)


def test_extract_table_name():
    """Table name extraction from DDL works."""
    ddl = "CREATE TABLE ORACLAW_TEST (\n    id NUMBER PRIMARY KEY\n)"
    assert _extract_table_name(ddl) == "ORACLAW_TEST"


def test_extract_index_name():
    """Index name extraction from DDL works."""
    ddl = "CREATE INDEX IDX_TEST ON ORACLAW_TEST(col1)"
    assert _extract_index_name(ddl) == "IDX_TEST"


def test_vector_index_statements():
    """Vector indexes are defined for chunks and memories."""
    assert len(VECTOR_INDEX_STATEMENTS) == 2
    # Both should reference COSINE distance
    for stmt in VECTOR_INDEX_STATEMENTS:
        assert "COSINE" in stmt.upper()
        assert "VECTOR INDEX" in stmt.upper()


def test_all_ddl_create_oraclaw_tables():
    """All DDL statements create ORACLAW_ prefixed tables."""
    for ddl in DDL_STATEMENTS:
        table = _extract_table_name(ddl)
        assert table.startswith("ORACLAW_"), f"Table {table} doesn't have ORACLAW_ prefix"
