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


def test_is_adb_property():
    """is_adb is True only in adb mode."""
    s_free = OraclawSettings(oracle_password="x")
    assert s_free.is_adb is False

    s_adb = OraclawSettings(oracle_mode="adb", oracle_password="x")
    assert s_adb.is_adb is True


def test_uses_wallet_property():
    """uses_wallet is True only in adb mode with wallet_path."""
    # FreePDB with wallet path -> still False
    s = OraclawSettings(oracle_password="x", oracle_wallet_path="/some/path")
    assert s.uses_wallet is False

    # ADB without wallet -> False
    s = OraclawSettings(oracle_mode="adb", oracle_password="x", oracle_dsn="(desc...)")
    assert s.uses_wallet is False

    # ADB with wallet -> True
    s = OraclawSettings(
        oracle_mode="adb", oracle_password="x",
        oracle_dsn="(desc...)", oracle_wallet_path="/wallet",
    )
    assert s.uses_wallet is True


def test_uses_tls_property():
    """uses_tls is True for wallet-less ADB with DSN descriptor."""
    # ADB with DSN, no wallet -> TLS
    s = OraclawSettings(
        oracle_mode="adb", oracle_password="x",
        oracle_dsn="(description= (address=(protocol=tcps)...))",
    )
    assert s.uses_tls is True

    # ADB with DSN + wallet -> mTLS, not TLS
    s = OraclawSettings(
        oracle_mode="adb", oracle_password="x",
        oracle_dsn="(description=...)", oracle_wallet_path="/wallet",
    )
    assert s.uses_tls is False


def test_dsn_adb_full_descriptor():
    """ADB mode with oracle-ai-developer-hub style DSN descriptor."""
    long_dsn = (
        "(description= (retry_count=20)(retry_delay=3)"
        "(address=(protocol=tcps)(port=1522)"
        "(host=adb.us-phoenix-1.oraclecloud.com))"
        "(connect_data=(service_name=g2f4dc3e5463897_mern_tpurgent.adb.oraclecloud.com))"
        "(security=(ssl_server_dn_match=yes)))"
    )
    s = OraclawSettings(
        oracle_mode="adb",
        oracle_user="ADMIN",
        oracle_password="Welcome12345*",
        oracle_dsn=long_dsn,
    )
    assert s.get_dsn() == long_dsn
    assert s.is_adb is True
    assert s.uses_tls is True
    assert s.uses_wallet is False
