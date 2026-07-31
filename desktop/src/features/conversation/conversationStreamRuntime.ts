import type {
  ConversationDetail,
  ConversationStreamEvent,
} from "../../types/conversation";
import { getConversation, streamConversation } from "./conversationRepository";
import { isFollowableRun } from "./conversationState";
import { createStreamEventBatcher } from "./streamEventBatcher";
import {
  RunLifecycleController,
} from "./runLifecycleController";

export interface ConversationStreamAdapter {
  applyEvents: (events: ConversationStreamEvent[]) => void;
  loadSnapshot: (snapshot: ConversationDetail) => void;
}

export interface ConversationStreamDependencies {
  stream: typeof streamConversation;
  snapshot: typeof getConversation;
  wait: typeof waitForRetry;
}

const DEFAULT_DEPENDENCIES: ConversationStreamDependencies = {
  stream: streamConversation,
  snapshot: getConversation,
  wait: waitForRetry,
};

/**
 * Transport runtime for one active Run per conversation.
 *
 * Zustand remains a projection store: connection ownership, retries, batching
 * and authoritative snapshot recovery live here.
 */
export class ConversationStreamRuntime {
  readonly lifecycle = new RunLifecycleController();
  private readonly dependencies: ConversationStreamDependencies;

  constructor(dependencies: ConversationStreamDependencies = DEFAULT_DEPENDENCIES) {
    this.dependencies = dependencies;
  }

  stop(conversationId: string): void {
    this.lifecycle.stop(conversationId);
  }

  async follow(
    conversationId: string,
    runId: string,
    afterSequence: number,
    adapter: ConversationStreamAdapter,
  ): Promise<void> {
    const active = this.lifecycle.start(conversationId, runId);
    const batcher = createStreamEventBatcher<ConversationStreamEvent>(adapter.applyEvents);
    let cursor = afterSequence;
    let attempt = 0;
    try {
      while (this.lifecycle.isCurrent(active)) {
        try {
          cursor = await this.dependencies.stream(conversationId, {
            afterSequence: cursor,
            targetRunId: runId,
            signal: active.controller.signal,
            onEvent: (event) => {
              if (event.kind === "event") {
                cursor = Math.max(cursor, event.event.sequence);
              }
              batcher.push(event);
            },
          });
          attempt = 0;
        } catch (error) {
          if (!this.lifecycle.isCurrent(active) || isAbortError(error)) return;
          attempt += 1;
        }

        // Apply every live event before the authoritative snapshot so a queued
        // animation-frame callback cannot replay stale deltas over terminal state.
        batcher.flush();
        let snapshot: ConversationDetail;
        try {
          snapshot = await this.dependencies.snapshot(active.conversationId);
          if (!this.lifecycle.isCurrent(active)) return;
          adapter.loadSnapshot(snapshot);
        } catch {
          if (!this.lifecycle.isCurrent(active)) return;
          attempt += 1;
          await this.dependencies.wait(
            Math.min(4_000, 250 * (2 ** Math.min(attempt, 4))),
            active.controller.signal,
          );
          continue;
        }
        cursor = Math.max(cursor, snapshot.cursor || 0);
        const run = snapshot.runs.find((item) => item.id === runId);
        if (!run || !isFollowableRun(run.status)) return;
        await this.dependencies.wait(
          Math.min(4_000, 250 * (2 ** Math.min(attempt, 4))),
          active.controller.signal,
        );
      }
    } finally {
      batcher.cancel();
      this.lifecycle.finish(active);
    }
  }

}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export function waitForRetry(duration: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) {
      resolve();
      return;
    }
    const finish = () => {
      globalThis.clearTimeout(timer);
      signal.removeEventListener("abort", finish);
      resolve();
    };
    const timer = globalThis.setTimeout(finish, duration);
    signal.addEventListener("abort", finish, { once: true });
  });
}

export const conversationStreamRuntime = new ConversationStreamRuntime();
