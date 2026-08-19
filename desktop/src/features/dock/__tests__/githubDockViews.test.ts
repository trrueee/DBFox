import { beforeEach, describe, expect, it } from "vitest";
import { githubDockViews } from "../githubDockViews";
import { productDockViews, createDockViewRegistry } from "../dockViewComposition";
import { useGithubStore } from "../../github/githubStore";
import type { WorkspaceDockTab } from "../../../types/workspace";

describe("GitHub Dock Views", () => {
  beforeEach(() => {
    useGithubStore.setState({
      fileStateByKey: {},
    });
  });

  it("exports githubDockViews with viewType dbfox.github.file", () => {
    expect(githubDockViews).toHaveLength(1);
    expect(githubDockViews[0].viewType).toBe("dbfox.github.file");
  });

  it("is registered in productDockViews without collision", () => {
    const allViews = productDockViews();
    expect(allViews.some((v) => v.viewType === "dbfox.github.file")).toBe(true);

    const registry = createDockViewRegistry(allViews);
    const view = registry.get("dbfox.github.file");
    expect(view).not.toBeNull();
    expect(view?.viewType).toBe("dbfox.github.file");
  });

  it("resolves title from stored fileState if present", () => {
    const contribution = githubDockViews[0];
    const tab: WorkspaceDockTab = {
      viewKey: "dbfox.github.file:gh-1:rev1:src/main.rs",
      viewType: "dbfox.github.file",
      title: "Fallback Title",
      closeable: true,
      stateKey: "dbfox.github.file:gh-1:rev1:src/main.rs",
    };

    useGithubStore.setState({
      fileStateByKey: {
        "dbfox.github.file:gh-1:rev1:src/main.rs": {
          projectId: "proj-1",
          bindingId: "gh-1",
          revision: "rev1",
          filePath: "src/main.rs",
          fileName: "main.rs",
          owner: "astral-sh",
          repository: "uv",
        },
      },
    });

    expect(contribution.resolveTitle(tab)).toBe("main.rs");
  });

  it("filters visibility by activeProjectId", () => {
    const contribution = githubDockViews[0];
    const tab: WorkspaceDockTab = {
      viewKey: "dbfox.github.file:gh-1:rev1:src/main.rs",
      viewType: "dbfox.github.file",
      title: "main.rs",
      closeable: true,
      projectId: "proj-1",
    };

    const context = {
      activeProjectId: "proj-1",
      activeDatasourceId: "ds-1",
      activeConversationId: null,
    };

    expect(contribution.isVisible(tab, context)).toBe(true);
    expect(contribution.isVisible(tab, { ...context, activeProjectId: "proj-2" })).toBe(false);
  });
});
