import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ConnectorContext, ConnectorProjectResource } from "../../../../../sdk/frontend/index";
import { ProjectOverview } from "../ProjectOverview";

vi.mock("../useProjectState", () => ({
  useProjectState: () => ({
    activeProject: { id: "project-1", name: "Default Workspace", description: "" },
    loadingProjects: false,
    projectError: "",
    refreshProjects: vi.fn(),
  }),
}));
import { useDlcStore } from "../../dlc/extensionStore";
import { useWorkspaceStore } from "../../../stores/workspaceStore";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  useDlcStore.getState().reset();
});

function configureStores() {
  useWorkspaceStore.setState({
    activeProjectId: "project-1",
    mainSurfaceByProject: { "project-1": { kind: "project-overview" } },
  });
}

describe("ProjectOverview resource inventory", () => {
  it("lists per-DLC configured resources and removes through the DLC hook", async () => {
    configureStores();
    const entries: ConnectorProjectResource[] = [
      { kind: "dbfox.data.database", id: "db-1", name: "CreatorHub 主库", detail: "PostgreSQL · creatorhub · 主连接" },
    ];
    const listResources = vi.fn(async () => entries);
    const removeResource = vi.fn(async () => undefined);
    registerTestConnector({ id: "dbfox.data", listResources, removeResource });

    render(<ProjectOverview />);

    await waitFor(() => expect(screen.getByText("CreatorHub 主库")).toBeInTheDocument());
    expect(screen.getByText(/PostgreSQL · creatorhub/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "移除 CreatorHub 主库" }));

    await waitFor(() => expect(removeResource).toHaveBeenCalledTimes(1));
    expect(removeResource).toHaveBeenCalledWith(
      { projectId: "project-1" },
      expect.objectContaining({ id: "db-1" }),
    );
    // The inventory reloads after removal; the hook is asked again.
    await waitFor(() => expect(listResources).toHaveBeenCalledTimes(2));
  });

  it("keeps connectors without an inventory as configure-only rows", async () => {
    configureStores();
    registerTestConnector({ id: "dbfox.music" });

    render(<ProjectOverview />);

    expect(screen.getByText("音乐")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "配置" })).toBeInTheDocument();
    expect(screen.queryByText(/还没有配置资源/)).not.toBeInTheDocument();
  });

  it("surfaces inventory load failures without breaking the page", async () => {
    configureStores();
    registerTestConnector({
      id: "dbfox.data",
      listResources: async () => {
        throw new Error("boom");
      },
    });

    render(<ProjectOverview />);

    expect(await screen.findByText(/资源列表载入失败/)).toBeInTheDocument();
  });
});

let nextConnectorId = 0;

function registerTestConnector(overrides: {
  id: string;
  listResources?: (context: ConnectorContext) => Promise<ConnectorProjectResource[]>;
  removeResource?: (context: ConnectorContext, resource: ConnectorProjectResource) => Promise<void>;
}) {
  nextConnectorId += 1;
  useDlcStore.getState().setProjectionResult(`snap-inventory-${nextConnectorId}`, {}, {
    connectors: [
      {
        id: overrides.id,
        title: overrides.id === "dbfox.data" ? "数据" : "音乐",
        icon: null,
        render: () => null,
        addLabel: "配置",
        onAdd: vi.fn(),
        listResources: overrides.listResources,
        removeResource: overrides.removeResource,
      },
    ],
    dockViews: [],
    artifactViews: [],
  });
}
