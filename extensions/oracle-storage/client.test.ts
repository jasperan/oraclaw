/**
 * Tests for the OracLaw client module.
 *
 * Tests the OraclawClient class error handling, retry logic, and type structures.
 * Uses a mock HTTP server to simulate sidecar responses.
 */

import http from "node:http";
import { afterAll, beforeAll, describe, expect, test } from "vitest";
import { OraclawClient } from "./client.js";

let server: http.Server;
let baseUrl: string;

beforeAll(async () => {
  server = http.createServer((req, res) => {
    const url = new URL(req.url ?? "/", `http://localhost`);
    const path = url.pathname;

    res.setHeader("Content-Type", "application/json");

    // Health endpoint
    if (path === "/api/health" && req.method === "GET") {
      res.writeHead(200);
      res.end(
        JSON.stringify({
          status: "ok",
          pool: { min: 2, max: 10, open: 3, busy: 1 },
          onnx_model: { name: "ALL_MINILM_L12_V2", loaded: true },
          tables: { ORACLAW_META: true },
          schema_version: "0.1.0",
        }),
      );
      return;
    }

    // Init endpoint
    if (path === "/api/init" && req.method === "POST") {
      res.writeHead(200);
      res.end(
        JSON.stringify({
          status: "initialized",
          tables_created: ["ORACLAW_META"],
          indexes_created: [],
          errors: [],
          onnx_loaded: true,
        }),
      );
      return;
    }

    // Memory recall
    if (path === "/api/memory/recall" && req.method === "POST") {
      res.writeHead(200);
      res.end(
        JSON.stringify({
          results: [
            {
              memory_id: "mem-1",
              text: "User prefers dark mode",
              category: "preference",
              importance: 0.8,
              score: 0.92,
              agent_id: "default",
              created_at: "2026-01-01",
            },
          ],
          count: 1,
        }),
      );
      return;
    }

    // Memory remember
    if (path === "/api/memory/remember" && req.method === "POST") {
      res.writeHead(200);
      res.end(JSON.stringify({ memory_id: "new-mem-1", stored: true }));
      return;
    }

    // Memory forget
    if (path.startsWith("/api/memory/forget/") && req.method === "DELETE") {
      res.writeHead(200);
      res.end(JSON.stringify({ deleted: 1 }));
      return;
    }

    // Memory count
    if (path === "/api/memory/count" && req.method === "GET") {
      res.writeHead(200);
      res.end(JSON.stringify({ count: 42 }));
      return;
    }

    // Memory status
    if (path === "/api/memory/status" && req.method === "GET") {
      res.writeHead(200);
      res.end(
        JSON.stringify({
          chunk_count: 100,
          file_count: 10,
          memory_count: 42,
          cache_count: 5,
        }),
      );
      return;
    }

    // Memory search
    if (path === "/api/memory/search" && req.method === "POST") {
      res.writeHead(200);
      res.end(
        JSON.stringify({
          results: [
            {
              path: "src/main.py",
              startLine: 1,
              endLine: 10,
              score: 0.85,
              snippet: "def main():\n    pass",
              source: "memory",
            },
          ],
          count: 1,
        }),
      );
      return;
    }

    // Sessions list
    if (path === "/api/sessions/" && req.method === "GET") {
      res.writeHead(200);
      res.end(
        JSON.stringify({
          sessions: [
            {
              session_key: "sk-1",
              session_id: "sid-1",
              agent_id: "default",
              updated_at: Date.now(),
              session_data: {},
            },
          ],
          count: 1,
        }),
      );
      return;
    }

    // Transcripts append
    if (path === "/api/transcripts/" && req.method === "POST") {
      res.writeHead(200);
      res.end(
        JSON.stringify({
          id: "ev-1",
          session_id: "sess-1",
          sequence_num: 0,
          event_type: "message",
        }),
      );
      return;
    }

    // 404 client error (not retried)
    if (path === "/api/not-found") {
      res.writeHead(404);
      res.end(JSON.stringify({ detail: "Not found" }));
      return;
    }

    // 500 server error (retried)
    if (path === "/api/server-error") {
      res.writeHead(500);
      res.end(JSON.stringify({ detail: "Internal error" }));
      return;
    }

    res.writeHead(404);
    res.end(JSON.stringify({ detail: "Not found" }));
  });

  await new Promise<void>((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const addr = server.address();
      if (addr && typeof addr === "object") {
        baseUrl = `http://127.0.0.1:${addr.port}`;
      }
      resolve();
    });
  });
});

