import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useWorkspaceStore, selectActiveWorkbench, selectActiveWorkbenchReferences } from "../../../stores/workspaceStore";
import { useDlcStore } from "../../dlc/extensionStore";
import { useAttachmentInput } from "../useAttachmentInput";
import { ATTACHMENT_RESOURCE_KIND, attachmentCapabilities, uploadAttachment, removeStagedAttachment } from "../attachmentRepository";
import { openAttachmentDock } from "../attachmentDock";
import { pickDesktopFile, readDesktopPickedFile } from "../../../lib/desktopHost";

vi.mock("../../../lib/desktopHost", () => ({ pickDesktopFile: vi.fn(), readDesktopPickedFile: vi.fn() }));
vi.mock("../attachmentRepository", () => ({ ATTACHMENT_RESOURCE_KIND: "dbfox.core.attachment",
  attachmentCapabilities: vi.fn(), uploadAttachment: vi.fn(), removeStagedAttachment: vi.fn() }));

const file = { id: "att_" + "a".repeat(32), session_id: "s1", display_name: "orders.xlsx", media_type: "application/octet-stream",
  byte_count: 3, content_sha256: "f".repeat(64), created_at: "2026-10-27T10:00:00Z", first_input_id: null, first_input_sequence: null, available: true };
const ensure = vi.fn(async () => { useWorkspaceStore.getState().setDraftConversationId("s1"); return "s1"; });
afterEach(cleanup);

function Harness() {
  const refs = useWorkspaceStore(selectActiveWorkbenchReferences);
  const task = useAttachmentInput(ensure, refs);
  return <div><input aria-label="question" defaultValue="分析这份订单" /><button onClick={() => void task.add()}>add</button>
    <button onClick={() => void task.retry()}>retry</button>{task.error && <p role="alert">{task.error}</p>}
    <span>{refs.length}</span></div>;
}

beforeEach(() => {
  vi.clearAllMocks();
  useWorkspaceStore.setState({ activeProjectId: "p1", mainSurfaceByProject: { p1: { kind: "new-conversation" } }, workbenchByConversation: {} });
  useWorkspaceStore.getState().ensureActiveWorkbenchScope();
  useDlcStore.setState({ contributions: { connectors: [], artifactViews: [], dockViews: [{
    viewType: "test.workbook", attachmentExtensions: ["xlsx"], icon: () => null, render: () => null,
    resolveTitle: view => view.title, isVisible: () => true,
  }] } });
  vi.mocked(attachmentCapabilities).mockResolvedValue({ max_file_bytes: 4096, max_session_files: 10, max_session_bytes: 100_000 });
  vi.mocked(pickDesktopFile).mockResolvedValue({ name: "orders.xlsx", path: "D:/fixture/orders.xlsx", sizeBytes: 3, modifiedAtUnix: 1 });
  vi.mocked(readDesktopPickedFile).mockResolvedValue(new Uint8Array([1, 2, 3]));
  vi.mocked(uploadAttachment).mockResolvedValue(file);
  vi.mocked(removeStagedAttachment).mockResolvedValue();
});

