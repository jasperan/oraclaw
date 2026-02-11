import type { OraclawClient, SessionEntry } from "./client.js";

export class OracleSessionProvider {
  constructor(private client: OraclawClient) {}

  async load(agentId: string): Promise<Record<string, SessionEntry>> {
    return this.client.getSessions(agentId);
  }

  async get(key: string): Promise<SessionEntry> {
    return this.client.getSession(key);
  }

  async save(key: string, entry: SessionEntry): Promise<void> {
    await this.client.putSession(key, entry);
  }

  async update(key: string, updates: Partial<SessionEntry>): Promise<void> {
    await this.client.patchSession(key, updates);
  }

  async remove(key: string): Promise<void> {
    await this.client.deleteSession(key);
  }

  async prune(agentId: string, maxAgeMs: number): Promise<number> {
    return this.client.pruneSessions(agentId, maxAgeMs);
  }

  async cap(agentId: string, maxCount: number): Promise<number> {
    return this.client.capSessions(agentId, maxCount);
  }
}
