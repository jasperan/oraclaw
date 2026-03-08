#!/usr/bin/env python3
"""
OracLaw Live Oracle Database Monitor
=====================================
Real-time monitoring dashboard for Oracle FreePDB tables.
Shows row counts, sample data, vector index stats, and highlights
Oracle AI Database capabilities.

Usage:
    python scripts/oracle_monitor.py                  # One-shot report
    python scripts/oracle_monitor.py --watch          # Live refresh every 5s
    python scripts/oracle_monitor.py --watch --interval 2  # Custom interval
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

import oracledb

# Default connection settings
ORACLE_USER = os.environ.get("ORACLE_USER", "oraclaw")
ORACLE_PASSWORD = os.environ.get("ORACLE_PASSWORD", "OracLaw2024")
ORACLE_HOST = os.environ.get("ORACLE_HOST", "localhost")
ORACLE_PORT = int(os.environ.get("ORACLE_PORT", 1521))
ORACLE_SERVICE = os.environ.get("ORACLE_SERVICE", "FREEPDB1")

ORACLAW_TABLES = [
    "ORACLAW_META",
    "ORACLAW_FILES",
    "ORACLAW_CHUNKS",
    "ORACLAW_MEMORIES",
    "ORACLAW_EMBEDDING_CACHE",
    "ORACLAW_SESSIONS",
    "ORACLAW_TRANSCRIPTS",
    "ORACLAW_CONFIG",
]

ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[91m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "blue": "\033[94m",
    "magenta": "\033[95m",
    "cyan": "\033[96m",
    "white": "\033[97m",
    "bg_blue": "\033[44m",
    "bg_green": "\033[42m",
    "underline": "\033[4m",
}


def c(text, *styles):
    """Apply ANSI color/style to text."""
    prefix = "".join(ANSI.get(s, "") for s in styles)
    return f"{prefix}{text}{ANSI['reset']}"


def get_connection():
    dsn = f"{ORACLE_HOST}:{ORACLE_PORT}/{ORACLE_SERVICE}"
    return oracledb.connect(user=ORACLE_USER, password=ORACLE_PASSWORD, dsn=dsn)


def get_table_counts(conn):
    """Get row counts for all OracLaw tables."""
    counts = {}
    cursor = conn.cursor()
    for table in ORACLAW_TABLES:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            row = cursor.fetchone()
            counts[table] = row[0] if row else 0
        except Exception as e:
            counts[table] = f"ERROR: {e}"
    return counts


def get_table_size_bytes(conn):
    """Get table sizes in bytes."""
    sizes = {}
    cursor = conn.cursor()
    for table in ORACLAW_TABLES:
        try:
            cursor.execute(
                "SELECT NVL(SUM(bytes), 0) FROM user_segments WHERE segment_name = :t",
                {"t": table},
            )
            row = cursor.fetchone()
            sizes[table] = row[0] if row else 0
        except Exception:
            sizes[table] = 0
    return sizes


def format_bytes(b):
    """Human-readable byte size."""
    if b == 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(b) < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def get_vector_index_stats(conn):
    """Get Oracle Vector Index statistics."""
    cursor = conn.cursor()
    indexes = []
    try:
        cursor.execute(
            """
            SELECT index_name, table_name, status
            FROM user_indexes
            WHERE index_type LIKE '%VECTOR%' OR index_name LIKE '%VEC%'
            """
        )
        for row in cursor.fetchall():
            indexes.append({
                "name": row[0],
                "table": row[1],
                "status": row[2],
            })
    except Exception:
        pass
    return indexes


def get_onnx_models(conn):
    """Get loaded ONNX models."""
    cursor = conn.cursor()
    models = []
    try:
        cursor.execute(
            "SELECT model_name, mining_function, algorithm FROM user_mining_models"
        )
        for row in cursor.fetchall():
            models.append({
                "name": row[0],
                "function": row[1],
                "algorithm": row[2],
            })
    except Exception:
        pass
    return models


def get_sample_memories(conn, limit=3):
    """Get recent memories with metadata."""
    cursor = conn.cursor()
    memories = []
    try:
        cursor.execute(
            """
            SELECT memory_id, agent_id, text, importance, category,
                   created_at, access_count
            FROM ORACLAW_MEMORIES
            ORDER BY created_at DESC
            FETCH FIRST :lim ROWS ONLY
            """,
            {"lim": limit},
        )
        for row in cursor.fetchall():
            text_val = row[2]
            if hasattr(text_val, "read"):
                text_val = text_val.read()
            memories.append({
                "id": row[0][:12] + "...",
                "agent": row[1],
                "text": (text_val[:80] + "...") if text_val and len(text_val) > 80 else text_val,
                "importance": row[3],
                "category": row[4],
                "created": str(row[5])[:19],
                "accesses": row[6],
            })
    except Exception as e:
        memories.append({"error": str(e)})
    return memories


def get_sample_chunks(conn, limit=3):
    """Get recent code chunks."""
    cursor = conn.cursor()
    chunks = []
    try:
        cursor.execute(
            """
            SELECT chunk_id, path, source, start_line, end_line,
                   CASE WHEN embedding IS NOT NULL THEN 'YES' ELSE 'NO' END as has_vec
            FROM ORACLAW_CHUNKS
            ORDER BY created_at DESC
            FETCH FIRST :lim ROWS ONLY
            """,
            {"lim": limit},
        )
        for row in cursor.fetchall():
            chunks.append({
                "id": row[0][:20],
                "path": row[1],
                "source": row[2],
                "lines": f"{row[3]}-{row[4]}",
                "has_vector": row[5],
            })
    except Exception as e:
        chunks.append({"error": str(e)})
    return chunks


def get_sample_sessions(conn, limit=3):
    """Get recent sessions."""
    cursor = conn.cursor()
    sessions = []
    try:
        cursor.execute(
            """
            SELECT session_key, session_id, agent_id, channel, label
            FROM ORACLAW_SESSIONS
            ORDER BY updated_at DESC
            FETCH FIRST :lim ROWS ONLY
            """,
            {"lim": limit},
        )
        for row in cursor.fetchall():
            sessions.append({
                "key": row[0],
                "session_id": row[1][:20],
                "agent": row[2],
                "channel": row[3] or "-",
                "label": row[4] or "-",
            })
    except Exception as e:
        sessions.append({"error": str(e)})
    return sessions


def get_sample_transcripts(conn, limit=5):
    """Get recent transcript events."""
    cursor = conn.cursor()
    events = []
    try:
        cursor.execute(
            """
            SELECT id, session_id, event_type, event_data, created_at
            FROM ORACLAW_TRANSCRIPTS
            ORDER BY created_at DESC
            FETCH FIRST :lim ROWS ONLY
            """,
            {"lim": limit},
        )
        for row in cursor.fetchall():
            data = row[3]
            if hasattr(data, "read"):
                data = data.read()
            try:
                parsed = json.loads(data) if isinstance(data, str) else data
                content = parsed.get("content", "")[:60]
            except Exception:
                content = str(data)[:60] if data else ""
            events.append({
                "session": row[1][:16],
                "type": row[2],
                "content": content + ("..." if len(content) >= 60 else ""),
                "time": str(row[4])[:19],
            })
    except Exception as e:
        events.append({"error": str(e)})
    return events


def get_db_version(conn):
    """Get Oracle DB version."""
    cursor = conn.cursor()
    cursor.execute("SELECT banner FROM v$version WHERE ROWNUM = 1")
    row = cursor.fetchone()
    return row[0] if row else "Unknown"


def get_schema_version(conn):
    """Get OracLaw schema version."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT meta_value FROM ORACLAW_META WHERE meta_key = 'schema_version'"
        )
        row = cursor.fetchone()
        return row[0] if row else "not set"
    except Exception:
        return "unknown"


