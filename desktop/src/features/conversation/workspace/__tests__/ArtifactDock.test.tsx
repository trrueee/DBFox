import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ConversationArtifact } from "../../../../types/conversation";
import { agentApi } from "../../../../lib/api/agent";
import {
  DATAFRAME_REPRESENTATION_TYPE,
} from "../../../../lib/api/representation";
import { ArtifactDock } from "../ArtifactDock";

vi.mock("../../../../lib/api/agent", () => ({
  agentApi: {
    listArtifactRepresentations: vi.fn(),
    readArtifactRepresentation: vi.fn(),
    streamArtifactRepresentation: vi.fn(),
  },
}));

function trustedQueryArtifacts(): ConversationArtifact[] {
  return [
    {
      id: "artifact-sql",
      semantic_key: "sql_candidate",
      session_id: "conv",
      run_id: "run",
      version: 1,
      type: "dbfox.data.sql",
      schema_version: 1,
      visibility: "supporting",
      title: "SQL",
      status: "completed",
      payload: {
        sql: "SELECT id, amount FROM orders",
        safeSql: "SELECT id, amount FROM orders",
        dialect: "sqlite",
        queryFingerprint: "sql-orders",
      },
      provenance: {},
      relations: [],
    },
    {
      id: "artifact-safety",
      semantic_key: "safety_report",
      session_id: "conv",
      run_id: "run",
      version: 1,
      type: "dbfox.data.safety",
      schema_version: 1,
      visibility: "internal",
      title: "Safety",
      status: "completed",
      payload: {
        passed: true,
        canExecute: true,
        requiresApproval: false,
        guardrailResult: "passed",
        schemaWarningsCount: 0,
        safeSql: "SELECT id, amount FROM orders WHERE amount > 10",
      },
      provenance: {},
      relations: [{ relation: "validated_by", artifact_id: "artifact-sql" }],
    },
    {
      id: "artifact-result",
      semantic_key: "result_view_1",
      session_id: "conv",
      run_id: "run",
      version: 1,
      type: "dbfox.data.result_view",
      schema_version: 2,
      visibility: "primary",
      title: "Order result",
      status: "completed",
      payload: {
        sourceSqlArtifactId: "artifact-sql",
        queryFingerprint: "query-1",
        columns: ["id", "amount"],
        rowCount: 1,
      },
      provenance: {},
      relations: [{ relation: "executed_as", artifact_id: "artifact-sql" }],
    },
  ];
}

