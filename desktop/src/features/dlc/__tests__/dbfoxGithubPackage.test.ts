import { beforeEach, describe, expect, it, vi } from "vitest";

import { createStagedExtensionHost, initExtensionHostGlobalSdk } from "../extensionHost";
import { register } from "../../../../../dlcs/dbfox.github/frontend/index.js";

describe("dbfox.github packaged frontend", () => {
  beforeEach(() => {
    document.head
      .querySelectorAll('link[data-dbfox-dlc="dbfox.github"]')
      .forEach((node) => node.remove());
  });

  it("registers the complete frontend contribution set through the bounded host", () => {
    initExtensionHostGlobalSdk();
    const invokeOperation = vi.fn();
    const openDockTab = vi.fn();
    const staged = createStagedExtensionHost("dbfox.github", {
      invokeOperation,
      openDockTab,
    });

    register(staged.host);
    const contributions = staged.getContributions();

    expect(contributions.connectors.map((item) => item.id)).toEqual(["dbfox.github"]);
    expect(contributions.dockViews.map((item) => item.viewType)).toEqual([
      "dbfox.github.file",
    ]);
    expect(contributions.artifactRenderers.map((item) => item.type)).toEqual([
      "dbfox.github.file_snapshot",
    ]);
    expect(invokeOperation).not.toHaveBeenCalled();
    expect(openDockTab).not.toHaveBeenCalled();
    expect(
      document.head.querySelector('link[data-dbfox-dlc="dbfox.github"]'),
    ).not.toBeNull();
  });
});