def render_dashboard(conn, previous_counts=None):
    """Render the full monitoring dashboard."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    counts = get_table_counts(conn)
    sizes = get_table_size_bytes(conn)
    vec_indexes = get_vector_index_stats(conn)
    onnx_models = get_onnx_models(conn)
    schema_ver = get_schema_version(conn)

    lines = []
    w = 90  # dashboard width

    # Header
    lines.append("")
    lines.append(c("=" * w, "cyan", "bold"))
    lines.append(c("  ORACLAW - Oracle AI Database Live Monitor", "cyan", "bold"))
    lines.append(c(f"  {now}  |  Schema v{schema_ver}", "dim"))
    lines.append(c("=" * w, "cyan", "bold"))

    # ── Table Overview ──
    lines.append("")
    lines.append(c("  TABLE OVERVIEW", "yellow", "bold"))
    lines.append(c("  " + "-" * (w - 4), "dim"))
    lines.append(
        c("  {:<30} {:>10} {:>12} {:>10}".format("Table", "Rows", "Size", "Delta"), "bold")
    )
    lines.append(c("  " + "-" * (w - 4), "dim"))

    total_rows = 0
    total_size = 0
    for table in ORACLAW_TABLES:
        row_count = counts.get(table, 0)
        size = sizes.get(table, 0)
        total_rows += row_count if isinstance(row_count, int) else 0
        total_size += size

        # Delta since last check
        delta = ""
        if previous_counts and table in previous_counts:
            diff = row_count - previous_counts[table] if isinstance(row_count, int) and isinstance(previous_counts[table], int) else 0
            if diff > 0:
                delta = c(f"+{diff}", "green")
            elif diff < 0:
                delta = c(str(diff), "red")

        row_str = str(row_count) if isinstance(row_count, int) else c(str(row_count), "red")
        color = "green" if isinstance(row_count, int) and row_count > 0 else "dim"
        lines.append(
            f"  {c(table, color):<50} {row_str:>10} {format_bytes(size):>12} {delta:>10}"
        )

    lines.append(c("  " + "-" * (w - 4), "dim"))
    lines.append(
        f"  {c('TOTAL', 'bold'):<50} {c(str(total_rows), 'bold'):>20} {c(format_bytes(total_size), 'bold'):>12}"
    )

    # ── Vector Indexes ──
    lines.append("")
    lines.append(c("  ORACLE AI VECTOR INDEXES", "magenta", "bold"))
    lines.append(c("  " + "-" * (w - 4), "dim"))
    if vec_indexes:
        for idx in vec_indexes:
            status_color = "green" if idx["status"] == "VALID" else "red"
            lines.append(
                f"  {c(idx['name'], 'cyan'):<50} Table: {idx['table']:<25} [{c(idx['status'], status_color)}]"
            )
    else:
        lines.append(c("  No vector indexes found", "dim"))

    # ── ONNX Models ──
    lines.append("")
    lines.append(c("  IN-DATABASE ONNX MODELS", "magenta", "bold"))
    lines.append(c("  " + "-" * (w - 4), "dim"))
    if onnx_models:
        for model in onnx_models:
            lines.append(
                f"  {c(model['name'], 'green', 'bold'):<40} Function: {model['function']:<20} Algorithm: {model['algorithm']}"
            )
    else:
        lines.append(c("  No ONNX models loaded (using Python-side embeddings)", "yellow"))

    # ── Sample Memories ──
    lines.append("")
    lines.append(c("  RECENT MEMORIES (ORACLAW_MEMORIES)", "blue", "bold"))
    lines.append(c("  " + "-" * (w - 4), "dim"))
    memories = get_sample_memories(conn)
    for mem in memories:
        if "error" in mem:
            lines.append(c(f"  Error: {mem['error']}", "red"))
        else:
            lines.append(
                f"  [{c(mem['category'], 'cyan')}] {c(mem['text'], 'white')} "
                f"(imp={mem['importance']}, accessed={mem['accesses']}x)"
            )

    # ── Sample Chunks ──
    lines.append("")
    lines.append(c("  RECENT CODE CHUNKS (ORACLAW_CHUNKS)", "blue", "bold"))
    lines.append(c("  " + "-" * (w - 4), "dim"))
    chunks = get_sample_chunks(conn)
    for chunk in chunks:
        if "error" in chunk:
            lines.append(c(f"  Error: {chunk['error']}", "red"))
        else:
            vec_icon = c("VEC", "green", "bold") if chunk["has_vector"] == "YES" else c("---", "dim")
            lines.append(
                f"  [{vec_icon}] {c(chunk['path'], 'cyan')} L{chunk['lines']} ({chunk['source']})"
            )

    # ── Sample Sessions ──
    lines.append("")
    lines.append(c("  ACTIVE SESSIONS (ORACLAW_SESSIONS)", "blue", "bold"))
    lines.append(c("  " + "-" * (w - 4), "dim"))
    sessions = get_sample_sessions(conn)
    for sess in sessions:
        if "error" in sess:
            lines.append(c(f"  Error: {sess['error']}", "red"))
        else:
            lines.append(
                f"  {c(sess['key'], 'cyan')} | {sess['channel']:>4} | {c(sess['label'], 'white')}"
            )

    # ── Recent Transcript Events ──
    lines.append("")
    lines.append(c("  RECENT TRANSCRIPT EVENTS (ORACLAW_TRANSCRIPTS)", "blue", "bold"))
    lines.append(c("  " + "-" * (w - 4), "dim"))
    events = get_sample_transcripts(conn)
    for evt in events:
        if "error" in evt:
            lines.append(c(f"  Error: {evt['error']}", "red"))
        else:
            type_color = "green" if "user" in evt["type"] else "yellow"
            lines.append(
                f"  {c(evt['type'], type_color):<30} {evt['content']}"
            )

    # ── Oracle AI Benefits ──
    lines.append("")
    lines.append(c("  ORACLE AI DATABASE BENEFITS", "green", "bold"))
    lines.append(c("  " + "-" * (w - 4), "dim"))
    benefits = [
        "VECTOR data type native in Oracle - no external vector DB needed",
        "VECTOR_DISTANCE() with COSINE/DOT/EUCLIDEAN for similarity search",
        "IVF_FLAT vector indexes for fast approximate nearest neighbor (ANN)",
        "In-database ONNX models via VECTOR_EMBEDDING() - zero data movement",
        "ACID transactions for vectors + relational data together",
        "Oracle connection pooling for high-throughput async workloads",
        "JSON/CLOB + VECTOR columns in same table - unified data model",
        "Enterprise security, backup, RAC/HA for vector workloads",
    ]
    for b in benefits:
        lines.append(f"  {c('>', 'green')} {b}")

    lines.append("")
    lines.append(c("=" * w, "cyan", "bold"))

    return "\n".join(lines), counts


def main():
    parser = argparse.ArgumentParser(description="OracLaw Oracle Database Monitor")
    parser.add_argument("--watch", action="store_true", help="Continuously refresh")
    parser.add_argument("--interval", type=int, default=5, help="Refresh interval in seconds")
    parser.add_argument("--json", action="store_true", help="Output as JSON (for programmatic use)")
    args = parser.parse_args()

    conn = get_connection()

    if args.json:
        counts = get_table_counts(conn)
        sizes = get_table_size_bytes(conn)
        vec_indexes = get_vector_index_stats(conn)
        onnx_models = get_onnx_models(conn)
        data = {
            "timestamp": datetime.now().isoformat(),
            "tables": counts,
            "sizes": {k: format_bytes(v) for k, v in sizes.items()},
            "vector_indexes": vec_indexes,
            "onnx_models": onnx_models,
            "sample_memories": get_sample_memories(conn),
            "sample_chunks": get_sample_chunks(conn),
            "sample_sessions": get_sample_sessions(conn),
            "recent_events": get_sample_transcripts(conn),
        }
        print(json.dumps(data, indent=2, default=str))
        conn.close()
        return

    previous_counts = None

    if args.watch:
        try:
            while True:
                os.system("clear" if os.name != "nt" else "cls")
                output, previous_counts = render_dashboard(conn, previous_counts)
                print(output)
                print(c(f"  Refreshing every {args.interval}s... (Ctrl+C to stop)", "dim"))
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n" + c("  Monitor stopped.", "yellow"))
    else:
        output, _ = render_dashboard(conn)
        print(output)

    conn.close()


if __name__ == "__main__":
    main()
