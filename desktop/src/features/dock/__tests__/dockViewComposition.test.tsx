import { describe, expect, it } from "vitest";
import type { WorkspaceDockTab } from "../../../types/workspace";
import { dockViewTitle, getDockView } from "../dockViewComposition";
import { useConversationStore } from "../../../stores/conversationStore";

function tab(overrides: Partial<WorkspaceDockTab> = {}): WorkspaceDockTab {
  return {
    viewKey: "dbfox.data.table:ds-1:orders",
    viewType: "dbfox.data.table",
    title: "orders",
    closeable: true,
    target: { type: "object", object: { kind: "dbfox.data.database", id: "ds-1" } },
    ...overrides,
  };
}

describe("dock view registry", () => {
  it("maps view types to registered contributions", () => {
    expect(getDockView("core.artifacts")?.viewType).toBe("core.artifacts");
    expect(getDockView("core.artifact")?.viewType).toBe("core.artifact");
    expect(getDockView("dbfox.data.sql-console")).toBeNull();
    expect(getDockView("dbfox.workspace.file")).toBeNull();
    expect(getDockView("future-webview")).toBeNull();
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
          activeConversationId: "conv-1",
        },
      ),
    ).toBe(true);
  });

  it("resolves titles through the contribution instead of a central switch", () => {
    expect(dockViewTitle(tab({ viewType: "core.artifacts", title: "ignored" }))).toBe("✦ 工件");
    expect(dockViewTitle(tab())).toBe("orders");
  });

  it("uses explicit navigation project metadata without relaxing ordinary artifact session visibility", () => {
    const view = getDockView("core.artifact")!;
    const artifactTab = tab({ viewType: "core.artifact", target: { type: "artifact", id: "action-result" } });
    const context = { activeProjectId: "project-1", activeConversationId: null };
    const previous = useConversationStore.getState().artifactsById;
    useConversationStore.setState({ artifactsById: { "action-result": {
      id: "action-result", session_id: "action-session", run_id: "run-1", title: "Result",
      type: "example.result", payload: {}, version: 1, status: "completed",
      visibility: "primary", provenance: {}, relations: [],
    } } });
    try {
      expect(view.isVisible(artifactTab, context)).toBe(false);
      expect(view.isVisible(artifactTab, { ...context, activeConversationId: "chat-session" })).toBe(false);
      expect(view.isVisible(artifactTab, { ...context, activeConversationId: "action-session" })).toBe(true);
      expect(view.isVisible({ ...artifactTab, projectId: "project-1" }, context)).toBe(true);
      expect(view.isVisible({ ...artifactTab, projectId: "project-2" }, context)).toBe(false);
      expect(view.isVisible({ ...artifactTab, projectId: " " }, context)).toBe(false);
      expect(view.isVisible({ ...artifactTab, projectId: "project-1", target: { type: "conversation", id: "action-session" } }, context)).toBe(false);
    } finally { useConversationStore.setState({ artifactsById: previous }); }
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

