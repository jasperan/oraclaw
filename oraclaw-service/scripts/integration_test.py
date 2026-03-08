#!/usr/bin/env python3
"""
OracLaw End-to-End Integration Test
=====================================
Tests all OracLaw sidecar APIs against a live Oracle FreePDB instance.
Demonstrates the full lifecycle: init -> store -> search -> recall -> cleanup.

Prerequisites:
    - Oracle FreePDB container running on localhost:1521
    - OracLaw sidecar running on localhost:8100
    - ORACLAW user created in FREEPDB1

Usage:
    python scripts/integration_test.py
"""

import json
import sys
import time
import uuid
from datetime import datetime

import requests

BASE = "http://localhost:8100"
AGENT = f"test-agent-{uuid.uuid4().hex[:8]}"
PASS = 0
FAIL = 0
RESULTS = []


def log(status, test_name, detail=""):
    global PASS, FAIL
    icon = "\033[92mPASS\033[0m" if status else "\033[91mFAIL\033[0m"
    if status:
        PASS += 1
    else:
        FAIL += 1
    msg = f"  [{icon}] {test_name}"
    if detail:
        msg += f" - {detail}"
    print(msg)
    RESULTS.append({"test": test_name, "status": "PASS" if status else "FAIL", "detail": detail})


def section(title):
    print(f"\n\033[96m\033[1m{'=' * 70}\033[0m")
    print(f"\033[96m\033[1m  {title}\033[0m")
    print(f"\033[96m\033[1m{'=' * 70}\033[0m")


def test_health():
    section("1. HEALTH CHECK")
    r = requests.get(f"{BASE}/api/health")
    data = r.json()
    log(r.status_code == 200, "Health endpoint returns 200")
    log(data["status"] == "ok", "Status is 'ok'")
    log(data["pool"]["open"] > 0, f"Connection pool open={data['pool']['open']}")
    log(all(data["tables"].values()), f"All {len(data['tables'])} tables exist")
    log(data["schema_version"] == "0.1.0", f"Schema version: {data['schema_version']}")
    log(data["onnx_model"]["loaded"], f"Embedding mode: {data['onnx_model']['mode']}")
    return data


def test_memory_store():
    section("2. MEMORY STORE (remember)")
    memories = [
        {"text": "Python is great for data science and ML", "importance": 0.9, "category": "language"},
        {"text": "Oracle Database supports VECTOR data type natively", "importance": 0.95, "category": "database"},
        {"text": "FastAPI provides async HTTP endpoints with auto-docs", "importance": 0.8, "category": "framework"},
        {"text": "Cosine similarity measures the angle between two vectors", "importance": 0.85, "category": "math"},
        {"text": "ONNX models can run inside Oracle Database for zero-copy inference", "importance": 0.92, "category": "ai"},
    ]

    memory_ids = []
    for mem in memories:
        mem["agent_id"] = AGENT
        r = requests.post(f"{BASE}/api/memory/remember", json=mem)
        data = r.json()
        log(r.status_code == 200, f"Store: '{mem['text'][:50]}...'")
        log(data.get("stored") is True, f"  memory_id: {data.get('memory_id', 'N/A')[:20]}...")
        memory_ids.append(data.get("memory_id"))

    return memory_ids


def test_memory_recall():
    section("3. MEMORY RECALL (vector similarity search)")
    queries = [
        ("What programming language is used for ML?", "language"),
        ("vector database support", "database"),
        ("nearest neighbor search algorithm", "math"),
    ]

    for query, expected_cat in queries:
        r = requests.post(f"{BASE}/api/memory/recall", json={
            "query": query,
            "agent_id": AGENT,
            "max_results": 3,
            "min_score": 0.2,
        })
        data = r.json()
        results = data.get("results", [])
        log(r.status_code == 200, f"Recall: '{query}'")
        log(len(results) > 0, f"  Found {len(results)} results (expected > 0)")
        if results:
            top = results[0]
            log(top["score"] > 0.2, f"  Top score: {top['score']} (text: '{top['text'][:50]}...')")


