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
        sourceSqlArtifactKey: "artifact-sql-1",
        sourceSqlSemanticKey: "sql_candidate_1",
        safetyArtifactKey: "artifact-safety-1",
        safetySemanticKey: "safety_report_1",
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
    expect(model.sourceSqlArtifactId).toBe("artifact-sql-1");
    expect(model.sourceSqlSemanticId).toBe("sql_candidate_1");
    expect(model.safetyArtifactId).toBe("artifact-safety-1");
    expect(model.safetySemanticId).toBe("safety_report_1");
  });

  it("keeps legacy result_view source ids usable for conversation dock previews", () => {
    const artifact: ConversationArtifact = {
      id: "result-view-legacy",
      semantic_id: "result_view_legacy",
      type: "result_view",
      title: "Legacy result view",
      payload: {
        storageMode: "sql_backed",
        datasourceId: "ds-1",
        sourceSqlArtifactId: "legacy-sql-artifact",
        sourceSqlSemanticId: "legacy_sql_candidate",
        safetyArtifactId: "legacy-safety-artifact",
        safetySemanticId: "legacy_safety_report",
        safeSql: "SELECT total_users FROM users",
        columns: ["total_users"],
        previewRows: [{ total_users: 30 }],
      },
      depends_on: ["legacy_sql_candidate"],
      sequence: 1,
    };

    const model = toResultViewArtifactModel(artifact);

    expect(model.sourceSqlArtifactId).toBe("legacy-sql-artifact");
    expect(model.sourceSqlSemanticId).toBe("legacy_sql_candidate");
    expect(model.safetyArtifactId).toBe("legacy-safety-artifact");
    expect(model.safetySemanticId).toBe("legacy_safety_report");
  });
});
