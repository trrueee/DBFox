import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DataGridCell } from "../DataGridCell";

function renderCell(value: unknown, numeric = false) {
  const onSelect = vi.fn();
  const onInspect = vi.fn();
  const onContextMenu = vi.fn();

  render(
    <table>
      <tbody>
        <tr>
          <DataGridCell
            value={value}
            selected={false}
            numeric={numeric}
            onSelect={onSelect}
            onInspect={onInspect}
            onContextMenu={onContextMenu}
          />
        </tr>
      </tbody>
    </table>,
  );

  return { onSelect, onInspect, onContextMenu };
}

describe("DataGridCell", () => {
  beforeEach(() => cleanup());

  it("keeps long text preview self-contained while preserving select and inspect actions", () => {
    const value = "customer_id=1024&plan=enterprise&notes=" + "long text ".repeat(12);
    const { onSelect, onInspect } = renderCell(value);
    const cell = document.querySelector("td");

    expect(cell).toBeTruthy();
    expect(() => fireEvent.mouseEnter(cell!)).not.toThrow();

    fireEvent.click(cell!);
    expect(onSelect).toHaveBeenCalledTimes(1);

    fireEvent.doubleClick(cell!);
    expect(onInspect).toHaveBeenCalledWith(value, false);
  });

  it("keeps JSON preview self-contained while preserving JSON inspect mode", () => {
    const value = JSON.stringify({ user: "admin", flags: ["seed", "active"], quota: { rows: 20 } });
    const { onInspect } = renderCell(value);
    const cell = screen.getByText(/JSON/).closest("td");

    expect(cell).toBeTruthy();
    expect(() => fireEvent.mouseEnter(cell!)).not.toThrow();

    fireEvent.doubleClick(cell!);
    expect(onInspect).toHaveBeenCalledWith(value, true);
  });
});
