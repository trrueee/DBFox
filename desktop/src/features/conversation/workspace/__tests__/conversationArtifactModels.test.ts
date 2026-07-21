import { describe, expect, it } from "vitest";
import { conversationTableColumns, toResultViewArtifactModel } from "../conversationArtifactModels";
import type { ConversationArtifact } from "../../../../types/conversation";

describe("conversationArtifactModels", () => {
  it("maps only the durable result descriptor", () => {
    const artifact: ConversationArtifact = {
      id: "result-view-1",
      semantic_id: "result_view_1",
      type: "result_view",
      title: "Result view",
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
      depends_on: ["sql-1"],
      sequence: 1,
    };

    expect(conversationTableColumns(artifact)).toEqual(["total_users"]);
    const model = toResultViewArtifactModel(artifact);
    expect(model.columns).toEqual(["total_users"]);
    expect(model.sourceSqlArtifactId).toBe("artifact-sql-1");
    expect(model.queryFingerprint).toBe("query-users");
    expect(model).not.toHaveProperty("previewRows");
  });

});
