import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CellValuePreview } from "../CellValuePreview";
import { cellValueToText, isCellValuePreviewable } from "../cellValue";

const { openExternalMock } = vi.hoisted(() => ({
  openExternalMock: vi.fn(),
}));

vi.mock("../../../lib/desktopHost", () => ({
  isEngineDesktopHost: () => true,
  openDesktopExternalHttps: openExternalMock,
  saveDesktopExternalImage: vi.fn(),
}));

describe("CellValuePreview", () => {
  beforeEach(() => {
    cleanup();
    openExternalMock.mockReset().mockResolvedValue(undefined);
  });

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

  it("routes image URLs through the shared on-demand image viewer", () => {
    render(<CellValuePreview value="https://cdn.example.com/photo.webp" />);

    expect(screen.getByRole("button", { name: "预览图片 https://cdn.example.com/photo.webp" })).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("previews an ordinary HTTPS link before explicitly opening the browser", () => {
    const { rerender } = render(<CellValuePreview value="https://example.com/report?id=7" />);

    fireEvent.click(screen.getByRole("button", { name: "查看链接 https://example.com/report?id=7" }));
    expect(screen.getByRole("dialog", { name: "链接" })).toBeTruthy();
    expect(openExternalMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "在浏览器打开" }));
    expect(openExternalMock).toHaveBeenCalledWith("https://example.com/report?id=7");

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    rerender(<CellValuePreview value="javascript:alert(1)" />);
    expect(screen.queryByRole("button", { name: /查看链接/ })).toBeNull();
    expect(screen.getByText("javascript:alert(1)").className).toContain("dbfox-cell-preview-text");
  });

  it("uses one viewer contract for JSON and binary placeholders", () => {
    const { rerender } = render(
      <CellValuePreview value={{ enabled: true }} dataType="jsonb" columnName="payload" />,
    );

    fireEvent.click(screen.getByRole("button", { name: /JSON · Object/ }));
    expect(screen.getByRole("dialog", { name: "JSON 值 · payload" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    rerender(<CellValuePreview value="<binary>" dataType="blob" columnName="content" />);
    fireEvent.click(screen.getByRole("button", { name: /原始字节未加载/ }));
    expect(screen.getByRole("dialog", { name: "二进制值 · content" }).textContent).toContain("不会把占位符伪装成可下载文件");
  });
});
