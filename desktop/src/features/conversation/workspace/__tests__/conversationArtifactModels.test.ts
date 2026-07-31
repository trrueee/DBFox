import { describe, expect, it } from "vitest";
import { conversationTableColumns, toResultViewArtifactModel } from "../conversationArtifactModels";
import type { ConversationArtifact } from "../../../../types/conversation";

describe("conversationArtifactModels", () => {
  it("maps only the durable result descriptor", () => {
    const artifact: ConversationArtifact = {
      id: "result-view-1",
      session_id: "session-1",
      run_id: "run-1",
      turn_id: "turn-1",
      semantic_key: "result_view_1",
      version: 1,
      type: "result_view",
      title: "Result view",
      status: "completed",
      visibility: "primary",
      payload: {
        sourceSqlArtifactId: "artifact-sql-1",
        queryFingerprint: "query-users",
        datasourceGeneration: 1,
        columns: [{ name: "total_users", type: "integer" }],
        rowCount: 1,
        returnedRows: 1,
        latencyMs: 2,
        executedAt: "2026-07-19T00:00:00Z",
        truncated: false,
      },
      provenance: {},
      relations: [{ relation: "executed_as", artifact_id: "sql-1" }],
    };

    expect(conversationTableColumns(artifact)).toEqual(["total_users"]);
    const model = toResultViewArtifactModel(artifact);
    expect(model.columns).toEqual(["total_users"]);
    expect(model.sourceSqlArtifactId).toBe("artifact-sql-1");
    expect(model.queryFingerprint).toBe("query-users");
    expect(model).not.toHaveProperty("previewRows");
  });

});
