import type { RequestClient } from "@buape/carbon";
import { Routes } from "discord-api-types/v10";
import type { TypingController } from "../../auto-reply/reply/typing.js";
import type { FeedbackConfig } from "../../config/types.messages.js";
import { normalizeReactionEmoji } from "../send.shared.js";

type FeedbackState = "idle" | "processing" | "tools" | "done";

type DiscordFeedbackControllerOptions = {
  channelId: string;
  messageId: string;
  rest: RequestClient;
  config: FeedbackConfig;
};

/**
 * Per-message feedback controller managing reaction state machine,
 * optional status messages, and typing TTL refresh during agent processing.
 *
 * All Discord API calls are fire-and-forget with error swallowing to
 * ensure feedback never blocks agent execution.
 */
export class DiscordFeedbackController {
  private readonly channelId: string;
  private readonly messageId: string;
  private readonly rest: RequestClient;

  // Reaction config (defaults)
  private readonly reactionsEnabled: boolean;
  private readonly processingEmoji: string;
  private readonly toolsEmoji: string;
  private readonly doneEmoji: string;
  private readonly doneRemoveAfterSeconds: number;

  // Status config (defaults)
  private readonly statusEnabled: boolean;
  private readonly statusDelaySeconds: number;
  private readonly statusInitialText: string;
  private readonly statusToolTemplate: string;
  private readonly statusDeleteAfterReply: boolean;

  // State
  private state: FeedbackState = "idle";
  private sealed = false;
  private typingController: TypingController | null = null;
  private statusMessageId: string | null = null;
  private statusTimer: ReturnType<typeof setTimeout> | null = null;
  private doneRemoveTimer: ReturnType<typeof setTimeout> | null = null;
  private lastToolName: string | undefined;

  constructor(opts: DiscordFeedbackControllerOptions) {
    this.channelId = opts.channelId;
    this.messageId = opts.messageId;
    this.rest = opts.rest;

    const rc = opts.config.reactions ?? {};
    this.reactionsEnabled = rc.enabled !== false;
    this.processingEmoji = rc.processing ?? "\u23F3"; // ⏳
    this.toolsEmoji = rc.tools ?? "\u2699\uFE0F"; // ⚙️
    this.doneEmoji = rc.done ?? "\u2705"; // ✅
    this.doneRemoveAfterSeconds = rc.doneRemoveAfterSeconds ?? 10;

    const sc = opts.config.status ?? {};
    this.statusEnabled = sc.enabled ?? false;
    this.statusDelaySeconds = sc.delaySeconds ?? 15;
    this.statusInitialText = sc.initialText ?? "Working on it...";
    this.statusToolTemplate = sc.toolTemplate ?? "Using {tool}...";
    this.statusDeleteAfterReply = sc.deleteAfterReply !== false;
  }

  /** Provide the typing controller for TTL refresh on tool events. */
  setTypingController(typing: TypingController): void {
    if (this.sealed) {
      return;
    }
    this.typingController = typing;
  }

  /** Called when the agent run starts processing. */
  async onRunStart(): Promise<void> {
    if (this.sealed) {
      return;
    }
    await this.transitionTo("processing");
    this.startStatusTimer();
  }

  /** Called on each tool lifecycle event from the agent runner. */
  async onToolEvent(phase: string, toolName?: string): Promise<void> {
    if (this.sealed) {
      return;
    }

    // Refresh typing TTL on every tool event
    this.typingController?.refreshTypingTtl();

    if (phase === "start") {
      this.lastToolName = toolName;
      await this.transitionTo("tools");
      this.updateStatusWithTool(toolName);
    }
  }

  /** Called when a reply has been delivered to the user. */
  async onReplyDelivered(): Promise<void> {
    if (this.sealed) {
      return;
    }
    await this.transitionTo("done");
    this.cleanupStatus();
    this.scheduleDoneRemoval();
    this.seal();
  }

  /** Called when the dispatch completes with no reply (silent/NO_REPLY). */
  async onNoReply(): Promise<void> {
    if (this.sealed) {
      return;
    }
    await this.removeCurrentReaction();
    this.cleanupStatus();
    this.seal();
  }

  /** Called on dispatch error for cleanup. */
  async onError(): Promise<void> {
    if (this.sealed) {
      return;
    }
    await this.removeCurrentReaction();
    this.cleanupStatus();
    this.seal();
  }

