import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { TableWorkspace } from "../TableWorkspace";

vi.mock("../table/TablePreviewPane", () => ({
  TablePreviewPane: () => {
    const [value, setValue] = useState("");
    return <input aria-label="预览状态" value={value} onChange={(event) => setValue(event.target.value)} />;
  },
}));

vi.mock("../table/TableSchemaPane", () => ({
  TableSchemaPane: () => <div>字段结构内容</div>,
}));

vi.mock("../table/TableErPane", () => ({
  TableErPane: () => <div>关系图内容</div>,
}));

describe("TableWorkspace", () => {
  it("preserves visited subview state while switching table tabs", () => {
    const commonProps = {
      tableId: "users",
      datasourceId: "ds-1",
      datasourceDbType: "mysql",
      onSubTabChange: vi.fn(),
      onOpenSqlConsole: vi.fn(),
      onToast: vi.fn(),
    };
    const { rerender } = render(<TableWorkspace {...commonProps} currentSubTab="preview" />);

    fireEvent.change(screen.getByLabelText("预览状态"), { target: { value: "保留我" } });
    rerender(<TableWorkspace {...commonProps} currentSubTab="schema" />);

    expect(screen.getByText("字段结构内容")).toBeTruthy();
    expect(screen.getByLabelText("预览状态").closest<HTMLElement>("[role=tabpanel]")?.hidden).toBe(true);

    rerender(<TableWorkspace {...commonProps} currentSubTab="preview" />);
    expect((screen.getByLabelText("预览状态") as HTMLInputElement).value).toBe("保留我");
  });
});
