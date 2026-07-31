import { afterEach, describe, expect, it, vi } from "vitest";
import { createStreamEventBatcher } from "../streamEventBatcher";

afterEach(() => {
  vi.useRealTimers();
});

describe("createStreamEventBatcher", () => {
  it("flushes queued events synchronously before a terminal snapshot is loaded", () => {
    vi.useFakeTimers();
    const consumed: number[][] = [];
    const batcher = createStreamEventBatcher<number>((events) => consumed.push(events));

    batcher.push(1);
    batcher.push(2);
    expect(consumed).toEqual([]);

    batcher.flush();
    expect(consumed).toEqual([[1, 2]]);

    vi.runAllTimers();
    expect(consumed).toEqual([[1, 2]]);
  });

  it("cancels stale events when a follower is replaced", () => {
    vi.useFakeTimers();
    const consumed: number[][] = [];
    const batcher = createStreamEventBatcher<number>((events) => consumed.push(events));

    batcher.push(1);
    batcher.cancel();
    vi.runAllTimers();

    expect(consumed).toEqual([]);
  });
});
