import { act, cleanup, render, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useConversationStore } from "../../../stores/conversationStore";
import { getActiveWorkbenchKey, selectActiveWorkbench, useWorkspaceStore } from "../../../stores/workspaceStore";
import type { ConversationDetail } from "../../../types/conversation";
import { ConversationCenter } from "../ConversationCenter";

const controls = vi.hoisted(() => ({
  home: null as Record<string, unknown> | null,
  ensureAttachment: null as (() => Promise<string>) | null,
  openComputer: null as (() => Promise<void>) | null,
  openedComputer: vi.fn(),
}));
vi.mock("../../workspace/SmartQueryHome", () => ({
  SmartQueryHome: (props: Record<string, unknown>) => {
    controls.home = props;
    return <>{props.context as ReactNode}{props.feedback as ReactNode}</>;
  },
}));
vi.mock("../../conversation/workspace/ConversationWorkspace", () => ({ ConversationWorkspace: () => null }));
vi.mock("../../conversation/workspace/ComposerContext", () => ({
  ComposerContext: ({ onOpenComputer }: { onOpenComputer: () => Promise<void> }) => {
    controls.openComputer = onOpenComputer;
    return null;
  },
}));
vi.mock("../../computer/openComputerDock", () => ({ openComputerDock: controls.openedComputer }));
vi.mock("../../conversation/useAttachmentInput", () => ({
  useAttachmentInput: (ensure: () => Promise<string>) => {
    controls.ensureAttachment = ensure;
    return { busy: false, add: vi.fn(), retry: vi.fn(), remove: vi.fn() };
  },
}));

function barrier() {
  let release!: () => void;
  const promise = new Promise<void>((resolve) => { release = resolve; });
  return { promise, release };
}
const conversation = (id: string): ConversationDetail => ({
  protocol_version: 2, id, title: "Draft fixture", resource_intents: [], runs: [], items: [],
});
const original = {
  createAndOpenConversation: useConversationStore.getState().createAndOpenConversation,
  sendMessage: useConversationStore.getState().sendMessage,
};

describe("draft conversation ownership", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    controls.home = null;
    controls.ensureAttachment = null;
    controls.openComputer = null;
    useWorkspaceStore.setState({ activeProjectId: "one", mainSurfaceByProject: {}, workbenchByConversation: {}, centerMode: "home", pendingAsk: null });
    useWorkspaceStore.getState().setDraftInput("统计订单");
    useConversationStore.setState(original);
  });
  afterEach(() => { cleanup(); useConversationStore.setState(original); });

  it("shares one pending creation across attachment, computer and send", async () => {
    const ready = barrier();
    let sequence = 0;
    const create = vi.fn(async () => { const id = `conversation-${++sequence}`; await ready.promise; return conversation(id); });
    const send = vi.fn().mockResolvedValue(undefined);
    useConversationStore.setState({ createAndOpenConversation: create, sendMessage: send });
    render(<ConversationCenter onNewProject={vi.fn()} />);
    let attachment!: Promise<string>;
    let computer!: Promise<void>;
    await act(async () => {
      attachment = controls.ensureAttachment!();
      computer = controls.openComputer!();
      (controls.home!.onSubmitAsk as () => void)();
    });
    try {
      expect(create).toHaveBeenCalledTimes(1);
      await act(async () => { ready.release(); await Promise.all([attachment, computer]); });
      expect(await attachment).toBe("conversation-1");
      await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
      expect(send.mock.calls[0][0]).toBe("conversation-1");
      expect(controls.openedComputer).toHaveBeenCalledWith("conversation-1");
    } finally {
      ready.release();
      await act(async () => { await Promise.allSettled([attachment, computer]); });
    }
  });

  it("binds a late creation to its captured draft without opening the new project's dock", async () => {
    const ready = barrier();
    const create = vi.fn(async () => { await ready.promise; return conversation("original-conversation"); });
    useConversationStore.setState({ createAndOpenConversation: create });
    const originalKey = getActiveWorkbenchKey(useWorkspaceStore.getState());
    render(<ConversationCenter onNewProject={vi.fn()} />);
    const pending = controls.openComputer!();
    const settled = pending.catch(() => undefined);
    await act(async () => {
      useWorkspaceStore.getState().setActiveProject("two");
      useWorkspaceStore.getState().setDraftInput("另一个项目的草稿");
      ready.release();
      await settled;
    });
    expect(controls.openedComputer).not.toHaveBeenCalled();
    expect(selectActiveWorkbench(useWorkspaceStore.getState()).draftInput).toBe("另一个项目的草稿");
    expect(selectActiveWorkbench(useWorkspaceStore.getState()).draftConversationId).toBeUndefined();
    expect(useWorkspaceStore.getState().workbenchByConversation[originalKey].draftConversationId).toBe("original-conversation");
  });

  it("can retry creation after a rejected request in the same draft", async () => {
    const create = vi.fn<typeof original.createAndOpenConversation>().mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(conversation("retried"));
    useConversationStore.setState({ createAndOpenConversation: create });
    render(<ConversationCenter onNewProject={vi.fn()} />);
    await act(async () => { await expect(controls.ensureAttachment!()).rejects.toThrow("offline"); });
    await act(async () => { expect(await controls.ensureAttachment!()).toBe("retried"); });
    expect(create).toHaveBeenCalledTimes(2);
    expect(selectActiveWorkbench(useWorkspaceStore.getState()).draftConversationId).toBe("retried");
  });
});