  // ── Reaction state machine ──────────────────────────────────────

  private async transitionTo(next: FeedbackState): Promise<void> {
    if (!this.reactionsEnabled || this.sealed) {
      return;
    }
    const prev = this.state;
    if (prev === next) {
      return;
    }
    const prevEmoji = this.emojiForState(prev);
    const nextEmoji = this.emojiForState(next);
    this.state = next;

    // Add new reaction first, then remove old to prevent visual gap
    if (nextEmoji) {
      await this.addReaction(nextEmoji);
    }
    if (prevEmoji && prevEmoji !== nextEmoji) {
      await this.removeReaction(prevEmoji);
    }
  }

  private emojiForState(state: FeedbackState): string | null {
    switch (state) {
      case "processing":
        return this.processingEmoji;
      case "tools":
        return this.toolsEmoji;
      case "done":
        return this.doneEmoji;
      default:
        return null;
    }
  }

  private async removeCurrentReaction(): Promise<void> {
    const emoji = this.emojiForState(this.state);
    if (emoji) {
      await this.removeReaction(emoji);
    }
    this.state = "idle";
  }

  private async addReaction(emoji: string): Promise<void> {
    try {
      const encoded = normalizeReactionEmoji(emoji);
      await this.rest.put(
        Routes.channelMessageOwnReaction(this.channelId, this.messageId, encoded),
      );
    } catch {
      // Never block agent processing
    }
  }

  private async removeReaction(emoji: string): Promise<void> {
    try {
      const encoded = normalizeReactionEmoji(emoji);
      await this.rest.delete(
        Routes.channelMessageOwnReaction(this.channelId, this.messageId, encoded),
      );
    } catch {
      // Never block agent processing
    }
  }

  // ── Status messages ─────────────────────────────────────────────

  private startStatusTimer(): void {
    if (!this.statusEnabled || this.sealed) {
      return;
    }
    this.statusTimer = setTimeout(() => {
      void this.sendStatusMessage(this.statusInitialText);
    }, this.statusDelaySeconds * 1000);
  }

  private async sendStatusMessage(text: string): Promise<void> {
    if (this.sealed) {
      return;
    }
    try {
      const body: Record<string, unknown> = {
        content: `> ${text}`,
        message_reference: {
          message_id: this.messageId,
          fail_if_not_exists: false,
        },
      };
      const res = (await this.rest.post(Routes.channelMessages(this.channelId), {
        body,
      })) as { id: string };
      this.statusMessageId = res.id;
    } catch {
      // Never block agent processing
    }
  }

  private updateStatusWithTool(toolName?: string): void {
    if (!this.statusEnabled || !this.statusMessageId || this.sealed) {
      return;
    }
    const displayName = toolName ?? "a tool";
    const text = this.statusToolTemplate.replace("{tool}", displayName);
    void this.editStatusMessage(text);
  }

  private async editStatusMessage(text: string): Promise<void> {
    if (!this.statusMessageId) {
      return;
    }
    try {
      await this.rest.patch(Routes.channelMessage(this.channelId, this.statusMessageId), {
        body: { content: `> ${text}` },
      });
    } catch {
      // Never block agent processing
    }
  }

  private cleanupStatus(): void {
    if (this.statusTimer) {
      clearTimeout(this.statusTimer);
      this.statusTimer = null;
    }
    if (this.statusDeleteAfterReply && this.statusMessageId) {
      void this.deleteStatusMessage();
    }
  }

  private async deleteStatusMessage(): Promise<void> {
    const msgId = this.statusMessageId;
    if (!msgId) {
      return;
    }
    this.statusMessageId = null;
    try {
      await this.rest.delete(Routes.channelMessage(this.channelId, msgId));
    } catch {
      // Never block agent processing
    }
  }

  // ── Done reaction auto-removal ──────────────────────────────────

  private scheduleDoneRemoval(): void {
    if (!this.reactionsEnabled || this.doneRemoveAfterSeconds <= 0) {
      return;
    }
    this.doneRemoveTimer = setTimeout(() => {
      void this.removeReaction(this.doneEmoji);
    }, this.doneRemoveAfterSeconds * 1000);
  }

  // ── Lifecycle seal ──────────────────────────────────────────────

  private seal(): void {
    this.sealed = true;
    if (this.statusTimer) {
      clearTimeout(this.statusTimer);
      this.statusTimer = null;
    }
  }
}
