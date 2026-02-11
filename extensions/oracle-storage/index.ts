/**
 * OpenClaw Oracle Storage Plugin
 *
 * Oracle AI Vector Search with in-database ONNX embeddings for long-term memory.
 * Connects to the OracLaw Python sidecar service for all database operations.
 * Provides auto-recall, auto-capture, tools, CLI commands, and lifecycle hooks.
 */

import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import { Type } from "@sinclair/typebox";
import { OraclawClient, type MemoryEntry } from "./client.js";
import { MEMORY_CATEGORIES, type MemoryCategory, oracleConfigSchema } from "./config.js";

// ============================================================================
// Rule-based capture filter
// ============================================================================

const MEMORY_TRIGGERS = [
  /remember|zapamatuj si|pamatuj/i,
  /prefer|preferuji|rad(š|s)i|nechci/i,
  /decided|rozhodli jsme|budeme používat/i,
  /\+\d{10,}/,
  /[\w.-]+@[\w.-]+\.\w+/,
  /my\s+\w+\s+is|is\s+my/i,
  /i (like|prefer|hate|love|want|need)/i,
  /always|never|important/i,
  /the api|the endpoint|the url|the key/i,
  /i work at|my name is|i use/i,
];

export function shouldCapture(text: string): boolean {
  if (text.length < 10 || text.length > 500) {
    return false;
  }
  if (text.includes("<relevant-memories>")) {
    return false;
  }
  if (text.startsWith("<") && text.includes("</")) {
    return false;
  }
  if (text.includes("**") && text.includes("\n-")) {
    return false;
  }
  const emojiCount = (text.match(/[\u{1F300}-\u{1F9FF}]/gu) || []).length;
  if (emojiCount > 3) {
    return false;
  }
  return MEMORY_TRIGGERS.some((r) => r.test(text));
}

export function detectCategory(text: string): MemoryCategory {
  const lower = text.toLowerCase();
  if (/prefer|like|love|hate|want|dislike/i.test(lower)) {
    return "preference";
  }
  if (/decided|agreed|chose|will use|plan to/i.test(lower)) {
    return "decision";
  }
  if (/\+\d{10,}|@[\w.-]+\.\w+|is called|named|known as/i.test(lower)) {
    return "entity";
  }
  if (/is|are|has|have|was|were/i.test(lower)) {
    return "fact";
  }
  return "other";
}

// ============================================================================
// Plugin Definition
// ============================================================================

