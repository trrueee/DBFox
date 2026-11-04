import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ComposerContext } from "../ComposerContext";
import { getStoredApiConfig, saveStoredApiConfig } from "../../../../lib/llmConfig";
import { useWorkspaceStore } from "../../../../stores/workspaceStore";

const models = vi.hoisted(() => vi.fn());
vi.mock("../../../../lib/api/agent", () => ({ listLlmModels: models }));
vi.mock("../../../projects/useProjectState", () => ({ useProjectState: (id: string) => {
  const projects = [{ id: "p1", name: "DBFox" }, { id: "p2", name: "Research" }];
  return { projects, activeProject: projects.find(p => p.id === id) };
} }));
let client: QueryClient;
beforeEach(() => {
  localStorage.clear();
  models.mockReset().mockResolvedValue({ ok: true, models: [{ id: "model-new" }] });
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  useWorkspaceStore.setState({ activeProjectId: "p1", workbenchByConversation: {}, mainSurfaceByProject: {} });
  saveStoredApiConfig({ credentialId: "vault-reference", apiBase: "https://example.test/v1", modelName: "model-old" });
});
afterEach(() => { cleanup(); client.clear(); localStorage.clear(); });
function renderContext() { return render(<QueryClientProvider client={client}><ComposerContext /></QueryClientProvider>); }
function open(name: RegExp) { fireEvent.pointerDown(screen.getByRole("button", { name }), { button: 0, ctrlKey: false, pointerType: "mouse" }); }

describe("composer project and model context", () => {
  it("fetches model options only when opened and saves the model without copying credentials", async () => {
    renderContext();
    expect(models).not.toHaveBeenCalled();
    open(/当前模型/);
    fireEvent.click(await screen.findByRole("menuitem", { name: "model-new" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "当前模型：model-new" })).toBeInTheDocument());
    expect(models).toHaveBeenCalledWith("vault-reference", "https://example.test/v1");
    expect(getStoredApiConfig()).toEqual({ credentialId: "vault-reference", apiBase: "https://example.test/v1", modelName: "model-new" });
    expect(localStorage.getItem("dbfox-api-config")).not.toContain("apiKey");
  });
  it("switches projects through the existing shell and keeps each in-memory draft", async () => {
    useWorkspaceStore.getState().setDraftInput("project one draft");
    renderContext();
    open(/当前项目/);
    fireEvent.click(await screen.findByRole("menuitem", { name: "Research" }));
    expect(useWorkspaceStore.getState().activeProjectId).toBe("p2");
    useWorkspaceStore.getState().setDraftInput("project two draft");
    expect(useWorkspaceStore.getState().workbenchByConversation["draft:p1"].draftInput).toBe("project one draft");
    expect(models).not.toHaveBeenCalled();
  });
  it("observes configuration changes from the model settings screen", async () => {
    renderContext();
    act(() => saveStoredApiConfig({ credentialId: "vault-reference", apiBase: "https://example.test/v1", modelName: "changed-in-settings" }));
    expect(screen.getByRole("button", { name: "当前模型：changed-in-settings" })).toBeInTheDocument();
  });
});
