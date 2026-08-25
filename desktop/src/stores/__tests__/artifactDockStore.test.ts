import { beforeEach, describe, expect, it } from "vitest";

import { useArtifactDockStore } from "../artifactDockStore";
import { selectActiveDockTabs, useWorkspaceStore } from "../workspaceStore";

describe("artifactDockStore", () => {
  beforeEach(() => {
    useWorkspaceStore.setState({
      activeProjectId: "",
      projectShell: {},
      mainSurfaceByProject: {},
      workbenchByConversation: {},
      settingsOpen: false,
    });
    useArtifactDockStore.setState({ artifactById: {}, conversationIdByArtifactId: {} });
  });

  it("deduplicates Core artifact views by canonical identity", () => {
    useArtifactDockStore.getState().openArtifacts("conv-1");
    useArtifactDockStore.getState().openArtifacts("conv-1");
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toHaveLength(1);

    const artifact = {
      id: "artifact-1",
      type: "result_view" as const,
      title: "Result",
      sourceSqlArtifactId: "sql-1",
      columns: [],
      queryFingerprint: "fp",
    };
    useArtifactDockStore.getState().openArtifact(artifact, "conv-1");
    useArtifactDockStore.getState().openArtifact(artifact, "conv-1");
    expect(selectActiveDockTabs(useWorkspaceStore.getState())).toHaveLength(2);
    expect(useArtifactDockStore.getState().artifactById["artifact-1"]).toBe(artifact);
  });
});
