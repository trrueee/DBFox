import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import { createStagedExtensionHost, initExtensionHostGlobalSdk } from "../extensionHost";
import type { DlcModule } from "../types";

const fixturePath = resolve(
  process.cwd(),
  "../dlcs/dbfox.visualization/frontend/index.js",
);

function moduleUrl(source: string): string {
  return `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
}

afterEach(() => { vi.unstubAllGlobals(); });

describe("dbfox.visualization System DLC frontend fixture", () => {
  it("owns its inline/workspace Visualization Artifact View", async () => {
    initExtensionHostGlobalSdk();
    vi.stubGlobal("document", undefined);
    const source = await readFile(fixturePath, "utf8");
    expect(source).not.toMatch(/\bstyle\s*:\s*\{/);
    expect(source).not.toContain(".style.");
    expect(source).not.toContain("innerHTML");
    expect(source).not.toContain("Fira Sans");
    expect(source).toContain("view.tooltip(");
    const module = await import(/* @vite-ignore */ moduleUrl(source)) as DlcModule;
    const staged = createStagedExtensionHost("dbfox.visualization", {
      invokeOperation: vi.fn(),
      openDockTab: vi.fn(),
      pickFolder: vi.fn(),
      pickFile: vi.fn(),
      readPickedFile: vi.fn(),
    });

    await module.register?.(staged.host);
    const contributions = staged.getContributions();
    expect(contributions.artifactViews.map((item) => item.id)).toEqual([
      "dbfox.visualization.document",
      "dbfox.visualization.authored-dataset",
      "dbfox.visualization.legacy-data-chart",
    ]);
    const view = contributions.artifactViews[0];
    expect(view.id).toBe("dbfox.visualization.document");
    expect(view.surfaces).toEqual(["inline", "workspace"]);
    expect(view.artifactTypes).toEqual([
      { type: "dbfox.visualization.document", schemaVersions: [1, 2] },
    ]);
    expect(view.parsePayload({
      specVersion: "1.0",
      title: "Revenue trend",
      insight: "Revenue increased.",
      source: {
        kind: "inline",
        provenance: "model_knowledge",
        records: [{ month: "Jan", revenue: 10 }],
      },
      layout: { columns: 1, density: "comfortable" },
      blocks: [{
        id: "trend",
        kind: "chart",
        span: 1,
        grammar: "vega-lite",
        minHeight: 240,
        spec: {
          data: { name: "dbfox_source" },
          mark: "line",
          encoding: {},
        },
      }],
    })).toMatchObject({ title: "Revenue trend" });
    expect(view.parsePayload({
      specVersion: "1.0",
      title: "Revenue summary",
      insight: "Revenue increased.",
      source: {
        kind: "inline",
        provenance: "model_knowledge",
        records: [{ revenue: 10 }],
      },
      layout: { columns: 1, density: "comfortable" },
      blocks: [{
        id: "revenue",
        kind: "metric",
        span: 1,
        label: "Revenue",
        field: "revenue",
        aggregation: "sum",
        format: "number",
        emphasis: "positive",
      }],
    })).toMatchObject({ title: "Revenue summary" });
    const authoredDatasetView = contributions.artifactViews[1];
    expect(authoredDatasetView.artifactTypes).toEqual([
      { type: "dbfox.visualization.authored_dataset", schemaVersions: [1] },
    ]);
    expect(authoredDatasetView.parsePayload({
      provenance: "user_provided",
      records: [{ category: "A", value: 2 }],
    })).toMatchObject({ provenance: "user_provided" });

    vi.unstubAllGlobals();
    const emptyPayload = view.parsePayload({
      specVersion: "1.0",
      title: "Empty result",
      insight: "No current rows.",
      source: {
        kind: "artifact",
        artifactId: "result-empty",
        representationType: "dbfox.dataframe.v1",
        pageSize: 100,
      },
      layout: { columns: 1, density: "comfortable" },
      blocks: [{
        id: "trend",
        kind: "chart",
        span: 1,
        grammar: "vega-lite",
        minHeight: 240,
        spec: {
          data: { name: "dbfox_source" },
          mark: "line",
          encoding: {},
        },
      }],
    });
    render(view.render(
      {
        id: "visualization-empty",
        type: "dbfox.visualization.document",
        schema_version: 2,
        title: "Empty result",
        version: 1,
      },
      emptyPayload,
      {
        surface: "inline",
        onToast: vi.fn(),
        representations: {
          available: [],
          list: vi.fn().mockResolvedValue([]),
          read: vi.fn().mockResolvedValue({
            representation_type: "dbfox.dataframe.v1",
            representation_version: 1,
            operation: "page",
            payload: { fields: [], has_next_page: false },
            consistency: "live_reexecution",
            read_at: "2026-08-28T00:00:00Z",
            read_id: "read-empty",
            source_version: "1",
            source_fingerprint: "empty",
          }),
          stream: vi.fn(),
        },
      },
    ));
    await waitFor(() => expect(screen.getByText("来源暂时没有数据行")).toBeTruthy());
    expect(screen.getByText("实时重查")).toBeTruthy();
    expect(screen.queryByText("正在绘制图形…")).toBeNull();
  });
});
