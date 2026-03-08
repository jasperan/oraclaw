import type { OraclawClient, TranscriptEvent, TranscriptHeader } from "./client.js";

export class OracleTranscriptProvider {
  constructor(private client: OraclawClient) {}

  async append(sessionId: string, event: { type: string; data: unknown }): Promise<void> {
    await this.client.appendTranscript(sessionId, {
      event_type: event.type,
      event_data: event.data,
    });
  }

  async read(sessionId: string, offset?: number, limit?: number): Promise<TranscriptEvent[]> {
    return this.client.getTranscript(sessionId, offset, limit);
  }

  async getHeader(sessionId: string): Promise<TranscriptHeader> {
    return this.client.getTranscriptHeader(sessionId);
  }

  async clear(sessionId: string): Promise<void> {
    await this.client.deleteTranscript(sessionId);
  }
}
