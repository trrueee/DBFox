import { beforeEach, describe, expect, it } from "vitest";
import {
  collectProductRequestedResources,
  dataRequestedResourceContributor,
  workspaceRequestedResourceContributor,
} from "../requestedResourceComposition";
import { queryClient } from "../../../lib/queryClient";
import { projectQueryKeys } from "../../projects/useProjectState";

describe("Requested Resource Composition Contributors", () => {
  beforeEach(() => {
    queryClient.clear();
  });

  it("data contributor returns database ref when datasourceId is present", () => {
    const result = dataRequestedResourceContributor({
      projectId: "proj-1",
      conversationId: "conv-1",
      datasourceId: "ds-1",
    });
    expect(result.complete).toBe(true);
    expect(result.refs).toEqual([{ kind: "database", id: "ds-1" }]);
  });

  it("data contributor returns empty refs when datasourceId is null", () => {
    const result = dataRequestedResourceContributor({
      projectId: "proj-1",
      conversationId: "conv-1",
      datasourceId: null,
    });
    expect(result.complete).toBe(true);
    expect(result.refs).toEqual([]);
  });

  it("workspace contributor returns complete=false when project catalog is not cached", () => {
    const result = workspaceRequestedResourceContributor({
      projectId: "proj-1",
      conversationId: "conv-1",
    });
    expect(result.complete).toBe(false);
  });

  it("workspace contributor returns workspace ref when project has workspace_root", () => {
    queryClient.setQueryData(projectQueryKeys.all, [
      { id: "proj-1", name: "Project 1", workspace_root: "/path/to/work" },
    ]);
    const result = workspaceRequestedResourceContributor({
      projectId: "proj-1",
      conversationId: "conv-1",
    });
    expect(result.complete).toBe(true);
    expect(result.refs).toEqual([{ kind: "workspace", id: "proj-1" }]);
  });

  it("workspace contributor returns empty refs when project explicitly has no workspace_root", () => {
    queryClient.setQueryData(projectQueryKeys.all, [
      { id: "proj-1", name: "Project 1", workspace_root: null },
    ]);
    const result = workspaceRequestedResourceContributor({
      projectId: "proj-1",
      conversationId: "conv-1",
    });
    expect(result.complete).toBe(true);
    expect(result.refs).toEqual([]);
  });

  it("collectProductRequestedResources returns complete snapshot when all contributors are proven", () => {
    queryClient.setQueryData(projectQueryKeys.all, [
      { id: "proj-1", name: "Project 1", workspace_root: "/path/to/work" },
    ]);
    const snapshot = collectProductRequestedResources({
      projectId: "proj-1",
      conversationId: "conv-1",
      datasourceId: "ds-1",
    });

    expect(snapshot.complete).toBe(true);
    expect(snapshot.refs).toEqual([
      { kind: "database", id: "ds-1" },
      { kind: "workspace", id: "proj-1" },
    ]);
  });

  it("collectProductRequestedResources returns complete=false when workspace catalog is unproven", () => {
    const snapshot = collectProductRequestedResources({
      projectId: "proj-1",
      conversationId: "conv-1",
      datasourceId: "ds-1",
    });
    expect(snapshot.complete).toBe(false);
    expect(snapshot.refs).toEqual([]);
  });
});
