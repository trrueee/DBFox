import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ConversationArtifact } from "../../../../types/conversation";
import { ArtifactEvidencePanel } from "../ArtifactEvidencePanel";

describe("ArtifactEvidencePanel", () => {
  it("groups SQL, table, and chart by depends_on", () => {
    const artifacts: ConversationArtifact[] = [
      {
        id: "sql-1",
        conversation_id: "conv",
        run_id: "run",
        message_id: "assistant",
        type: "sql",
        title: "SQL 1",
        status: "completed",
        sequence: 1,
        payload: { sql: "select 1" },
        depends_on: [],
      },
      {
        id: "table-1",
        conversation_id: "conv",
        run_id: "run",
        message_id: "assistant",
        type: "table",
        title: "Rows",
        status: "completed",
        sequence: 2,
        payload: { columns: ["value"], rows: [{ value: 1 }] },
        depends_on: ["sql-1"],
      },
      {
        id: "chart-1",
        conversation_id: "conv",
        run_id: "run",
        message_id: "assistant",
        type: "chart",
        title: "Chart",
        status: "completed",
        sequence: 3,
        payload: { type: "bar", series: [{ label: "A", value: 1 }] },
        depends_on: ["table-1"],
      },
    ];

    render(<ArtifactEvidencePanel artifacts={artifacts} onOpenSqlConsole={vi.fn()} />);

    expect(screen.getByText("SQL 1")).toBeTruthy();
    expect(screen.getByText("Rows")).toBeTruthy();
    expect(screen.getByText("Chart")).toBeTruthy();
  });
});
