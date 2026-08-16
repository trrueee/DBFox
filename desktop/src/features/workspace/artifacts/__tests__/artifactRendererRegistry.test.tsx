import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  ArtifactMetadataFallback,
  getArtifactRenderer,
  renderArtifact,
  type ArtifactEnvelope,
} from "../artifactRendererRegistry";

vi.mock("../TableArtifactView", () => ({
  TableArtifactView: () => <div data-testid="table-artifact-view" />,
}));
vi.mock("../ChartArtifactView", () => ({
  ChartArtifactView: () => <div data-testid="chart-artifact-view" />,
}));
vi.mock("../MarkdownArtifactView", () => ({
  MarkdownArtifactView: () => <div data-testid="markdown-artifact-view" />,
}));
vi.mock("../SqlArtifactView", () => ({
  SqlArtifactView: () => <div data-testid="sql-artifact-view" />,
}));
vi.mock("../WorkspaceFileSnapshotArtifactView", () => ({
  WorkspaceFileSnapshotArtifactView: () => <div data-testid="workspace-file-snapshot-view" />,
}));

describe("artifact renderer registry", () => {
  it("binds known renderers to (type, schemaVersion)", () => {
    expect(getArtifactRenderer("result_view", 1)).not.toBeNull();
    expect(getArtifactRenderer("chart", 1)).not.toBeNull();
    expect(getArtifactRenderer("markdown", 1)).not.toBeNull();
    expect(getArtifactRenderer("sql", 1)).not.toBeNull();
    expect(getArtifactRenderer("result_view", 2)).toBeNull();
    expect(getArtifactRenderer("dbfox.workspace.file_snapshot", 1)).not.toBeNull();
  });

  it("renders unknown artifacts through the metadata fallback", () => {
    const artifact: ArtifactEnvelope = {
      id: "artifact-unknown",
      type: "dbfox.workspace.future_object",
      schema_version: 1,
      title: "Unknown snapshot",
      summary: "historical envelope",
    };
    render(renderArtifact(artifact, { onToast: vi.fn() }));
    expect(screen.getByText("Unknown snapshot")).toBeTruthy();
    expect(screen.getByText(/保留 Artifact envelope/)).toBeTruthy();
    expect(screen.getByText(/dbfox.workspace.future_object v1/)).toBeTruthy();
  });

  it("renders workspace file snapshots through their own contribution", () => {
    const artifact: ArtifactEnvelope = {
      id: "artifact-file",
      type: "dbfox.workspace.file_snapshot",
      schema_version: 1,
      title: "src/main.py",
      payload: {
        relativePath: "src/main.py",
        sizeBytes: 32,
        sha256: "a".repeat(64),
        truncated: false,
      },
    };
    const { container } = render(renderArtifact(artifact, { onToast: vi.fn() }));
    expect(container.querySelector('[data-testid="workspace-file-snapshot-view"]')).toBeTruthy();
  });

  it("falls back when a known renderer payload cannot be parsed", () => {
    const artifact: ArtifactEnvelope = {
      id: "artifact-bad-result",
      type: "result_view",
      schema_version: 1,
      title: "Bad result",
      payload: { sourceSqlArtifactId: "" },
    };
    render(renderArtifact(artifact, { onToast: vi.fn() }));
    expect(screen.getByText("Bad result")).toBeTruthy();
    expect(screen.getByText(/payload 解析失败/)).toBeTruthy();
  });

  it("renders metadata fallback without a payload", () => {
    render(
      <ArtifactMetadataFallback
        artifact={{
          id: "artifact-empty",
          type: "sql",
          title: "SQL envelope",
          schema_version: 2,
        }}
      />,
    );
    expect(screen.getByText("SQL envelope")).toBeTruthy();
    expect(screen.getByText("sql v2")).toBeTruthy();
  });
});
