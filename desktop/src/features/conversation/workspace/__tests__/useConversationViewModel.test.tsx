import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
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

  it("reconciles the authoritative snapshot after an approval conflict without replaying the decision", async () => {
    const conflict = new Error("Approval is no longer pending");
    const resolveApproval = vi.fn().mockRejectedValue(conflict);
    const openConversation = vi.fn().mockResolvedValue(undefined);
    useConversationStore.setState({ resolveApproval, openConversation });
    const { result } = renderHook(
      () => useConversationViewModel("conversation-1"),
      { wrapper: createWrapper() },
    );

    await act(async () => {
      await expect(
        result.current.resolveApproval("run-1", "approval-1", true),
      ).rejects.toBe(conflict);
    });

    expect(resolveApproval).toHaveBeenCalledTimes(1);
    expect(openConversation).toHaveBeenCalledWith("conversation-1");
  });

  it("reconciles the authoritative snapshot after a question conflict without replaying the answer", async () => {
    const conflict = new Error("Question is no longer pending");
    const resolveQuestion = vi.fn().mockRejectedValue(conflict);
    const openConversation = vi.fn().mockResolvedValue(undefined);
    useConversationStore.setState({ resolveQuestion, openConversation });
    const { result } = renderHook(
      () => useConversationViewModel("conversation-1"),
      { wrapper: createWrapper() },
    );

    await act(async () => {
      await expect(
        result.current.resolveQuestion("run-1", "question-1", { text: "按自然月" }),
      ).rejects.toBe(conflict);
    });

    expect(resolveQuestion).toHaveBeenCalledTimes(1);
    expect(openConversation).toHaveBeenCalledWith("conversation-1");
  });

  it("uses the existing bounded history action and surfaces a retryable error", async () => {
    const historyError = new Error("history offline");
    const loadOlderHistory = vi.fn().mockRejectedValue(historyError);
    useConversationStore.setState({ loadOlderHistory });
    const { result } = renderHook(
      () => useConversationViewModel("conversation-1"),
      { wrapper: createWrapper() },
    );

    await act(async () => {
      await expect(result.current.loadOlderHistory()).rejects.toThrow("history offline");
    });

    expect(loadOlderHistory).toHaveBeenCalledWith("conversation-1");
    await waitFor(() => expect(result.current.historyLoadError).toBe(historyError));
    expect(result.current.loadingOlderHistory).toBe(false);
  });
});
