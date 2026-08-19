import { describe, expect, it } from "vitest";
import {
  collectProductRequestedResources,
  dataRequestedResourceCollector,
  githubRequestedResourceCollector,
  workspaceRequestedResourceCollector,
} from "../requestedResourceComposition";

describe("Requested Resource Composition", () => {
  it("collects data resource ref when datasourceId is present", () => {
    const refs = dataRequestedResourceCollector({
      projectId: "proj-1",
      datasourceId: "ds-1",
    });
    expect(refs).toEqual([{ kind: "database", id: "ds-1" }]);
  });

  it("returns undefined for data collector when datasourceId is missing", () => {
    const refs = dataRequestedResourceCollector({
      projectId: "proj-1",
      datasourceId: null,
    });
    expect(refs).toBeUndefined();
  });

  it("collects workspace resource ref when workspaceRoot is present", () => {
    const refs = workspaceRequestedResourceCollector({
      projectId: "proj-1",
      workspaceRoot: "/path/to/project",
    });
    expect(refs).toEqual([{ kind: "workspace", id: "proj-1" }]);
  });

  it("returns undefined for workspace collector when workspaceRoot is missing", () => {
    const refs = workspaceRequestedResourceCollector({
      projectId: "proj-1",
      workspaceRoot: null,
    });
    expect(refs).toBeUndefined();
  });

  it("collects github resource ref when activeGithubBindingId is present", () => {
    const refs = githubRequestedResourceCollector({
      projectId: "proj-1",
      activeGithubBindingId: "gh-binding-1",
    });
    expect(refs).toEqual([{ kind: "github.repository", id: "gh-binding-1" }]);
  });

  it("returns undefined for github collector when bindingId is missing", () => {
    const refs = githubRequestedResourceCollector({
      projectId: "proj-1",
      activeGithubBindingId: null,
    });
    expect(refs).toBeUndefined();
  });

  it("combines all active resources and deduplicates refs", () => {
    const refs = collectProductRequestedResources({
      projectId: "proj-1",
      datasourceId: "ds-1",
      workspaceRoot: "/workspace",
      activeGithubBindingId: "gh-1",
    });
    expect(refs).toEqual([
      { kind: "database", id: "ds-1" },
      { kind: "workspace", id: "proj-1" },
      { kind: "github.repository", id: "gh-1" },
    ]);
  });

  it("returns undefined when no resources are active", () => {
    const refs = collectProductRequestedResources({
      projectId: "proj-1",
      datasourceId: null,
      workspaceRoot: null,
      activeGithubBindingId: null,
    });
    expect(refs).toBeUndefined();
  });
});
