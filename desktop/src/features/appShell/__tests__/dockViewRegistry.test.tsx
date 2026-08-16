import { describe, expect, it } from "vitest";
import type { WorkspaceDockTab } from "../../../types/workspace";
import { dockViewTitle, getDockView } from "../dockViewRegistry";

function tab(overrides: Partial<WorkspaceDockTab> = {}): WorkspaceDockTab {
  return {
    id: "tab-1",
    kind: "table",
    title: "orders",
    closeable: true,
    datasourceId: "ds-1",
    ...overrides,
  };
}

describe("dock view registry", () => {
  it("maps current dock kinds to stable view types", () => {
    expect(getDockView("console")?.viewType).toBe("core.sql-console");
    expect(getDockView("table")?.viewType).toBe("dbfox.data.table");
    expect(getDockView("artifacts")?.viewType).toBe("core.artifacts");
    expect(getDockView("artifact")?.viewType).toBe("core.artifact");
    expect(getDockView("multi-table")?.viewType).toBe("dbfox.data.multi-table");
    expect(getDockView("file")?.viewType).toBe("dbfox.workspace.file");
    expect(getDockView("future-webview")).toBeNull();
  });

  it("keeps datasource views scoped to the active datasource", () => {
    const table = getDockView("table");
    const console = getDockView("console");
    expect(
      table?.isVisible(tab({ datasourceId: "ds-2" }), {
        activeProjectId: "project-1",
        activeDatasourceId: "ds-1",
        activeConversationId: null,
      }),
    ).toBe(false);
    expect(
      console?.isVisible(tab({ kind: "console", datasourceId: "ds-1" }), {
        activeProjectId: "project-1",
        activeDatasourceId: "ds-1",
        activeConversationId: null,
      }),
    ).toBe(true);
  });

  it("keeps artifact views scoped to the active conversation", () => {
    const artifacts = getDockView("artifacts");
    expect(
      artifacts?.isVisible(
        tab({ kind: "artifacts", conversationId: "conv-2" }),
        {
          activeProjectId: "project-1",
          activeDatasourceId: "ds-1",
          activeConversationId: "conv-1",
        },
      ),
    ).toBe(false);
    expect(
      artifacts?.isVisible(
        tab({ kind: "artifacts", conversationId: "conv-1" }),
        {
          activeProjectId: "project-1",
          activeDatasourceId: "ds-1",
          activeConversationId: "conv-1",
        },
      ),
    ).toBe(true);
  });

  it("keeps file views scoped to their source project", () => {
    const file = getDockView("file");
    expect(
      file?.isVisible(
        tab({ kind: "file", filePath: "C:/demo/README.md", fileName: "README.md", projectId: "project-2" }),
        { activeProjectId: "project-1", activeDatasourceId: "ds-1", activeConversationId: null },
      ),
    ).toBe(false);
    expect(
      file?.isVisible(
        tab({ kind: "file", filePath: "C:/demo/README.md", fileName: "README.md", projectId: "project-1" }),
        { activeProjectId: "project-1", activeDatasourceId: "ds-1", activeConversationId: null },
      ),
    ).toBe(true);
  });

  it("resolves titles through the contribution instead of a central switch", () => {
    expect(dockViewTitle(tab({ kind: "console", title: "ignored" }))).toBe("SQL 控制台");
    expect(dockViewTitle(tab())).toBe("orders");
  });
});