def test_memory_count():
    section("4. MEMORY COUNT")
    r = requests.get(f"{BASE}/api/memory/count", params={"agent_id": AGENT})
    data = r.json()
    log(r.status_code == 200, "Count endpoint returns 200")
    log(data["count"] == 5, f"Memory count: {data['count']} (expected 5)")


def test_chunk_storage():
    section("5. CODE CHUNK STORAGE")
    chunks = [
        {
            "id": f"intg-chunk-{uuid.uuid4().hex[:8]}",
            "path": "/test/integration/app.py",
            "source": "integration-test",
            "start_line": 1,
            "end_line": 20,
            "hash": uuid.uuid4().hex[:16],
            "model": "test",
            "text": "class Application:\n    def __init__(self, config):\n        self.db = OracleDB(config)\n        self.cache = VectorCache()\n    \n    async def search(self, query):\n        return await self.db.vector_search(query)",
        },
        {
            "id": f"intg-chunk-{uuid.uuid4().hex[:8]}",
            "path": "/test/integration/config.py",
            "source": "integration-test",
            "start_line": 1,
            "end_line": 10,
            "hash": uuid.uuid4().hex[:16],
            "model": "test",
            "text": "ORACLE_DSN = 'localhost:1521/FREEPDB1'\nORACLE_USER = 'oraclaw'\nPOOL_MIN = 2\nPOOL_MAX = 10",
        },
    ]

    chunk_ids = []
    for chunk in chunks:
        r = requests.post(f"{BASE}/api/memory/chunks", json=chunk)
        data = r.json()
        log(r.status_code == 200, f"Store chunk: {chunk['path']}")
        log(data.get("stored") is True, f"  chunk_id: {chunk['id']}")
        chunk_ids.append(chunk["id"])

    return chunk_ids


def test_chunk_search():
    section("6. CODE CHUNK SEARCH (vector)")
    queries = [
        "Oracle database configuration",
        "application class with vector cache",
    ]

    for query in queries:
        r = requests.post(f"{BASE}/api/memory/search", json={
            "query": query,
            "max_results": 3,
            "min_score": 0.2,
            "source": "integration-test",
        })
        data = r.json()
        log(r.status_code == 200, f"Search: '{query}'")
        log(len(data.get("results", [])) > 0, f"  Found {data.get('count', 0)} results")
        for res in data.get("results", [])[:2]:
            print(f"    -> {res['path']} (score={res['score']}, L{res['startLine']}-{res['endLine']})")


def test_sessions():
    section("7. SESSION MANAGEMENT")
    session_key = f"intg-sess-{uuid.uuid4().hex[:8]}"

    # Create session
    r = requests.put(f"{BASE}/api/sessions/", json={
        "session_key": session_key,
        "session_id": f"sid-{session_key}",
        "agent_id": AGENT,
        "updated_at": int(time.time() * 1000),
        "session_data": {"test": True, "started_at": datetime.now().isoformat()},
        "channel": "integration-test",
        "label": "Integration Test Session",
    })
    log(r.status_code == 200, f"Create session: {session_key}")

    # Get session
    r = requests.get(f"{BASE}/api/sessions/{session_key}")
    data = r.json()
    log(r.status_code == 200, "Get session")
    log(data["session_key"] == session_key, f"  session_key matches: {session_key}")

    # List sessions
    r = requests.get(f"{BASE}/api/sessions/", params={"agent_id": AGENT})
    data = r.json()
    log(r.status_code == 200, f"List sessions: {data['count']} found")
    log(data["count"] >= 1, "  At least 1 session for agent")

    # Update session
    r = requests.patch(f"{BASE}/api/sessions/{session_key}", json={
        "label": "Integration Test Session (updated)",
    })
    log(r.status_code == 200, "Update session label")

    # Delete session
    r = requests.delete(f"{BASE}/api/sessions/{session_key}")
    log(r.status_code == 200, "Delete session")

    # Verify deletion
    r = requests.get(f"{BASE}/api/sessions/{session_key}")
    log(r.status_code == 404, "Session properly deleted (404)")


