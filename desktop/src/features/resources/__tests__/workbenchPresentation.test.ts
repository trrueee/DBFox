import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  acknowledgeWorkbenchPresentationApiV1ConversationsConversationIdWorkbenchPresentationsInvocationIdReceiptPost as acknowledgePresentation,
  claimWorkbenchPresentationApiV1ConversationsConversationIdWorkbenchPresentationsInvocationIdClaimPost as claimPresentation,
} from "../../../lib/api/generated/sdk.gen";
import type { WorkbenchPresentation } from "../../../lib/api/generated/types.gen";
import { selectActiveWorkbench, useWorkspaceStore } from "../../../stores/workspaceStore";
import type { FunctionCallItem } from "../../../types/conversation";
import { applyWorkbenchPresentation, useWorkbenchPresentation } from "../workbenchPresentation";

vi.mock("../../../lib/api/generated/sdk.gen", async (original) => ({
  ...await original<typeof import("../../../lib/api/generated/sdk.gen")>(),
  acknowledgeWorkbenchPresentationApiV1ConversationsConversationIdWorkbenchPresentationsInvocationIdReceiptPost: vi.fn(),
  claimWorkbenchPresentationApiV1ConversationsConversationIdWorkbenchPresentationsInvocationIdClaimPost: vi.fn(),
}));

const request = (): WorkbenchPresentation => ({
  project_id: "project-1", conversation_id: "chat-1", invocation_id: "open-1",
  artifact_id: "result-1", title: "Report", expires_at_ms: Date.now() + 10_000,
});

const claimResult = () => ({
  data: request(), request: new Request("http://localhost/claim"), response: new Response(),
});

const runningCall: FunctionCallItem = {
  id: "open-1", type: "function_call", session_id: "chat-1", run_id: "run-1",
  sequence: 1, revision: 1, status: "in_progress", created_at: "2026-11-10T00:00:00Z",
  payload: { call_id: "open", name: "workbench_open_artifact", tool_version: "1", arguments: {}, attempt: 1,
    presentation: { title: "Open", category: "explore", visibility: "summary", progress: "none" } },
};

describe("Workbench presentation", () => {
  beforeEach(() => {
    cleanup();
    useWorkspaceStore.setState({ activeProjectId: "project-1", mainSurfaceByProject: {}, workbenchByConversation: {} });
    useWorkspaceStore.getState().setProjectActiveConversation("project-1", "chat-1");
    vi.resetAllMocks();
  });

  it("acknowledges only after the native Dock selects the exact artifact", async () => {
    vi.mocked(claimPresentation).mockResolvedValue(claimResult());
    vi.mocked(acknowledgePresentation).mockImplementation(async () => {
      const state = selectActiveWorkbench(useWorkspaceStore.getState());
      expect(state.open).toBe(true);
      expect(state.activeViewKey).toBe("core.artifact:result-1");
      return { data: undefined, request: new Request("http://localhost/receipt"), response: new Response(null, { status: 204 }) };
    });
    renderHook(() => useWorkbenchPresentation("chat-1", "run-1", [runningCall]));

    await waitFor(() => expect(acknowledgePresentation).toHaveBeenCalledWith(expect.objectContaining({
      path: { conversation_id: "chat-1", invocation_id: "open-1" }, body: { outcome: "opened" },
    })));
    expect(claimPresentation).toHaveBeenCalledTimes(1);
  });

  it("leaves a different conversation and an expired scope untouched", () => {
    const scope = useWorkspaceStore.getState().ensureActiveWorkbenchScope();
    expect(applyWorkbenchPresentation({ ...request(), expires_at_ms: 0 }, scope)).toBe("not_opened");
    useWorkspaceStore.getState().setProjectActiveConversation("project-1", "chat-2");
    expect(applyWorkbenchPresentation(request(), scope)).toBe("not_opened");
    expect(selectActiveWorkbench(useWorkspaceStore.getState()).tabs).toEqual([]);
  });

  it("ignores a claim response after switching away and back during delivery", async () => {
    type ClaimResult = ReturnType<typeof claimResult>;
    let resolveClaim!: (result: ClaimResult) => void;
    vi.mocked(claimPresentation).mockReturnValue(new Promise<ClaimResult>((resolve) => { resolveClaim = resolve; }));
    renderHook(() => useWorkbenchPresentation("chat-1", "run-1", [runningCall]));
    await waitFor(() => expect(claimPresentation).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(claimPresentation).mock.calls[0][0].signal;

    await act(async () => {
      useWorkspaceStore.getState().setProjectActiveConversation("project-1", "chat-2");
      useWorkspaceStore.getState().setProjectActiveConversation("project-1", "chat-1");
      resolveClaim(claimResult());
    });

    expect(signal?.aborted).toBe(true);
    expect(selectActiveWorkbench(useWorkspaceStore.getState()).tabs).toEqual([]);
    expect(acknowledgePresentation).not.toHaveBeenCalled();
  });
});
