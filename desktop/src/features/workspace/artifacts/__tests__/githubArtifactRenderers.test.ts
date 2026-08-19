import { describe, expect, it } from "vitest";
import { githubArtifactRenderers } from "../githubArtifactRenderers";
import {
  productArtifactRenderers,
  createArtifactRendererRegistry,
} from "../artifactRendererRegistry";

describe("GitHub Artifact Renderers", () => {
  it("exports githubArtifactRenderers for dbfox.github.file_snapshot v1", () => {
    expect(githubArtifactRenderers).toHaveLength(1);
    expect(githubArtifactRenderers[0].type).toBe("dbfox.github.file_snapshot");
    expect(githubArtifactRenderers[0].supportedSchemaVersions).toEqual([1]);
  });

  it("is registered in productArtifactRenderers without duplicate errors", () => {
    const all = productArtifactRenderers();
    expect(all.some((r) => r.type === "dbfox.github.file_snapshot")).toBe(true);

    const registry = createArtifactRendererRegistry(all);
    const renderer = registry.get("dbfox.github.file_snapshot", 1);
    expect(renderer).not.toBeNull();
    expect(renderer?.type).toBe("dbfox.github.file_snapshot");
  });

  it("parses valid file snapshot payload", () => {
    const renderer = githubArtifactRenderers[0];
    const raw = {
      repositoryBindingId: "gh-1",
      relativePath: "src/lib.rs",
      revision: "1234567890abcdef1234567890abcdef12345678",
      blobSha: "abcdef1234567890abcdef1234567890abcdef12",
      sizeBytes: 1024,
      truncated: false,
    };

    const parsed = renderer.parsePayload(raw);
    expect(parsed).toEqual({
      id: "",
      type: "dbfox.github.file_snapshot",
      schemaVersion: 1,
      title: "",
      repositoryBindingId: "gh-1",
      relativePath: "src/lib.rs",
      revision: "1234567890abcdef1234567890abcdef12345678",
      blobSha: "abcdef1234567890abcdef1234567890abcdef12",
      sizeBytes: 1024,
      truncated: false,
    });
  });

  it("throws error on missing required fields in payload", () => {
    const renderer = githubArtifactRenderers[0];
    const invalid = {
      repositoryBindingId: "gh-1",
      // missing relativePath
      revision: "1234567890abcdef1234567890abcdef12345678",
    };

    expect(() => renderer.parsePayload(invalid)).toThrow();
  });
});
