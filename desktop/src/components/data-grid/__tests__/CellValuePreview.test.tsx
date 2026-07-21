import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { CellValuePreview } from "../CellValuePreview";
import { cellValueToText, isCellValuePreviewable } from "../cellValue";

describe("CellValuePreview", () => {
  beforeEach(() => cleanup());

  it("renders long text through a bounded preview trigger", () => {
    const value = "payload=" + "segment-".repeat(12);

    render(<CellValuePreview value={value} detailHint="Click to copy" />);

    const trigger = screen.getByText(/payload=segment/).closest(".dbfox-cell-preview-trigger");
    if (!trigger) throw new Error("Expected long text preview trigger");
    expect(trigger.className).toContain("dbfox-cell-preview-trigger");
    expect(screen.getByText("键值").className).toContain("dbfox-cell-preview-kind");
    expect(screen.getByText(/payload=segment/).className).toContain("dbfox-cell-preview-snippet");
    expect(isCellValuePreviewable(value)).toBe(true);
    expect(() => fireEvent.mouseEnter(trigger)).not.toThrow();
  });

  it("summarizes JSON values before the hover preview opens", () => {
    render(<CellValuePreview value={JSON.stringify({ user: "admin", roles: ["owner", "ops"] })} />);

    expect(screen.getByText(/JSON/).className).toContain("dbfox-cell-preview-json-pill");
    expect(screen.getByText(/Object/)).toBeTruthy();
  });

  it("keeps normal short values lightweight", () => {
    render(<CellValuePreview value="alpha" />);

    expect(screen.getByText("alpha").className).toContain("dbfox-cell-preview-text");
    expect(isCellValuePreviewable("alpha")).toBe(false);
    expect(cellValueToText(null)).toBe("");
  });
});
