export function createStreamEventBatcher<T>(flush: (events: T[]) => void) {
  let queue: T[] = [];
  let scheduled = false;

  const schedule =
    typeof window !== "undefined" && typeof window.requestAnimationFrame === "function"
      ? window.requestAnimationFrame.bind(window)
      : (callback: FrameRequestCallback) => globalThis.setTimeout(() => callback(Date.now()), 16);

  return (event: T) => {
    queue.push(event);
    if (scheduled) return;
    scheduled = true;
    schedule(() => {
      scheduled = false;
      const batch = queue;
      queue = [];
      flush(batch);
    });
  };
}
