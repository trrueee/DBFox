import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "../../ui";
import { DataGridHeaderCell } from "../DataGridHeaderCell";

describe("DataGridHeaderCell", () => {
  beforeEach(() => cleanup());

  it("opens column actions through a dropdown menu and preserves sort/filter actions", () => {
    const onSort = vi.fn();
    const onFilter = vi.fn();

    render(
      <TooltipProvider>
      <DataGridHeaderCell
        column="id"
        typeInfo={{ dataType: "bigint", isPrimaryKey: true, isForeignKey: false }}
        sortState={null}
        onSort={onSort}
        onClearSort={vi.fn()}
        onFilter={onFilter}
        onClearFilter={vi.fn()}
        onCopyColumnName={vi.fn()}
        onCopySelectColumn={vi.fn()}
        onHideColumn={vi.fn()}
      />
      </TooltipProvider>,
    );

    fireEvent.pointerDown(screen.getByRole("button", { name: "列操作 id" }), { button: 0, ctrlKey: false });
    fireEvent.click(screen.getByRole("menuitem", { name: /升序排序/ }));

    expect(onSort).toHaveBeenCalledWith("asc");

    fireEvent.pointerDown(screen.getByRole("button", { name: "列操作 id" }), { button: 0, ctrlKey: false });
    fireEvent.change(screen.getByPlaceholderText("搜索当前列值..."), { target: { value: "42" } });

    expect(onFilter).toHaveBeenCalledWith("contains", "42");
  });
});
