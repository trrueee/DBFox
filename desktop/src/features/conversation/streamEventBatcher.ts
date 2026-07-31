export interface StreamEventBatcher<T> {
  push: (event: T) => void;
  flush: () => void;
  cancel: () => void;
}

export function createStreamEventBatcher<T>(consume: (events: T[]) => void): StreamEventBatcher<T> {
  let queue: T[] = [];
  let scheduledHandle: number | null = null;

  const schedule =
    typeof window !== "undefined" && typeof window.requestAnimationFrame === "function"
      ? window.requestAnimationFrame.bind(window)
      : (callback: FrameRequestCallback) => globalThis.setTimeout(() => callback(Date.now()), 16);
  const cancelSchedule =
    typeof window !== "undefined" && typeof window.cancelAnimationFrame === "function"
      ? window.cancelAnimationFrame.bind(window)
      : (handle: number) => globalThis.clearTimeout(handle);

  const drain = () => {
    scheduledHandle = null;
    if (queue.length === 0) return;
    const batch = queue;
    queue = [];
    consume(batch);
  };

  const flush = () => {
    if (scheduledHandle !== null) cancelSchedule(scheduledHandle);
    drain();
  };

  return {
    push: (event: T) => {
      queue.push(event);
      if (scheduledHandle !== null) return;
      scheduledHandle = schedule(drain);
    },
    flush,
    cancel: () => {
      if (scheduledHandle !== null) cancelSchedule(scheduledHandle);
      scheduledHandle = null;
      queue = [];
    },
  };
}
