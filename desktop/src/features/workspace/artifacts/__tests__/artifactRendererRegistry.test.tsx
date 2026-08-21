import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  createArtifactRendererRegistry,
  getArtifactRenderer,
  productArtifactRenderers,
  renderArtifact,
  type ArtifactEnvelope,
  type ArtifactRendererContribution,
} from "../artifactRendererRegistry";
import { coreArtifactRenderers } from "../coreArtifactRenderers";
import { dataArtifactRenderers } from "../dataArtifactRenderers";
import { workspaceArtifactRenderers } from "../workspaceArtifactRenderers";
import { useDlcStore } from "../../../dlc/extensionStore";

vi.mock("../TableArtifactView", () => ({
  TableArtifactView: () => <div data-testid="table-artifact-view" />,
}));
vi.mock("../DeferredChartArtifactView", () => ({
  DeferredChartArtifactView: () => <div data-testid="chart-artifact-view" />,
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
vi.mock("../WorkspaceCodePatchArtifactView", () => ({
  WorkspaceCodePatchArtifactView: () => <div data-testid="workspace-code-patch-view" />,
}));

describe("artifact renderer registry", () => {
  it("binds known renderers to (type, schemaVersion)", () => {
    expect(getArtifactRenderer("result_view", 1)).not.toBeNull();
    expect(getArtifactRenderer("chart", 1)).not.toBeNull();
    expect(getArtifactRenderer("markdown", 1)).not.toBeNull();
    expect(getArtifactRenderer("sql", 1)).not.toBeNull();
    expect(getArtifactRenderer("result_view", 2)).toBeNull();
    expect(getArtifactRenderer("dbfox.workspace.file_snapshot", 1)).not.toBeNull();
    expect(getArtifactRenderer("dbfox.workspace.code_patch", 1)).not.toBeNull();
    expect(getArtifactRenderer("dbfox.github.file_snapshot", 1)).toBeNull();
  });

  it("verifies clean modular ownership among core, data, and workspace", () => {
    const coreTypes = coreArtifactRenderers.map((r) => r.type);
    const dataTypes = dataArtifactRenderers.map((r) => r.type);
    const wsTypes = workspaceArtifactRenderers.map((r) => r.type);

    expect(coreTypes).toEqual(["markdown"]);
    expect(dataTypes).toEqual(["result_view", "chart", "sql"]);
    expect(wsTypes).toEqual([
      "dbfox.workspace.file_snapshot",
      "dbfox.workspace.code_patch",
    ]);
    const productRenderers = productArtifactRenderers();
    expect(productRenderers).toHaveLength(6);
  });

  it("rejects duplicate renderer type registration with fail-closed error", () => {
    const dup: ArtifactRendererContribution<unknown> = {
      type: "duplicate.type",
      supportedSchemaVersions: [1],
      parsePayload: (v) => v,
      render: () => <div />,
    };
    expect(() => createArtifactRendererRegistry([dup, dup])).toThrow(
      /Duplicate Artifact renderer contribution detected/,
    );
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

  it("renders workspace code patches through their own contribution", () => {
    const artifact: ArtifactEnvelope = {
      id: "artifact-code-patch",
      type: "dbfox.workspace.code_patch",
      schema_version: 1,
      title: "src/main.py",
      payload: {
        relativePath: "src/main.py",
        oldSha256: "a".repeat(64),
        newSha256: "b".repeat(64),
        sizeBytes: 42,
        created: false,
      },
    };
    const { container } = render(renderArtifact(artifact, { onToast: vi.fn() }));
    expect(container.querySelector('[data-testid="workspace-code-patch-view"]')).toBeTruthy();
  });

  it("renders newly created workspace code patches with oldSha256 = null", () => {
    const artifact: ArtifactEnvelope = {
      id: "artifact-code-patch-new",
      type: "dbfox.workspace.code_patch",
      schema_version: 1,
      title: "src/new_service.py",
      payload: {
        relativePath: "src/new_service.py",
        oldSha256: null,
        newSha256: "c".repeat(64),
        sizeBytes: 128,
        created: true,
      },
    };
    const { container } = render(renderArtifact(artifact, { onToast: vi.fn() }));
    expect(container.querySelector('[data-testid="workspace-code-patch-view"]')).toBeTruthy();
    expect(screen.queryByText(/payload 解析失败/)).toBeNull();
  });

  it("supports configuring data actions via productArtifactRenderers or createDataArtifactRenderers", () => {
    const onOpenResultTab = vi.fn();
    const onOpenSqlConsole = vi.fn();
    const customRenderers = productArtifactRenderers({
      dataActions: {
        onOpenResultTab,
        onOpenSqlConsole,
      },
    });
    const registry = createArtifactRendererRegistry(customRenderers);

    const sqlArtifact: ArtifactEnvelope = {
      id: "sql-1",
      type: "sql",
      schema_version: 1,
      title: "SELECT 1",
      payload: { sql: "SELECT 1" },
    };
    const { container } = render(
      renderArtifact(sqlArtifact, { onToast: vi.fn() }, registry),
    );
    expect(container.querySelector('[data-testid="sql-artifact-view"]')).toBeTruthy();
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

  it("supports custom registry injection for third-party artifact proof", () => {
    const customContribution: ArtifactRendererContribution<unknown> = {
      type: "test.custom.artifact",
      supportedSchemaVersions: [1],
      parsePayload: (v) => v,
      render: () => <div data-testid="custom-rendered-artifact">Custom Artifact Body</div>,
    };
    const customRegistry = createArtifactRendererRegistry([
      ...productArtifactRenderers(),
      customContribution,
    ]);

    const artifact: ArtifactEnvelope = {
      id: "custom-1",
      type: "test.custom.artifact",
      schema_version: 1,
      title: "Custom Title",
      payload: {},
    };

    const { container } = render(
      renderArtifact(artifact, { onToast: vi.fn() }, customRegistry),
    );
    expect(
      container.querySelector('[data-testid="custom-rendered-artifact"]'),
    ).toBeTruthy();
  });

  it("renders active DLC artifact renderers through the production render path", () => {
    useDlcStore.getState().setProjectionResult("snap-dlc", {}, {
      connectors: [],
      requestedResources: [],
      dockViews: [],
      artifactRenderers: [{
        type: "acme.runtime.artifact",
        supportedSchemaVersions: [1],
        parsePayload: (value) => value,
        render: () => <div data-testid="dlc-rendered-artifact">DLC Artifact</div>,
      }],
    });
    const artifact: ArtifactEnvelope = {
      id: "dlc-artifact-1",
      type: "acme.runtime.artifact",
      schema_version: 1,
      title: "DLC Artifact",
      payload: {},
    };

    const { container } = render(renderArtifact(artifact, { onToast: vi.fn() }));
    expect(container.querySelector('[data-testid="dlc-rendered-artifact"]')).toBeTruthy();
    useDlcStore.getState().reset();
  });
});
