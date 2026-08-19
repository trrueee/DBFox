import { describe, expect, it } from "vitest";
import type { WorkspaceDockTab } from "../../../types/workspace";
import { dockViewTitle, getDockView } from "../dockViewRegistry";
import { useWorkspaceFileStore } from "../../../stores/workspaceFileStore";

function tab(overrides: Partial<WorkspaceDockTab> = {}): WorkspaceDockTab {
  return {
    viewKey: "dbfox.data.table:ds-1:orders",
    viewType: "dbfox.data.table",
    title: "orders",
    closeable: true,
    target: { type: "resource", kind: "database", id: "ds-1" },
    ...overrides,
  };
}

describe("dock view registry", () => {
  it("maps view types to registered contributions", () => {
    expect(getDockView("dbfox.data.sql-console")?.viewType).toBe("dbfox.data.sql-console");
    expect(getDockView("dbfox.data.table")?.viewType).toBe("dbfox.data.table");
    expect(getDockView("core.artifacts")?.viewType).toBe("core.artifacts");
    expect(getDockView("core.artifact")?.viewType).toBe("core.artifact");
    expect(getDockView("dbfox.data.multi-table")?.viewType).toBe("dbfox.data.multi-table");
    expect(getDockView("dbfox.workspace.file")?.viewType).toBe("dbfox.workspace.file");
    expect(getDockView("future-webview")).toBeNull();
  });

  it("keeps datasource views scoped to the active datasource", () => {
    const table = getDockView("dbfox.data.table");
    const console = getDockView("dbfox.data.sql-console");
    expect(
      table?.isVisible(
        tab({ target: { type: "resource", kind: "database", id: "ds-2" } }),
        {
          activeProjectId: "project-1",
          activeDatasourceId: "ds-1",
          activeConversationId: null,
        },
      ),
    ).toBe(false);
    expect(
      console?.isVisible(
        tab({
          viewType: "dbfox.data.sql-console",
          target: { type: "resource", kind: "database", id: "ds-1" },
        }),
        {
          activeProjectId: "project-1",
          activeDatasourceId: "ds-1",
          activeConversationId: null,
        },
      ),
    ).toBe(true);
  });

  it("keeps artifact views scoped to the active conversation", () => {
    const artifacts = getDockView("core.artifacts");
    expect(
      artifacts?.isVisible(
        tab({
          viewType: "core.artifacts",
          target: { type: "conversation", id: "conv-2" },
        }),
        {
          activeProjectId: "project-1",
          activeDatasourceId: "ds-1",
          activeConversationId: "conv-1",
        },
      ),
    ).toBe(false);
    expect(
      artifacts?.isVisible(
        tab({
          viewType: "core.artifacts",
          target: { type: "conversation", id: "conv-1" },
        }),
        {
          activeProjectId: "project-1",
          activeDatasourceId: "ds-1",
          activeConversationId: "conv-1",
        },
      ),
    ).toBe(true);
  });

  it("keeps file views scoped to their source project", () => {
    const file = getDockView("dbfox.workspace.file");
    useWorkspaceFileStore.setState({
      fileStateByKey: {
        "file-key-1": {
          projectId: "project-2",
          filePath: "C:/demo/README.md",
          fileName: "README.md",
        },
        "file-key-2": {
          projectId: "project-1",
          filePath: "C:/demo/README.md",
          fileName: "README.md",
        },
      },
    });

    expect(
      file?.isVisible(
        tab({
          viewKey: "file-key-1",
          viewType: "dbfox.workspace.file",
          stateKey: "file-key-1",
          projectId: "project-2",
        }),
        { activeProjectId: "project-1", activeDatasourceId: "ds-1", activeConversationId: null },
      ),
    ).toBe(false);
    expect(
      file?.isVisible(
        tab({
          viewKey: "file-key-2",
          viewType: "dbfox.workspace.file",
          stateKey: "file-key-2",
          projectId: "project-1",
        }),
        { activeProjectId: "project-1", activeDatasourceId: "ds-1", activeConversationId: null },
      ),
    ).toBe(true);
  });

  it("resolves titles through the contribution instead of a central switch", () => {
    expect(
      dockViewTitle(
        tab({
          viewType: "dbfox.data.sql-console",
          title: "ignored",
        }),
      ),
    ).toBe("SQL 控制台");
    expect(dockViewTitle(tab())).toBe("orders");
  });

  it("fails soft for an unknown view contribution", () => {
    const unknown = tab({
      viewKey: "future:1",
      viewType: "future-webview",
      title: "Future view",
    });

    expect(getDockView(unknown.viewType)).toBeNull();
    expect(dockViewTitle(unknown)).toBe("Future view");
  });
});
