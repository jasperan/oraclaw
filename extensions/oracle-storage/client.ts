// ============================================================================
// OracLaw Sidecar HTTP Client
// ============================================================================

export type HealthResponse = {
  status: string;
  pool?: { min: number; max: number; open: number; busy: number; free?: number };
  onnx_model?: { name: string; loaded: boolean; mode?: string };
  tables?: Record<string, boolean>;
  schema_version?: string;
  database?: string;
  uptime_seconds?: number;
};

export type InitResponse = {
  status: string;
  tables_created?: string[];
  indexes_created?: string[];
  errors?: string[];
  onnx_loaded?: boolean;
};

export type MemorySearchParams = {
  query: string;
  maxResults?: number;
  minScore?: number;
  hybrid?: boolean;
  source?: string;
};

export type MemorySearchResult = {
  path: string;
  startLine: number;
  endLine: number;
  score: number;
  snippet: string;
  source: string;
  citation?: string;
};

export type StoreChunkParams = {
  id: string;
  path: string;
  source?: string;
  start_line: number;
  end_line: number;
  hash: string;
  model: string;
  text: string;
};

export type SyncFile = {
  file_id: string;
  path: string;
  source?: string;
  hash?: string;
  chunk_count?: number;
};

export type MemoryStatus = {
  chunk_count: number;
  file_count: number;
  memory_count?: number;
  cache_count?: number;
};

export type FileInfo = {
  path: string;
  source: string;
  hash: string;
  chunk_count: number;
};

export type RememberParams = {
  text: string;
  category?: string;
  importance?: number;
  agent_id?: string;
};

export type RecallParams = {
  query: string;
  max_results?: number;
  min_score?: number;
  category?: string;
  agent_id?: string;
};

export type MemoryEntry = {
  id: string;
  text: string;
  category: string;
  importance: number;
  score: number;
  created_at?: string;
  agent_id?: string;
};

export type SessionEntry = Record<string, unknown>;

export type TranscriptEvent = {
  session_id: string;
  agent_id?: string;
  event_type: string;
  event_data: unknown;
};

export type TranscriptHeader = {
  session_id: string;
  event_count: number;
  first_event?: string;
  last_event?: string;
};

class OraclawClientError extends Error {
  constructor(
    message: string,
    public status: number,
    public body?: string,
  ) {
    super(message);
    this.name = "OraclawClientError";
  }
}

export class OraclawClient {
  private baseUrl: string;
  private token?: string;
  private maxRetries = 3;