const oracleStoragePlugin = {
  id: "oracle-storage",
  name: "Oracle AI Database",
  description:
    "Oracle AI Vector Search with in-database ONNX embeddings for memory, sessions, and transcripts",
  kind: "memory" as const,
  configSchema: oracleConfigSchema,

  register(api: OpenClawPluginApi) {
    const cfg = oracleConfigSchema.parse(api.pluginConfig);
    const client = new OraclawClient(cfg.serviceUrl, cfg.serviceToken);

    api.logger.info(`oracle-storage: plugin registered (service: ${cfg.serviceUrl})`);

    // ========================================================================
    // Tools
    // ========================================================================

    api.registerTool(
      {
        name: "memory_recall",
        label: "Memory Recall",
        description:
          "Search through long-term memories stored in Oracle AI Database using hybrid keyword+vector search. Use when you need context about user preferences, past decisions, or previously discussed topics.",
        parameters: Type.Object({
          query: Type.String({ description: "Search query" }),
          limit: Type.Optional(
            Type.Number({ description: "Max results (default: configured maxResults)" }),
          ),
          category: Type.Optional(
            Type.Unsafe<MemoryCategory>({
              type: "string",
              enum: [...MEMORY_CATEGORIES],
              description: "Filter by memory category",
            }),
          ),
        }),
        async execute(_toolCallId, params) {
          const {
            query,
            limit = cfg.maxResults,
            category,
          } = params as {
            query: string;
            limit?: number;
            category?: MemoryCategory;
          };

          const results = await client.recall({
            query,
            max_results: limit,
            min_score: cfg.minScore,
            category,
          });

          if (results.length === 0) {
            return {
              content: [{ type: "text", text: "No relevant memories found." }],
              details: { count: 0 },
            };
          }

          const text = results
            .map((r, i) => `${i + 1}. [${r.category}] ${r.text} (${(r.score * 100).toFixed(0)}%)`)
            .join("\n");

          const sanitizedResults = results.map((r) => ({
            id: r.id,
            text: r.text,
            category: r.category,
            importance: r.importance,
            score: r.score,
          }));

          return {
            content: [{ type: "text", text: `Found ${results.length} memories:\n\n${text}` }],
            details: { count: results.length, memories: sanitizedResults },
          };
        },
      },
      { name: "memory_recall" },
    );

    api.registerTool(
      {
        name: "memory_store",
        label: "Memory Store",
        description:
          "Save important information in long-term memory using Oracle AI Database. Use for preferences, facts, decisions, and entities.",
        parameters: Type.Object({
          text: Type.String({ description: "Information to remember" }),
          importance: Type.Optional(Type.Number({ description: "Importance 0-1 (default: 0.7)" })),
          category: Type.Optional(
            Type.Unsafe<MemoryCategory>({
              type: "string",
              enum: [...MEMORY_CATEGORIES],
              description: "Memory category",
            }),
          ),
        }),
        async execute(_toolCallId, params) {
          const {
            text,
            importance = 0.7,
            category = "other",
          } = params as {
            text: string;
            importance?: number;
            category?: MemoryCategory;
          };

          // Check for duplicates via recall with high similarity
          const existing = await client.recall({
            query: text,
            max_results: 1,
            min_score: 0.95,
          });

          if (existing.length > 0) {
            return {
              content: [
                {
                  type: "text",
                  text: `Similar memory already exists: "${existing[0].text}"`,
                },
              ],
              details: {
                action: "duplicate",
                existingId: existing[0].id,
                existingText: existing[0].text,
              },
            };
          }

          const result = await client.remember({
            text,
            category,
            importance,
          });

          return {
            content: [
              {
                type: "text",
                text: `Stored: "${text.slice(0, 100)}${text.length > 100 ? "..." : ""}"`,
              },
            ],
            details: { action: "created", id: result.id },
          };
        },
      },
      { name: "memory_store" },
    );

    api.registerTool(
      {
        name: "memory_forget",
        label: "Memory Forget",
        description: "Delete specific memories from Oracle AI Database. GDPR-compliant.",
        parameters: Type.Object({
          query: Type.Optional(Type.String({ description: "Search to find memory" })),
          memoryId: Type.Optional(Type.String({ description: "Specific memory ID" })),
        }),
        async execute(_toolCallId, params) {
          const { query, memoryId } = params as {
            query?: string;
            memoryId?: string;
          };

          if (memoryId) {
            await client.forget(memoryId);
            return {
              content: [{ type: "text", text: `Memory ${memoryId} forgotten.` }],
              details: { action: "deleted", id: memoryId },
            };
          }

          if (query) {
            const results = await client.recall({
              query,
              max_results: 5,
              min_score: 0.7,
            });

            if (results.length === 0) {
              return {
                content: [{ type: "text", text: "No matching memories found." }],
                details: { found: 0 },
              };
            }

            if (results.length === 1 && results[0].score > 0.9) {
              await client.forget(results[0].id);
              return {
                content: [{ type: "text", text: `Forgotten: "${results[0].text}"` }],
                details: { action: "deleted", id: results[0].id },
              };
            }

            const list = results
              .map(
                (r) =>
                  `- [${r.id.slice(0, 8)}] ${r.text.slice(0, 60)}${r.text.length > 60 ? "..." : ""}`,
              )
              .join("\n");

            const sanitizedCandidates = results.map((r) => ({
              id: r.id,
              text: r.text,
              category: r.category,
              score: r.score,
            }));

            return {
              content: [
                {
                  type: "text",
                  text: `Found ${results.length} candidates. Specify memoryId:\n${list}`,
                },
              ],
              details: { action: "candidates", candidates: sanitizedCandidates },
            };
          }

          return {
            content: [{ type: "text", text: "Provide query or memoryId." }],
            details: { error: "missing_param" },
          };
        },
      },
      { name: "memory_forget" },
    );

    // ========================================================================
    // CLI Commands
    // ========================================================================

    api.registerCli(
      ({ program }) => {
        const oracle = program
          .command("oracle-memory")
          .description("Oracle AI Database memory management");

        oracle
          .command("list")
          .description("Count stored memories")
          .action(async () => {
            const count = await client.memoryCount();
            console.log(`Total memories: ${count}`);
          });

        oracle
          .command("search")
          .description("Search memories")
          .argument("<query>", "Search query")
          .option("--limit <n>", "Max results", String(cfg.maxResults))
          .option("--category <cat>", "Filter by category")
          .action(async (query, opts) => {
            const results = await client.recall({
              query,
              max_results: parseInt(opts.limit),
              min_score: cfg.minScore,
              category: opts.category,
            });

            if (results.length === 0) {
              console.log("No memories found.");
              return;
            }

            const output = results.map((r) => ({
              id: r.id,
              text: r.text,
              category: r.category,
              importance: r.importance,
              score: r.score,
            }));
            console.log(JSON.stringify(output, null, 2));
          });

        oracle
          .command("stats")
          .description("Show database statistics")
          .action(async () => {
            try {
              const health = await client.health();
              const status = await client.memoryStatus();
              console.log(
                [
                  `Database: ${health.status}`,
                  `Pool: ${health.pool?.open ?? 0} open, ${health.pool?.busy ?? 0} busy, ${health.pool?.free ?? 0} free`,
                  `Chunks: ${status.chunk_count}`,
                  `Files: ${status.file_count}`,
                  `Memories: ${status.memory_count ?? "N/A"}`,
                  `ONNX Model: ${health.onnx_model?.loaded ? `loaded (${health.onnx_model.name})` : "not loaded"}`,
                  `Uptime: ${health.uptime_seconds ? `${Math.round(health.uptime_seconds)}s` : "N/A"}`,
                ].join("\n"),
              );
            } catch (err) {
              console.error(`Failed to get stats: ${err}`);
            }
          });

        oracle
          .command("init")
          .description("Initialize Oracle schema and ONNX model")
          .action(async () => {
            try {
              const result = await client.init();
              console.log(`Schema initialized: ${JSON.stringify(result, null, 2)}`);
            } catch (err) {
              console.error(`Initialization failed: ${err}`);
            }
          });

        oracle
          .command("health")
          .description("Check sidecar service health")
          .action(async () => {
            try {
              const health = await client.health();
              console.log(JSON.stringify(health, null, 2));
            } catch (err) {
              console.error(`Health check failed: ${err}`);
            }
          });
      },
      { commands: ["oracle-memory"] },
    );

    // ========================================================================
    // Lifecycle Hooks
    // ========================================================================

    // Auto-recall: inject relevant memories before agent starts
    if (cfg.autoRecall) {
      api.on("before_agent_start", async (event) => {
        if (!event.prompt || event.prompt.length < 5) {
          return;
        }

        try {
          const results = await client.recall({
            query: event.prompt,
            max_results: cfg.maxResults,
            min_score: cfg.minScore,
          });

          if (results.length === 0) {
            return;
          }

          const memoryContext = results.map((r) => `- [${r.category}] ${r.text}`).join("\n");

          api.logger.info?.(`oracle-storage: injecting ${results.length} memories into context`);

          return {
            prependContext: `<relevant-memories>\nThe following memories may be relevant to this conversation:\n${memoryContext}\n</relevant-memories>`,
          };
        } catch (err) {
          api.logger.warn(`oracle-storage: recall failed: ${String(err)}`);
        }
      });
    }

    // Auto-capture: analyze and store important information after agent ends
    if (cfg.autoCapture) {
      api.on("agent_end", async (event) => {
        if (!event.success || !event.messages || event.messages.length === 0) {
          return;
        }

        try {
          const texts: string[] = [];
          for (const msg of event.messages) {
            if (!msg || typeof msg !== "object") {
              continue;
            }
            const msgObj = msg as Record<string, unknown>;
            const role = msgObj.role;
            if (role !== "user" && role !== "assistant") {
              continue;
            }

            const content = msgObj.content;
            if (typeof content === "string") {
              texts.push(content);
              continue;
            }

            if (Array.isArray(content)) {
              for (const block of content) {
                if (
                  block &&
                  typeof block === "object" &&
                  "type" in block &&
                  (block as Record<string, unknown>).type === "text" &&
                  "text" in block &&
                  typeof (block as Record<string, unknown>).text === "string"
                ) {
                  texts.push((block as Record<string, unknown>).text as string);
                }
              }
            }
          }

          const toCapture = texts.filter((text) => text && shouldCapture(text));
          if (toCapture.length === 0) {
            return;
          }

          // Limit to 3 captures per conversation to avoid flooding
          let stored = 0;
          for (const text of toCapture.slice(0, 3)) {
            const category = detectCategory(text);

            // Check for duplicates
            const existing = await client.recall({
              query: text,
              max_results: 1,
              min_score: 0.95,
            });
            if (existing.length > 0) {
              continue;
            }

            await client.remember({
              text,
              category,
              importance: 0.7,
            });
            stored++;
          }

          if (stored > 0) {
            api.logger.info(`oracle-storage: auto-captured ${stored} memories`);
          }
        } catch (err) {
          api.logger.warn(`oracle-storage: capture failed: ${String(err)}`);
        }
      });
    }

    // ========================================================================
    // Service
    // ========================================================================

    api.registerService({
      id: "oracle-storage",
      start: async () => {
        try {
          const health = await client.health();
          if (health.status !== "ok") {
            throw new Error(`OracLaw service unhealthy: ${JSON.stringify(health)}`);
          }
          // Auto-init schema on startup
          await client.init();
          api.logger.info(
            `oracle-storage: service started (db: ${health.database}, pool: ${health.pool?.open ?? 0} connections)`,
          );
        } catch (err) {
          api.logger.warn(
            `oracle-storage: service start failed (sidecar may not be running): ${String(err)}`,
          );
        }
      },
      stop: () => {
        api.logger.info("oracle-storage: service stopped");
      },
    });
  },
};

export default oracleStoragePlugin;
