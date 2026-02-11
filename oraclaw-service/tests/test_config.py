"""Tests for OraclawSettings configuration."""

from oraclaw_service.config import OraclawSettings


def test_default_settings():
    """Settings have sensible defaults."""
    s = OraclawSettings(oracle_password="test")
    assert s.oracle_mode == "freepdb"
    assert s.oracle_user == "oraclaw"
    assert s.oracle_host == "localhost"
    assert s.oracle_port == 1521
    assert s.oracle_service == "FREEPDB1"
    assert s.oracle_pool_min == 2
    assert s.oracle_pool_max == 10
    assert s.oracle_onnx_model == "ALL_MINILM_L12_V2"
    assert s.oraclaw_service_port == 8100
    assert s.auto_init is False


def test_dsn_freepdb():
    """FreePDB DSN is constructed from host:port/service."""
    s = OraclawSettings(oracle_password="x", oracle_host="db.example.com", oracle_port=1522, oracle_service="PDB1")
    assert s.get_dsn() == "db.example.com:1522/PDB1"


def test_dsn_adb():
    """ADB mode uses oracle_dsn if provided."""
    s = OraclawSettings(
        oracle_mode="adb",
        oracle_password="x",
        oracle_dsn="(description=(address=...))",
    )
    assert s.get_dsn() == "(description=(address=...))"


def test_dsn_adb_fallback():
    """ADB mode without oracle_dsn falls back to host:port/service."""
    s = OraclawSettings(oracle_mode="adb", oracle_password="x")
    dsn = s.get_dsn()
    assert "localhost" in dsn
    assert "1521" in dsn
