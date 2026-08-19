import { beforeEach, describe, expect, it, vi } from "vitest";
import { useGithubStore } from "../githubStore";
import { githubApi } from "../../../lib/api/github";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import type { GithubBindingResponse } from "../../../lib/api/generated/types.gen";

vi.mock("../../../lib/api/github", () => ({
  githubApi: {
    listBindings: vi.fn(),
    createBinding: vi.fn(),
    deleteBinding: vi.fn(),
    refreshBinding: vi.fn(),
    listFiles: vi.fn(),
    readFile: vi.fn(),
  },
}));

describe("Github Store", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useGithubStore.setState({
      bindingsByProject: {},
      activeBindingIdByProject: {},
      loadingByProject: {},
      errorByProject: {},
      fileStateByKey: {},
    });
    useWorkspaceStore.setState({
      activeProjectId: "proj-1",
      dock: { open: true, activeViewKey: null },
      dockTabs: [],
    });
  });

  const mockBinding: GithubBindingResponse = {
    id: "gh-bind-1",
    project_id: "proj-1",
    owner: "astral-sh",
    repository: "uv",
    ref_name: "main",
    resolved_revision: "abcdef1234567890abcdef1234567890abcdef12",
    default_branch: "main",
    created_at: "2026-08-19T00:00:00Z",
    updated_at: "2026-08-19T00:00:00Z",
  };

  it("loads bindings and sets the first one active if none was active", async () => {
    vi.mocked(githubApi.listBindings).mockResolvedValue([mockBinding]);

    const result = await useGithubStore.getState().loadBindings("proj-1");
    expect(result).toHaveLength(1);
    expect(useGithubStore.getState().bindingsByProject["proj-1"]).toEqual([mockBinding]);
    expect(useGithubStore.getState().activeBindingIdByProject["proj-1"]).toBe("gh-bind-1");
  });

  it("adds a binding and sets it active", async () => {
    vi.mocked(githubApi.createBinding).mockResolvedValue(mockBinding);

    const added = await useGithubStore.getState().addBinding("proj-1", "astral-sh/uv", "main");
    expect(added.id).toBe("gh-bind-1");
    expect(useGithubStore.getState().bindingsByProject["proj-1"]).toEqual([mockBinding]);
    expect(useGithubStore.getState().activeBindingIdByProject["proj-1"]).toBe("gh-bind-1");
  });

  it("refreshes a binding and updates state", async () => {
    useGithubStore.setState({
      bindingsByProject: { "proj-1": [mockBinding] },
    });
    const refreshedBinding: GithubBindingResponse = {
      ...mockBinding,
      resolved_revision: "9999999999999999999999999999999999999999",
    };
    vi.mocked(githubApi.refreshBinding).mockResolvedValue(refreshedBinding);

    const result = await useGithubStore.getState().refreshBinding("proj-1", "gh-bind-1");
    expect(result.resolved_revision).toBe("9999999999999999999999999999999999999999");
    expect(
      useGithubStore.getState().bindingsByProject["proj-1"][0].resolved_revision,
    ).toBe("9999999999999999999999999999999999999999");
  });

  it("deletes a binding and updates active state", async () => {
    useGithubStore.setState({
      bindingsByProject: { "proj-1": [mockBinding] },
      activeBindingIdByProject: { "proj-1": "gh-bind-1" },
    });
    vi.mocked(githubApi.deleteBinding).mockResolvedValue();

    await useGithubStore.getState().deleteBinding("proj-1", "gh-bind-1");
    expect(useGithubStore.getState().bindingsByProject["proj-1"]).toHaveLength(0);
    expect(useGithubStore.getState().activeBindingIdByProject["proj-1"]).toBeNull();
  });

  it("opens a github file dock tab with canonical viewKey and envelope", () => {
    useGithubStore.getState().openGithubFile({
      projectId: "proj-1",
      bindingId: "gh-bind-1",
      owner: "astral-sh",
      repository: "uv",
      revision: "abcdef1234567890abcdef1234567890abcdef12",
      filePath: "README.md",
      fileName: "README.md",
    });

    const expectedViewKey = "dbfox.github.file:gh-bind-1:abcdef1234567890abcdef1234567890abcdef12:README.md";
    const tabs = useWorkspaceStore.getState().dockTabs;
    expect(tabs).toHaveLength(1);
    expect(tabs[0].viewKey).toBe(expectedViewKey);
    expect(tabs[0].viewType).toBe("dbfox.github.file");
    expect(tabs[0].target).toEqual({
      type: "resource",
      kind: "github.repository",
      id: "gh-bind-1",
    });

    const fileState = useGithubStore.getState().fileStateByKey[expectedViewKey];
    expect(fileState).toBeDefined();
    expect(fileState.filePath).toBe("README.md");
    expect(fileState.owner).toBe("astral-sh");
  });
});