describe("ArtifactDock", () => {
  beforeEach(() => {
    cleanup();
    vi.mocked(agentApi.listArtifactRepresentations).mockReset();
    vi.mocked(agentApi.listArtifactRepresentations).mockImplementation(async (artifactId) => (
      artifactId.includes("result")
        ? [{
            representation_type: DATAFRAME_REPRESENTATION_TYPE,
            version: 1,
            operations: [{ name: "page", result_kind: "json" }],
          }]
        : []
    ));
    vi.mocked(agentApi.readArtifactRepresentation).mockReset();
    vi.mocked(agentApi.readArtifactRepresentation).mockImplementation(async () => ({
            representation_type: DATAFRAME_REPRESENTATION_TYPE,
            representation_version: 1,
            operation: "page",
            payload: {
              fields: [
                { key: "field_0", name: "id", type: "integer", nullable: false, values: [1] },
                { key: "field_1", name: "amount", type: "integer", nullable: false, values: [20] },
              ],
              page: 1, page_size: 10, row_count: 1, has_next_page: false,
              latency_ms: 1, source_truncated: false,
            },
            consistency: "durable_snapshot",
            original_observed_at: "2026-07-20T00:00:00Z",
            read_at: "2026-07-20T00:00:01Z",
            read_id: "view-dock",
            source_version: "1",
            source_fingerprint: "query-dock",
            warnings: [], notices: [],
          }));
  });

  it("renders only core user-facing artifacts and keeps audit artifacts hidden", async () => {
    const onSelectArtifact = vi.fn();
    render(
      <ArtifactDock
        artifacts={trustedQueryArtifacts()}
        selectedArtifactId="artifact-result"
        onOpenArtifact={vi.fn()}
        onSelectArtifact={onSelectArtifact}
      />,
    );

    expect(screen.getByRole("complementary", { name: "Artifact dock" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "SQL sql" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Safety safety" })).toBeNull();
    expect(screen.getByRole("button", { name: "Order result result view" }).getAttribute("aria-pressed")).toBe("true");
    expect(await screen.findByText("本页 1 / 共 1 行")).toBeTruthy();
    expect(onSelectArtifact).not.toHaveBeenCalled();
  });

  it("keeps workspace-only source SQL out of the inline Artifact preview", async () => {
    const artifacts = trustedQueryArtifacts();
    artifacts.push({
      ...artifacts[0],
      id: "artifact-sql-unrelated",
      semantic_key: "sql_candidate_unrelated",
      payload: {
        sql: "SELECT secret FROM unrelated",
        safeSql: "SELECT secret FROM unrelated",
        dialect: "sqlite",
        queryFingerprint: "sql-unrelated",
      },
    });
    render(
      <ArtifactDock
        artifacts={artifacts}
        selectedArtifactId="artifact-result"
        onOpenArtifact={vi.fn()}
      />,
    );

    await screen.findByText("本页 1 / 共 1 行");
    expect(screen.queryByRole("tab", { name: "来源 SQL" })).toBeNull();
    expect(document.body.textContent).not.toContain("unrelated");
  });

  it("falls back to the latest primary artifact when selection points to supporting material", async () => {
    const artifacts = trustedQueryArtifacts();
    const latestSql: ConversationArtifact = {
      ...artifacts[0],
      id: "artifact-sql-latest",
      semantic_key: "sql_candidate_latest",
      run_id: "run-latest",
      title: "Latest SQL",
      version: 2,
      payload: {
        sql: "SELECT COUNT(*) AS count FROM orders",
        safeSql: "SELECT COUNT(*) AS count FROM orders",
        dialect: "sqlite",
        queryFingerprint: "sql-orders-count",
      },
    };
    const latestResult: ConversationArtifact = {
      ...artifacts[2],
      id: "artifact-result-latest",
      semantic_key: "result_view_latest",
      run_id: "run-latest",
      title: "Latest result",
      version: 2,
      payload: {
        sourceSqlArtifactId: "artifact-sql-latest",
        queryFingerprint: "query-latest",
        columns: ["count"],
        rowCount: 1,
      },
    };
    artifacts.push(latestSql, latestResult);

    render(
      <ArtifactDock
        artifacts={artifacts}
        selectedArtifactId="artifact-sql-latest"
        onOpenArtifact={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button", { name: "Latest SQL sql" })).toBeNull();
    expect(screen.getByRole("button", { name: "Latest result result view" }).getAttribute("aria-pressed"))
      .toBe("true");
    await waitFor(() => expect(agentApi.readArtifactRepresentation).toHaveBeenCalledWith(
        "artifact-result-latest",
        DATAFRAME_REPRESENTATION_TYPE,
        expect.objectContaining({ parameters: expect.objectContaining({ page: 1 }) }),
        expect.any(AbortSignal),
      ));
  });

  it("never promotes an internal safety record into the artifact dock", () => {
    render(
      <ArtifactDock
        artifacts={trustedQueryArtifacts()}
        selectedArtifactId="artifact-safety"
        onOpenArtifact={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button", { name: "Safety safety" })).toBeNull();
    expect(screen.getByRole("button", { name: "Order result result view" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("renders dock content without owning split pane resize state", () => {
    render(
        <ArtifactDock
          artifacts={trustedQueryArtifacts()}
          onOpenArtifact={vi.fn()}
      />,
    );

    const dock = screen.getByRole("complementary", { name: "Artifact dock" });

    expect(dock.getAttribute("style")).toBeNull();
    expect(screen.queryByRole("separator", { name: "调整工件区宽度" })).toBeNull();
  });
});
