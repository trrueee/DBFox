import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DataTable } from "../../DataTable";
import { TooltipProvider } from "../../ui";

describe("DataTable context menu", () => {
  beforeEach(() => {
    cleanup();
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  it("opens a cell context menu through Radix and preserves copy/filter actions", async () => {
    renderDataTable({
      columns: ["id", "name"],
      rows: [{ id: 1, name: "alpha" }],
      tableName: "users",
    });

    fireEvent.contextMenu(screen.getByText("alpha"));
    fireEvent.click(screen.getByRole("menuitem", { name: "复制单元格" }));

    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith("alpha"));

    fireEvent.contextMenu(screen.getByText("alpha"));
    fireEvent.click(screen.getByRole("menuitem", { name: "按当前值筛选" }));

    expect(screen.getByText("name 包含 alpha")).toBeTruthy();
  });

  it("renders large data sets through a virtual row window", () => {
    const rows = Array.from({ length: 200 }, (_, index) => ({
      id: index + 1,
      name: `row-${index + 1}`,
    }));

    const { container } = renderDataTable({
      columns: ["id", "name"],
      rows,
      tableName: "users",
    });

    expect(screen.getByText("row-1")).toBeTruthy();
    expect(container.querySelector(".data-grid-virtual-spacer")).toBeTruthy();
    expect(container.querySelectorAll("tbody tr").length).toBeLessThan(80);
    expect(screen.queryByText("row-200")).toBeNull();
  });

  it("keeps sort, filter, and hidden-column actions working through the table core", async () => {
    const { container } = renderDataTable({
      columns: ["id", "name"],
      rows: [
        { id: 1, name: "beta" },
        { id: 2, name: "alpha" },
      ],
      tableName: "users",
    });

    const nameHeaderButton = screen.getByRole("button", { name: /name/ });
    fireEvent.pointerDown(nameHeaderButton, { button: 0, ctrlKey: false });
    fireEvent.click(screen.getAllByRole("menuitem")[0]);

    expect(firstRenderedNameCell()).toBe("alpha");

    fireEvent.pointerDown(nameHeaderButton, { button: 0, ctrlKey: false });
    const filterInput = document.querySelector(".data-grid-menu-input");
    if (!filterInput) throw new Error("Expected column filter input to be rendered");
    fireEvent.change(filterInput, { target: { value: "beta" } });

    await waitFor(() => expect(screen.queryByText("alpha")).toBeNull());
    expect(screen.getByText("beta")).toBeTruthy();

    const menuItems = await screen.findAllByRole("menuitem");
    fireEvent.click(menuItems[menuItems.length - 1]);

    expect(screen.queryByText("beta")).toBeNull();
    expect(Array.from(container.querySelectorAll(".data-grid-chip")).some((chip) => chip.textContent?.includes("1"))).toBe(true);
  });
});

function renderDataTable(props: React.ComponentProps<typeof DataTable>) {
  return render(
    <TooltipProvider>
      <DataTable {...props} />
    </TooltipProvider>,
  );
}

function firstRenderedNameCell() {
  const cells = Array.from(document.querySelectorAll(".data-grid-cell--text"));
  return cells[0]?.textContent;
}
