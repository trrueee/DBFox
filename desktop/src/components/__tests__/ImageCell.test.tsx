import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ImageCell } from "../ImageCell";
import { isImageUrl } from "../imageUrl";

const { openExternalMock, saveImageMock } = vi.hoisted(() => ({
  openExternalMock: vi.fn(),
  saveImageMock: vi.fn(),
}));

vi.mock("../../lib/desktopHost", () => ({
  isEngineDesktopHost: () => true,
  openDesktopExternalHttps: openExternalMock,
  saveDesktopExternalImage: saveImageMock,
}));

describe("ImageCell", () => {
  beforeEach(() => {
    cleanup();
    openExternalMock.mockReset().mockResolvedValue(undefined);
    saveImageMock.mockReset();
  });
  afterEach(() => vi.restoreAllMocks());

  it("detects supported image URLs", () => {
    expect(isImageUrl("https://cdn.example.com/a.png")).toBe(true);
    expect(isImageUrl("https://cdn.example.com/a?x-oss-process=image/resize,w_100")).toBe(true);
    expect(isImageUrl("https://cdn.example.com/a.txt")).toBe(false);
    expect(isImageUrl("not-a-url.png")).toBe(false);
  });

  it("does not load a database-controlled remote image before preview intent", () => {
    render(<ImageCell url="https://cdn.example.com/a.png" />);

    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByText("https://cdn.example.com/a.png")).toBeTruthy();
  });

  it("loads a hover preview only after a deliberate pointer dwell", async () => {
    render(<ImageCell url="https://cdn.example.com/a.png" />);

    const trigger = screen.getByRole("button", { name: "预览图片 https://cdn.example.com/a.png" });
    fireEvent.pointerEnter(trigger);
    expect(screen.queryByRole("img")).toBeNull();

    const image = await screen.findByRole(
      "img",
      { name: "数据单元格中的图片悬浮预览" },
      { timeout: 1_000 },
    );
    expect(image.getAttribute("src")).toBe("https://cdn.example.com/a.png");
    expect(image.getAttribute("referrerpolicy")).toBe("no-referrer");
  });

  it("does not load the hover preview when the pointer leaves before the delay", async () => {
    render(<ImageCell url="https://cdn.example.com/a.png" />);

    const trigger = screen.getByRole("button", { name: "预览图片 https://cdn.example.com/a.png" });
    fireEvent.pointerEnter(trigger);
    fireEvent.pointerLeave(trigger);
    await new Promise((resolve) => setTimeout(resolve, 450));

    expect(screen.queryByRole("img")).toBeNull();
  });

  it("loads an HTTPS image in the application only after a direct user action", () => {
    render(<ImageCell url="https://cdn.example.com/a.png" />);

    expect(openExternalMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "预览图片 https://cdn.example.com/a.png" }));

    const dialog = screen.getByRole("dialog", { name: "图片预览" });
    const image = within(dialog).getByRole("img", { name: "数据单元格中的图片预览" });
    expect(image.getAttribute("src")).toBe("https://cdn.example.com/a.png");
    expect(image.getAttribute("referrerpolicy")).toBe("no-referrer");
    expect(openExternalMock).not.toHaveBeenCalled();
  });

  it("provides CSP-safe zoom, fit, actual-size, metadata, and keyboard controls", () => {
    render(<ImageCell url="https://cdn.example.com/a.png" />);

    fireEvent.click(screen.getByRole("button", { name: "预览图片 https://cdn.example.com/a.png" }));
    const dialog = screen.getByRole("dialog", { name: "图片预览" });
    const image = within(dialog).getByRole("img", { name: "数据单元格中的图片预览" });
    Object.defineProperty(image, "naturalWidth", { configurable: true, value: 1920 });
    Object.defineProperty(image, "naturalHeight", { configurable: true, value: 1080 });
    fireEvent.load(image);

    expect(within(dialog).getByText("1920 × 1080 px")).toBeTruthy();
    expect(within(dialog).getByText("适应 · 100%")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "放大图片" }));
    expect(image.getAttribute("data-zoom")).toBe("125");

    const canvas = within(dialog).getByLabelText(/图片画布/);
    fireEvent.keyDown(canvas, { key: "+" });
    expect(image.getAttribute("data-zoom")).toBe("150");
    fireEvent.keyDown(canvas, { key: "0" });
    expect(image.getAttribute("data-view-mode")).toBe("fit");
    expect(image.getAttribute("data-zoom")).toBe("100");

    fireEvent.click(within(dialog).getByRole("button", { name: "实际大小" }));
    expect(image.getAttribute("data-view-mode")).toBe("actual");
    expect(within(dialog).getByRole("button", { name: "实际大小" }).getAttribute("aria-pressed")).toBe("true");
    expect(dialog.querySelector("[style]")).toBeNull();
  });

  it("keeps external navigation as a secondary explicit action", async () => {
    render(<ImageCell url="https://cdn.example.com/a.png" />);

    fireEvent.click(screen.getByRole("button", { name: "预览图片 https://cdn.example.com/a.png" }));
    fireEvent.click(screen.getByRole("button", { name: "在浏览器打开" }));

    await waitFor(() => expect(openExternalMock).toHaveBeenCalledWith(
      "https://cdn.example.com/a.png",
    ));
  });

  it("returns focus to the image trigger when Escape closes the dialog", async () => {
    render(<ImageCell url="https://cdn.example.com/a.png" />);
    const trigger = screen.getByRole("button", { name: "预览图片 https://cdn.example.com/a.png" });
    fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "图片预览" });

    fireEvent.keyDown(dialog, { key: "Escape", code: "Escape" });

    await waitFor(() => expect(screen.queryByRole("dialog", { name: "图片预览" })).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });

  it("saves through the dedicated Host command instead of renderer file access", async () => {
    saveImageMock.mockResolvedValueOnce({ status: "saved", fileName: "a.png", byteCount: 8 });
    render(<ImageCell url="https://cdn.example.com/a.png" />);

    fireEvent.click(screen.getByRole("button", { name: "预览图片 https://cdn.example.com/a.png" }));
    fireEvent.click(screen.getByRole("button", { name: "保存副本" }));

    await waitFor(() => expect(saveImageMock).toHaveBeenCalledWith(
      "https://cdn.example.com/a.png",
    ));
    expect(await screen.findByRole("button", { name: "已保存" })).toBeTruthy();
  });

  it("shows a bounded failure state when an image cannot be decoded", () => {
    render(<ImageCell url="https://cdn.example.com/broken.png" />);

    fireEvent.click(screen.getByRole("button", { name: "预览图片 https://cdn.example.com/broken.png" }));
    fireEvent.error(screen.getByRole("img", { name: "数据单元格中的图片预览" }));

    expect(screen.getByRole("alert").textContent).toContain("图片无法预览");
  });

  it("closes and clears viewer state when a virtualized cell receives a new URL", () => {
    const view = render(<ImageCell url="https://cdn.example.com/a.png" />);
    fireEvent.click(screen.getByRole("button", { name: "预览图片 https://cdn.example.com/a.png" }));
    const image = screen.getByRole("img", { name: "数据单元格中的图片预览" });
    Object.defineProperty(image, "naturalWidth", { configurable: true, value: 800 });
    Object.defineProperty(image, "naturalHeight", { configurable: true, value: 600 });
    fireEvent.load(image);
    fireEvent.click(screen.getByRole("button", { name: "放大图片" }));

    view.rerender(<ImageCell url="https://cdn.example.com/b.png" />);

    expect(screen.queryByRole("dialog", { name: "图片预览" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "预览图片 https://cdn.example.com/b.png" }));
    const nextDialog = screen.getByRole("dialog", { name: "图片预览" });
    expect(within(nextDialog).getByText("适应 · 100%")).toBeTruthy();
    expect(within(nextDialog).queryByText("800 × 600 px")).toBeNull();
  });

  it("does not offer external navigation for non-HTTPS image URLs", () => {
    render(<ImageCell url="http://cdn.example.com/a.png" />);

    expect((screen.getByRole("button", {
      name: "预览图片 http://cdn.example.com/a.png",
    }) as HTMLButtonElement).disabled).toBe(true);
    expect(openExternalMock).not.toHaveBeenCalled();
  });
});