  constructor(baseUrl: string, token?: string) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.token = token;
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
    timeoutMs = 5000,
  ): Promise<T> {
    let lastError: Error | undefined;

    for (let attempt = 0; attempt < this.maxRetries; attempt++) {
      if (attempt > 0) {
        // Exponential backoff: 100ms, 200ms, 400ms
        await new Promise((r) => setTimeout(r, 100 * 2 ** (attempt - 1)));
      }

      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);

      try {
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
          Accept: "application/json",
        };
        if (this.token) {
          headers.Authorization = `Bearer ${this.token}`;
        }

        const res = await fetch(`${this.baseUrl}${path}`, {
          method,
          headers,
          body: body !== undefined ? JSON.stringify(body) : undefined,
          signal: controller.signal,
        });

        clearTimeout(timer);

        if (!res.ok) {
          const text = await res.text().catch(() => "");
          // Don't retry 4xx client errors (except 429)
          if (res.status >= 400 && res.status < 500 && res.status !== 429) {
            throw new OraclawClientError(
              `${method} ${path} => ${res.status}: ${text}`,
              res.status,
              text,
            );
          }
          lastError = new OraclawClientError(
            `${method} ${path} => ${res.status}: ${text}`,
            res.status,
            text,
          );
          continue;
        }

        const contentType = res.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
          return (await res.json()) as T;
        }
        // For non-JSON responses, return text as-is
        return (await res.text()) as unknown as T;
      } catch (err) {
        clearTimeout(timer);
        if (
          err instanceof OraclawClientError &&
          err.status >= 400 &&
          err.status < 500 &&
          err.status !== 429
        ) {
          throw err;
        }
        lastError = err instanceof Error ? err : new Error(String(err));
      }
    }

    throw lastError ?? new Error(`${method} ${path} failed after ${this.maxRetries} attempts`);
  }

  // ========================================================================
  // Health & Init
  // ========================================================================

  async health(): Promise<HealthResponse> {
    return this.request<HealthResponse>("GET", "/api/health");
  }

  async init(): Promise<InitResponse> {
    return this.request<InitResponse>("POST", "/api/init", {}, 30000);
  }

  // ========================================================================
  // Memory - vector chunks (code/file search)
  // ========================================================================

  async memorySearch(params: MemorySearchParams): Promise<MemorySearchResult[]> {
    const response = await this.request<{ results: MemorySearchResult[]; count: number }>(
      "POST",
      "/api/memory/search",
      {
        query: params.query,
        max_results: params.maxResults ?? 6,
        min_score: params.minScore ?? 0.3,
        hybrid: params.hybrid ?? true,
        source: params.source,
      },
    );
    return response.results;
  }

  async storeChunk(chunk: StoreChunkParams): Promise<void> {
    await this.request<void>("POST", "/api/memory/chunks", chunk);
  }

  async storeChunksBatch(chunks: StoreChunkParams[]): Promise<void> {
    await this.request<void>("POST", "/api/memory/chunks/batch", chunks, 30000);
  }

  async deleteChunk(chunkId: string): Promise<void> {
    await this.request<void>("DELETE", `/api/memory/chunks/${encodeURIComponent(chunkId)}`);
  }

  async syncFiles(files: SyncFile[]): Promise<void> {
    await this.request<void>("POST", "/api/memory/files/sync", files, 60000);
  }

  async memoryStatus(): Promise<MemoryStatus> {
    return this.request<MemoryStatus>("GET", "/api/memory/status");
  }

  // ========================================================================
  // Memory - long-term (remember/recall)
  // ========================================================================

  async remember(params: RememberParams): Promise<{ id: string }> {
    const result = await this.request<{ memory_id: string; stored: boolean }>(
      "POST",
      "/api/memory/remember",
      params,
    );
    return { id: result.memory_id };
  }

  async recall(params: RecallParams): Promise<MemoryEntry[]> {
    const response = await this.request<{ results: Array<Record<string, unknown>>; count: number }>(
      "POST",
      "/api/memory/recall",
      params,
    );
    return response.results.map((r) => ({
      id: (r.memory_id as string) || "",
      text: (r.text as string) || "",
      category: (r.category as string) || "other",
      importance: (r.importance as number) || 0,
      score: (r.score as number) || 0,
      created_at: r.created_at as string | undefined,
      agent_id: r.agent_id as string | undefined,
    }));
  }

  async forget(id: string): Promise<void> {
    await this.request<void>("DELETE", `/api/memory/forget/${encodeURIComponent(id)}`);
  }

  async memoryCount(agentId?: string): Promise<number> {
    const qs = agentId ? `?agent_id=${encodeURIComponent(agentId)}` : "";
    const result = await this.request<{ count: number }>("GET", `/api/memory/count${qs}`);
    return result.count;
  }

  // ========================================================================
  // Sessions
  // ========================================================================

  async getSessions(agentId?: string): Promise<Record<string, SessionEntry>> {
    const qs = agentId ? `?agent_id=${encodeURIComponent(agentId)}` : "";
    const result = await this.request<{ sessions: SessionEntry[]; count: number }>(
      "GET",
      `/api/sessions/${qs}`,
    );
    // Convert array to record keyed by session_key
    const record: Record<string, SessionEntry> = {};
    for (const s of result.sessions) {
      const key = (s.session_key as string) || (s.session_id as string);
      if (key) record[key] = s;
    }
    return record;
  }

  async getSession(key: string): Promise<SessionEntry> {
    return this.request<SessionEntry>("GET", `/api/sessions/${encodeURIComponent(key)}`);
  }

  async putSession(key: string, entry: SessionEntry): Promise<void> {
    await this.request<void>("PUT", "/api/sessions/", {
      session_key: key,
      ...entry,
    });
  }

  async patchSession(key: string, updates: Partial<SessionEntry>): Promise<void> {
    await this.request<void>("PATCH", `/api/sessions/${encodeURIComponent(key)}`, updates);
  }

  async deleteSession(key: string): Promise<void> {
    await this.request<void>("DELETE", `/api/sessions/${encodeURIComponent(key)}`);
  }

  async pruneSessions(agentId: string, maxAgeMs: number): Promise<number> {
    const result = await this.request<{ removed: number }>("POST", "/api/sessions/prune", {
      agent_id: agentId,
      max_age_ms: maxAgeMs,
    });
    return result.removed;
  }

  async capSessions(agentId: string, maxCount: number): Promise<number> {
    const result = await this.request<{ removed: number }>("POST", "/api/sessions/cap", {
      agent_id: agentId,
      max_count: maxCount,
    });
    return result.removed;
  }

  // ========================================================================
  // Transcripts
  // ========================================================================

  async appendTranscript(
    sessionId: string,
    event: { event_type: string; event_data: unknown; agent_id?: string },
  ): Promise<void> {
    await this.request<void>("POST", "/api/transcripts/", {
      session_id: sessionId,
      agent_id: event.agent_id || "default",
      event_type: event.event_type,
      event_data: event.event_data,
    });
  }

  async getTranscript(
    sessionId: string,
    offset?: number,
    limit?: number,
  ): Promise<TranscriptEvent[]> {
    const params = new URLSearchParams();
    if (offset !== undefined) params.set("offset", String(offset));
    if (limit !== undefined) params.set("limit", String(limit));
    const qs = params.toString() ? `?${params.toString()}` : "";
    const result = await this.request<{ events: TranscriptEvent[]; count: number }>(
      "GET",
      `/api/transcripts/${encodeURIComponent(sessionId)}${qs}`,
    );
    return result.events;
  }

  async getTranscriptHeader(sessionId: string): Promise<TranscriptHeader> {
    return this.request<TranscriptHeader>(
      "GET",
      `/api/transcripts/${encodeURIComponent(sessionId)}/header`,
    );
  }

  async deleteTranscript(sessionId: string): Promise<void> {
    await this.request<void>("DELETE", `/api/transcripts/${encodeURIComponent(sessionId)}`);
  }
}