def test_transcripts():
    section("8. TRANSCRIPT STORAGE")
    session_id = f"sid-intg-{uuid.uuid4().hex[:8]}"

    # Append events
    events = [
        {"event_type": "user_message", "event_data": {"role": "user", "content": "What tables does OracLaw use?"}},
        {"event_type": "assistant_message", "event_data": {"role": "assistant", "content": "OracLaw uses 8 tables including MEMORIES, CHUNKS, SESSIONS, and TRANSCRIPTS."}},
        {"event_type": "user_message", "event_data": {"role": "user", "content": "How does vector search work?"}},
        {"event_type": "tool_call", "event_data": {"tool": "oracle_search", "query": "vector search architecture"}},
        {"event_type": "assistant_message", "event_data": {"role": "assistant", "content": "It uses VECTOR_DISTANCE with cosine similarity on embeddings stored in VECTOR columns."}},
    ]

    for evt in events:
        evt["session_id"] = session_id
        evt["agent_id"] = AGENT
        r = requests.post(f"{BASE}/api/transcripts/", json=evt)
        data = r.json()
        log(r.status_code == 200, f"Append: {evt['event_type']}")
        log("sequence_num" in data, f"  seq={data.get('sequence_num')}")

    # Get events
    r = requests.get(f"{BASE}/api/transcripts/{session_id}")
    data = r.json()
    log(r.status_code == 200, f"Get transcript: {data['count']} events")
    log(data["count"] == 5, "  All 5 events stored")

    # Check ordering
    if data["count"] == 5:
        seqs = [e["sequence_num"] for e in data["events"]]
        log(seqs == sorted(seqs), f"  Events ordered by sequence: {seqs}")

    # Delete transcript
    r = requests.delete(f"{BASE}/api/transcripts/{session_id}")
    log(r.status_code == 200, "Delete transcript")

    return session_id


def test_memory_status():
    section("9. MEMORY STATUS")
    r = requests.get(f"{BASE}/api/memory/status")
    data = r.json()
    log(r.status_code == 200, "Memory status endpoint")
    log(data["chunk_count"] >= 3, f"  Chunks: {data['chunk_count']}")
    log(data["memory_count"] >= 5, f"  Memories: {data['memory_count']}")
    print(f"    Full status: {json.dumps(data)}")


def test_cleanup(memory_ids, chunk_ids):
    section("10. CLEANUP")

    # Forget memories
    for mid in memory_ids:
        if mid:
            r = requests.delete(f"{BASE}/api/memory/forget/{mid}")
            log(r.status_code == 200, f"Forget memory: {mid[:20]}...")

    # Delete chunks
    for cid in chunk_ids:
        r = requests.delete(f"{BASE}/api/memory/chunks/{cid}")
        log(r.status_code == 200, f"Delete chunk: {cid}")


def main():
    print("\n\033[95m\033[1m" + "=" * 70)
    print("  ORACLAW END-TO-END INTEGRATION TEST")
    print(f"  Agent: {AGENT}")
    print(f"  Target: {BASE}")
    print(f"  Time: {datetime.now().isoformat()}")
    print("=" * 70 + "\033[0m")

    try:
        health = test_health()
        memory_ids = test_memory_store()
        test_memory_recall()
        test_memory_count()
        chunk_ids = test_chunk_storage()
        test_chunk_search()
        test_sessions()
        test_transcripts()
        test_memory_status()
        test_cleanup(memory_ids, chunk_ids)
    except requests.ConnectionError:
        print(f"\n\033[91mERROR: Cannot connect to {BASE}")
        print("Make sure the OracLaw sidecar is running.\033[0m")
        sys.exit(1)
    except Exception as e:
        print(f"\n\033[91mERROR: {e}\033[0m")
        import traceback
        traceback.print_exc()

    # Summary
    print(f"\n\033[96m\033[1m{'=' * 70}\033[0m")
    print(f"\033[96m\033[1m  RESULTS: {PASS} passed, {FAIL} failed, {PASS + FAIL} total\033[0m")
    print(f"\033[96m\033[1m{'=' * 70}\033[0m\n")

    if FAIL > 0:
        print("\033[91mFailed tests:\033[0m")
        for r in RESULTS:
            if r["status"] == "FAIL":
                print(f"  - {r['test']}: {r['detail']}")
        sys.exit(1)
    else:
        print("\033[92mAll tests passed! OracLaw + Oracle AI Database integration is working.\033[0m\n")


if __name__ == "__main__":
    main()
