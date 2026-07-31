import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useConversationStore } from "../../../../stores/conversationStore";
import { useConversationViewModel } from "../useConversationViewModel";

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe("useConversationViewModel", () => {
  const originalState = useConversationStore.getState();

  afterEach(() => {
    cleanup();
    useConversationStore.setState(originalState, true);
  });

  it("reuses one idempotency key for an uncertain retry and rotates it after success", async () => {
    const sendMessage = vi.fn()
      .mockRejectedValueOnce(new Error("response was lost"))
      .mockResolvedValue(undefined);
    useConversationStore.setState({ sendMessage });
    const { result } = renderHook(
      () => useConversationViewModel("conversation-1"),
      { wrapper: createWrapper() },
    );

    await act(async () => {
      await expect(
        result.current.sendMessage("conversation-1", "分析订单", "queue"),
      ).rejects.toThrow("response was lost");
    });
    await act(async () => {
      await result.current.sendMessage("conversation-1", "分析订单", "queue");
    });
    await act(async () => {
      await result.current.sendMessage("conversation-1", "分析订单", "queue");
    });

    expect(sendMessage).toHaveBeenCalledTimes(3);
    expect(sendMessage.mock.calls[1][3]).toBe(sendMessage.mock.calls[0][3]);
    expect(sendMessage.mock.calls[2][3]).not.toBe(sendMessage.mock.calls[1][3]);
  });
});
