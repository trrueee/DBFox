export interface ActiveRunLifecycle {
  conversationId: string;
  runId: string;
  controller: AbortController;
}

/** Owns transport cancellation independently from application state. */
export class RunLifecycleController {
  private readonly active = new Map<string, ActiveRunLifecycle>();

  start(conversationId: string, runId: string): ActiveRunLifecycle {
    this.stop(conversationId);
    const lifecycle = {
      conversationId,
      runId,
      controller: new AbortController(),
    };
    this.active.set(conversationId, lifecycle);
    return lifecycle;
  }

  stop(conversationId: string): void {
    this.active.get(conversationId)?.controller.abort();
    this.active.delete(conversationId);
  }

  finish(lifecycle: ActiveRunLifecycle): void {
    if (this.active.get(lifecycle.conversationId) === lifecycle) {
      this.active.delete(lifecycle.conversationId);
    }
  }

  isCurrent(lifecycle: ActiveRunLifecycle): boolean {
    return (
      this.active.get(lifecycle.conversationId) === lifecycle
      && !lifecycle.controller.signal.aborted
    );
  }

  get(conversationId: string): ActiveRunLifecycle | undefined {
    return this.active.get(conversationId);
  }
}
