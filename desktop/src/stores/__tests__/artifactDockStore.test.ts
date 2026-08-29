import { beforeEach, describe, expect, it } from "vitest";

import { openArtifactDock, openArtifactsDock } from "../artifactDockStore";
import { selectActiveDockTabs, useWorkspaceStore } from "../workspaceStore";
import type { ConversationArtifact } from "../../types/conversation";

describe("artifact Dock commands", () => {
  beforeEach(() => {
    useWorkspaceStore.setState({
      activeProjectId: "",
      mainSurfaceByProject: {},
      workbenchByConversation: {},
      settingsOpen: false,
    });
  });

  it("deduplicates tabs by canonical target identity without caching Artifact data", () => {
    openArtifactsDock("conv-1");
    openArtifactsDock("conv-1");
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toHaveLength(1);

    const artifact: ConversationArtifact = {
      id: "artifact-1",
      session_id: "conv-1",
      run_id: "run-1",
      version: 1,
      type: "dbfox.data.result_view",
      schema_version: 2,
      title: "Result",
      status: "completed",
      visibility: "primary",
      payload: {},
      provenance: {},
      relations: [],
    };
    openArtifactDock(artifact);
    openArtifactDock(artifact);

    const tabs = selectActiveDockTabs(useWorkspaceStore.getState());
    expect(tabs).toHaveLength(2);
    expect(tabs[1]).toMatchObject({
      viewKey: "core.artifact:artifact-1",
      viewType: "core.artifact",
      target: { type: "artifact", id: "artifact-1" },
    });
    expect(tabs[1]).not.toHaveProperty("artifact");
  });
});
