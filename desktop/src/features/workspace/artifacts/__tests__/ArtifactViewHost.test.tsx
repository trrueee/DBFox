import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { agentApi } from "../../../../lib/api/agent";
import { DATAFRAME_REPRESENTATION_TYPE } from "../../../../lib/api/representation";
import { useDlcStore } from "../../../dlc/extensionStore";
import { ArtifactViewHost } from "../ArtifactViewHost";
import type { ArtifactEnvelope, ArtifactViewContribution } from "../types";

vi.mock("../../../../lib/api/agent", () => ({
  agentApi: {
    listArtifactRepresentations: vi.fn(),
    readArtifactRepresentation: vi.fn(),
    streamArtifactRepresentation: vi.fn(),
  },
}));

const result: ArtifactEnvelope = {
  id: "result-1",
  type: "dbfox.data.result_view",
  schema_version: 2,
  version: 3,
  status: "completed",
  title: "Orders",
  payload: { sourceSqlArtifactId: "sql-1" },
};

const sql: ArtifactEnvelope = {
  id: "sql-1",
  type: "dbfox.data.sql",
  schema_version: 1,
  status: "completed",
  title: "Orders SQL",
  payload: { sql: "SELECT id, amount FROM orders", dialect: "sqlite" },
};

const sourceSqlView: ArtifactViewContribution<unknown> = {
  id: "dbfox.data.source-sql",
  title: "来源 SQL",
  priority: 50,
  surfaces: ["workspace"],
  artifactTypes: [{ type: "dbfox.data.result_view", schemaVersions: [2] }],
  parsePayload: (value) => value,
  render: (_artifact, _payload, context) => {
    const source = context.resolveArtifact?.("sql-1");
    const payload = source?.payload as { sql?: string } | undefined;
    return <pre aria-label={`${source?.title} SQL`}>{payload?.sql}</pre>;
  },
};

describe("ArtifactViewHost", () => {
  beforeEach(() => {
    cleanup();
    useDlcStore.getState().setProjectionResult("snapshot-test", {}, {
      connectors: [],
      dockViews: [],
      artifactViews: [sourceSqlView],
    });
    vi.mocked(agentApi.listArtifactRepresentations).mockResolvedValue([{
      representation_type: DATAFRAME_REPRESENTATION_TYPE,
      version: 1,
      operations: [
        { name: "page", result_kind: "json" },
        { name: "export.csv", result_kind: "stream", media_type: "text/csv" },
      ],
    }]);
    vi.mocked(agentApi.readArtifactRepresentation).mockResolvedValue({
      representation_type: DATAFRAME_REPRESENTATION_TYPE,
      representation_version: 1,
      operation: "page",
      payload: {
        fields: [
          { key: "id", name: "id", type: "integer", nullable: false, values: [1] },
          { key: "amount", name: "amount", type: "decimal", nullable: false, values: [20] },
        ],
        page: 1,
        page_size: 50,
        row_count: 1,
        has_next_page: false,
        latency_ms: 2,
        source_truncated: false,
      },
      consistency: "live_reexecution",
      original_observed_at: "2026-08-28T00:00:00Z",
      read_at: "2026-08-28T00:00:01Z",
      read_id: "read-1",
      source_version: "3",
      source_fingerprint: "fp-1",
      warnings: [],
      notices: [],
    });
  });

  it("discovers multiple Views while keeping one Artifact identity", async () => {
    const onSelectedViewChange = vi.fn();
    render(
      <ArtifactViewHost
        artifact={result}
        surface="workspace"
        onToast={vi.fn()}
        onSelectedViewChange={onSelectedViewChange}
        resolveArtifact={(id) => id === sql.id ? sql : null}
      />,
    );

    expect(await screen.findByRole("tab", { name: "表格" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "来源 SQL" })).toBeTruthy();
    await waitFor(() => expect(onSelectedViewChange).toHaveBeenCalledWith("core.dataframe.table"));
    expect(await screen.findByText("20")).toBeTruthy();

    fireEvent.mouseDown(screen.getByRole("tab", { name: "来源 SQL" }), {
      button: 0,
      ctrlKey: false,
    });
    expect(await screen.findByLabelText("Orders SQL SQL")).toBeTruthy();
    expect(document.body.textContent).toContain("orders");
  });

  it("honors the Tab-selected View without copying Artifact content", async () => {
    render(
      <ArtifactViewHost
        artifact={result}
        surface="workspace"
        selectedViewId="dbfox.data.source-sql"
        onToast={vi.fn()}
        resolveArtifact={(id) => id === sql.id ? sql : null}
      />,
    );

    expect((await screen.findByRole("tab", { name: "来源 SQL" })).getAttribute("aria-selected"))
      .toBe("true");
    expect(screen.getByLabelText("Orders SQL SQL")).toBeTruthy();
  });

  it("opens the same inline Artifact identity in the workspace", async () => {
    const openArtifact = vi.fn();
    render(
      <ArtifactViewHost
        artifact={result}
        surface="inline"
        onToast={vi.fn()}
        openArtifact={openArtifact}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: "在工作区查看" }));
    expect(openArtifact).toHaveBeenCalledWith(result);
  });
});
