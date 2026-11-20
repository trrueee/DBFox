import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ComputerDock } from "../ComputerDock";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import type { ComputerGrant } from "../../../lib/api/generated/types.gen";

const api = vi.hoisted(() => ({ list: vi.fn(), targets: vi.fn(), share: vi.fn(), stop: vi.fn(), preview: vi.fn() }));
vi.mock("../../../lib/api/computer", () => ({
  COMPUTER_RESOURCE_KIND: "dbfox.computer.target",
  computerSharesQuery: (id: string) => ({ queryKey: ["computer-shares", id], queryFn: api.list, retry: false }),
  computerTargetsQuery: { queryKey: ["computer-targets"], queryFn: api.targets, retry: false },
  shareComputer: api.share, stopComputer: api.stop, previewComputer: api.preview,
  stopAllComputer: vi.fn(), readBrowserState: vi.fn(),
}));
vi.mock("../../../lib/desktopHost", () => ({ getDesktopEngineStatus: async () => ({ state: "ready", computerStopShortcut: false }) }));

const grant: ComputerGrant = {
  id: "computer_00000000000000000000000000000001", session_id: "s", version: "version-one", permission: "observe", status: "active",
  created_at: 1, expires_at: 9999999999999,
  target: { kind: "window", title: "Dedicated fixture window", executable: "C:/Fixture.exe", process_id: 42,
    process_started_at: 1, window_handle: "abc", include_owned_dialogs: true },
};
let client: QueryClient;
beforeEach(() => {
  vi.clearAllMocks();
  useWorkspaceStore.setState({ activeProjectId: "p", mainSurfaceByProject: { p: { kind: "conversation", conversationId: "s" } }, workbenchByConversation: {} });
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  api.list.mockResolvedValue([]);
  api.targets.mockResolvedValue([{ inventory_id: "fixture-target", target: grant.target }]);
  api.preview.mockRejectedValue(new Error("Fixture preview unavailable"));
});
afterEach(() => { cleanup(); client.clear(); });
function mount() { return render(<QueryClientProvider client={client}><ComputerDock conversationId="s" /></QueryClientProvider>); }

describe("computer sharing interaction", () => {
  it("requires an explicit window choice and defaults to observation only", async () => {
    api.share.mockResolvedValue(grant);
    api.list.mockResolvedValueOnce([]).mockResolvedValue([grant]);
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "共享窗口" }));
    expect((screen.getByRole("button", { name: "开始共享" }) as HTMLButtonElement).disabled).toBe(true);
    const selector = await screen.findByLabelText("共享目标");
    fireEvent.change(selector, { target: { value: "fixture-target" } });
    expect((screen.getByRole("radio", { name: /仅观察/ }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "开始共享" }));
    await waitFor(() => expect(api.share).toHaveBeenCalledWith("s", { inventory_id: "fixture-target", permission: "observe", duration_minutes: 15, replace_existing: false }));
    await screen.findByText("仅观察 · 无法点击或输入");
    expect(useWorkspaceStore.getState().workbenchByConversation.s.references[0].object).toEqual({ kind: "dbfox.computer.target", id: grant.id, version: "version-one" });
  });

  it("keeps the active state visible when a stop has not been acknowledged", async () => {
    api.list.mockResolvedValue([{ ...grant, permission: "control" }]);
    api.stop.mockRejectedValue(new Error("Stop not acknowledged"));
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "停止并接管" }));
    await waitFor(() => expect(api.stop).toHaveBeenCalledWith("s", grant.id, undefined));
    expect(await screen.findByText("停止未获确认，请重试。")).toBeTruthy();
    expect(screen.getByRole("button", { name: "停止并接管" })).toBeTruthy();
    expect(screen.getByText(/全局停止快捷键不可用/)).toBeTruthy();
  });

  it("shows a restored panel's acknowledged share without attaching it to another conversation", async () => {
    useWorkspaceStore.setState({ mainSurfaceByProject: { p: { kind: "conversation", conversationId: "other" } } });
    api.share.mockResolvedValue(grant);
    api.list.mockResolvedValueOnce([]).mockResolvedValue([grant]);
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "共享窗口" }));
    fireEvent.change(await screen.findByLabelText("共享目标"), { target: { value: "fixture-target" } });
    fireEvent.click(screen.getByRole("button", { name: "开始共享" }));
    await screen.findByText("仅观察 · 无法点击或输入");
    expect(screen.queryByRole("button", { name: "开始共享" })).toBeNull();
    expect(useWorkspaceStore.getState().workbenchByConversation.other?.references ?? []).toEqual([]);
    expect(useWorkspaceStore.getState().workbenchByConversation.s?.references ?? []).toEqual([]);
  });

  it("does not display or refresh a stopped target's old screenshot", async () => {
    api.list.mockResolvedValue([{ ...grant, status: "interrupted" }]);
    mount();
    await screen.findByText("当前没有可执行的共享");
    expect(api.preview).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "停止并接管" })).toBeNull();
    expect(screen.getByRole("button", { name: "重新共享" })).toBeTruthy();
  });
});
