import { describe, expect, it } from "vitest";
import { conversationTableColumns, toResultViewArtifactModel } from "../conversationArtifactModels";
import type { ConversationArtifact } from "../../../../types/conversation";

describe("conversationArtifactModels", () => {
  it("maps typed result_view columns for conversation dock previews", () => {
    const artifact: ConversationArtifact = {
      id: "result-view-1",
      semantic_id: "result_view_1",
      type: "result_view",
      title: "Result view",
      payload: {
        storageMode: "sql_backed",
        datasourceId: "ds-1",
        sourceSqlSemanticId: "sql-1",
        safeSql: "SELECT total_users FROM users",
        columns: [{ name: "total_users", type: "integer" }],
        previewRows: [{ total_users: 30 }],
        rowCount: 1,
        returnedRows: 1,
      },
      depends_on: ["sql-1"],
      sequence: 1,
    };

    expect(conversationTableColumns(artifact)).toEqual(["total_users"]);
    const model = toResultViewArtifactModel(artifact);
    expect(model.columns).toEqual(["total_users"]);
    expect(model.previewRows).toEqual([["30"]]);
  });
});
