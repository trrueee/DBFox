import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CellValuePreview } from "../CellValuePreview";

afterEach(() => cleanup());

describe("CellValuePreview overlay coordination", () => {
  it("closes the hover preview when the full JSON dialog opens", async () => {
    render(<CellValuePreview value={{ answer: 42 }} dataType="jsonb" columnName="payload" />);

    const trigger = screen.getByRole("button", { name: "JSON · Object(1)" });
    fireEvent.pointerEnter(trigger);
    expect(await screen.findByText("点击打开完整查看")).toBeTruthy();

    fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "JSON 值 · payload" });
    expect(within(dialog).getByRole("tree", { name: "JSON 结构" })).toBeTruthy();
    expect(screen.queryByText("点击打开完整查看")).toBeNull();
  });
});