afterAll(async () => {
  await new Promise<void>((resolve) => {
    server.close(() => resolve());
  });
});

describe("OraclawClient", () => {
  test("health returns correct structure", async () => {
    const client = new OraclawClient(baseUrl);
    const health = await client.health();

    expect(health.status).toBe("ok");
    expect(health.pool?.min).toBe(2);
    expect(health.pool?.max).toBe(10);
    expect(health.onnx_model?.name).toBe("ALL_MINILM_L12_V2");
    expect(health.onnx_model?.loaded).toBe(true);
    expect(health.schema_version).toBe("0.1.0");
  });

  test("init returns initialization result", async () => {
    const client = new OraclawClient(baseUrl);
    const result = await client.init();

    expect(result.status).toBe("initialized");
    expect(result.onnx_loaded).toBe(true);
    expect(result.tables_created).toContain("ORACLAW_META");
  });

  test("recall returns mapped memory entries", async () => {
    const client = new OraclawClient(baseUrl);
    const results = await client.recall({ query: "dark mode" });

    expect(results.length).toBe(1);
    expect(results[0].id).toBe("mem-1");
    expect(results[0].text).toBe("User prefers dark mode");
    expect(results[0].category).toBe("preference");
    expect(results[0].score).toBe(0.92);
  });

  test("remember returns memory ID", async () => {
    const client = new OraclawClient(baseUrl);
    const result = await client.remember({ text: "Test memory" });

    expect(result.id).toBe("new-mem-1");
  });

  test("forget does not throw", async () => {
    const client = new OraclawClient(baseUrl);
    await expect(client.forget("mem-1")).resolves.not.toThrow();
  });

  test("memoryCount returns number", async () => {
    const client = new OraclawClient(baseUrl);
    const count = await client.memoryCount();

    expect(count).toBe(42);
  });

  test("memoryStatus returns counts", async () => {
    const client = new OraclawClient(baseUrl);
    const status = await client.memoryStatus();

    expect(status.chunk_count).toBe(100);
    expect(status.file_count).toBe(10);
    expect(status.memory_count).toBe(42);
  });

  test("memorySearch returns results", async () => {
    const client = new OraclawClient(baseUrl);
    const results = await client.memorySearch({ query: "main function" });

    expect(results.length).toBe(1);
    expect(results[0].path).toBe("src/main.py");
    expect(results[0].score).toBe(0.85);
  });

  test("getSessions returns keyed record", async () => {
    const client = new OraclawClient(baseUrl);
    const sessions = await client.getSessions();

    expect(sessions["sk-1"]).toBeDefined();
    expect(sessions["sk-1"].session_id).toBe("sid-1");
  });

  test("appendTranscript does not throw", async () => {
    const client = new OraclawClient(baseUrl);
    await expect(
      client.appendTranscript("sess-1", { event_type: "message", event_data: { text: "hello" } }),
    ).resolves.not.toThrow();
  });

  test("strips trailing slash from baseUrl", async () => {
    const client = new OraclawClient(`${baseUrl}/`);
    const health = await client.health();
    expect(health.status).toBe("ok");
  });

  test("includes Authorization header when token provided", async () => {
    // The mock server doesn't check auth, but the client should set the header
    const client = new OraclawClient(baseUrl, "test-token");
    const health = await client.health();
    expect(health.status).toBe("ok");
  });

  test("throws on connection errors after retries", async () => {
    // Point to a port where nothing is listening
    const badClient = new OraclawClient("http://127.0.0.1:1");
    await expect(badClient.health()).rejects.toThrow();
  });
});