describe("conversation attachment input", () => {
  it("uploads once with server limits, preserves the question, and opens the exact version in its scope", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("add"));
    await waitFor(() => expect(selectActiveWorkbenchReferences(useWorkspaceStore.getState())).toHaveLength(1));
    expect(pickDesktopFile).toHaveBeenCalledWith({ title: "添加对话文件", filters: [{ name: "支持的文件", extensions: ["xlsx"] }], maxBytes: 4096 });
    expect((screen.getByLabelText("question") as HTMLInputElement).value).toBe("分析这份订单");
    const reference = selectActiveWorkbenchReferences(useWorkspaceStore.getState())[0];
    expect(reference.object).toEqual({ kind: ATTACHMENT_RESOURCE_KIND, id: file.id, version: file.content_sha256 });
    act(() => { openAttachmentDock(reference, "s1"); openAttachmentDock(reference, "s1"); });
    const bench = selectActiveWorkbench(useWorkspaceStore.getState());
    expect(bench.tabs).toHaveLength(1);
    expect(bench.tabs[0]).toMatchObject({ sessionId: "s1", target: { type: "object", object: reference.object } });
    act(() => useWorkspaceStore.getState().promoteDraftWorkbenchToConversation("p1", "s1"));
    act(() => useWorkspaceStore.getState().setProjectActiveConversation("p1", "s1"));
    expect(selectActiveWorkbench(useWorkspaceStore.getState()).scopeId).toBe(bench.scopeId);
  });

  it("cancelled selection does not create a conversation or consume a read grant", async () => {
    vi.mocked(pickDesktopFile).mockResolvedValue(null);
    render(<Harness />); fireEvent.click(screen.getByText("add"));
    await waitFor(() => expect(pickDesktopFile).toHaveBeenCalled());
    expect(ensure).not.toHaveBeenCalled(); expect(readDesktopPickedFile).not.toHaveBeenCalled();
  });

  it("explicit upload retry reuses the same bytes/key and never rereads a consumed native grant", async () => {
    vi.mocked(uploadAttachment).mockRejectedValueOnce(new Error("网络中断"));
    render(<Harness />); fireEvent.click(screen.getByText("add"));
    await screen.findByRole("alert"); fireEvent.click(screen.getByText("retry"));
    await waitFor(() => expect(selectActiveWorkbenchReferences(useWorkspaceStore.getState())).toHaveLength(1));
    expect(readDesktopPickedFile).toHaveBeenCalledTimes(1);
    const calls = vi.mocked(uploadAttachment).mock.calls;
    expect(calls[1].slice(0, 4)).toEqual(calls[0].slice(0, 4));
  });

  it("ignores a late response after a project switch", async () => {
    let resolve!: (value: typeof file) => void;
    vi.mocked(uploadAttachment).mockReturnValue(new Promise(done => { resolve = done; }));
    render(<Harness />); fireEvent.click(screen.getByText("add"));
    await waitFor(() => expect(uploadAttachment).toHaveBeenCalled());
    act(() => useWorkspaceStore.getState().setActiveProject("p2"));
    await act(async () => resolve(file));
    expect(selectActiveWorkbenchReferences(useWorkspaceStore.getState())).toEqual([]);
    expect(Object.values(useWorkspaceStore.getState().workbenchByConversation).every(bench => bench.references.length === 0)).toBe(true);
  });

  it("refuses a second draft file and rejects opening another conversation's reference", async () => {
    act(() => useWorkspaceStore.getState().addWorkbenchReference({ label: file.display_name, object: { kind: ATTACHMENT_RESOURCE_KIND, id: file.id, version: file.content_sha256 } }));
    render(<Harness />); fireEvent.click(screen.getByText("add"));
    await screen.findByText("每条消息可添加一份文件，请先移除当前文件。");
    expect(pickDesktopFile).not.toHaveBeenCalled();
    expect(() => openAttachmentDock(selectActiveWorkbenchReferences(useWorkspaceStore.getState())[0], "foreign-session")).toThrow("会话已切换");
  });

  it("takes accepted formats from the registered preview contribution", async () => {
    const state = useDlcStore.getState();
    useDlcStore.setState({ contributions: { ...state.contributions,
      dockViews: state.contributions.dockViews.map(view => ({ ...view, attachmentExtensions: ["pdf"] })) } });
    vi.mocked(pickDesktopFile).mockResolvedValue({ name: "document.pdf", path: "D:/fixture/document.pdf", sizeBytes: 3, modifiedAtUnix: 1 });
    vi.mocked(uploadAttachment).mockResolvedValue({ ...file, display_name: "document.pdf" });
    render(<Harness />); fireEvent.click(screen.getByText("add"));
    await waitFor(() => expect(uploadAttachment).toHaveBeenCalled());
    expect(vi.mocked(pickDesktopFile).mock.calls[0][0]?.filters?.[0].extensions).toEqual(["pdf"]);
  });
});
