import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ImageCell } from "../ImageCell";
import { isImageUrl } from "../imageUrl";

const { invokeMock, isTauriMock } = vi.hoisted(() => ({
  invokeMock: vi.fn(),
  isTauriMock: vi.fn(),
}));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: invokeMock,
  isTauri: isTauriMock,
}));

describe("ImageCell", () => {
  beforeEach(() => {
    cleanup();
    invokeMock.mockReset().mockResolvedValue(undefined);
    isTauriMock.mockReset().mockReturnValue(true);
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
      { name: "数据库单元格中的图片悬浮预览" },
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

    expect(invokeMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "预览图片 https://cdn.example.com/a.png" }));

    const dialog = screen.getByRole("dialog", { name: "图片预览" });
    const image = within(dialog).getByRole("img", { name: "数据库单元格中的图片预览" });
    expect(image.getAttribute("src")).toBe("https://cdn.example.com/a.png");
    expect(image.getAttribute("referrerpolicy")).toBe("no-referrer");
    expect(invokeMock).not.toHaveBeenCalled();
  });

  it("keeps external navigation as a secondary explicit action", async () => {
    render(<ImageCell url="https://cdn.example.com/a.png" />);

    fireEvent.click(screen.getByRole("button", { name: "预览图片 https://cdn.example.com/a.png" }));
    fireEvent.click(screen.getByRole("button", { name: "在浏览器打开" }));

    await waitFor(() => expect(invokeMock).toHaveBeenCalledWith("open_external_https_url", {
      url: "https://cdn.example.com/a.png",
    }));
  });

  it("saves through the dedicated Host command instead of renderer file access", async () => {
    invokeMock.mockResolvedValueOnce({ status: "saved", fileName: "a.png", byteCount: 8 });
    render(<ImageCell url="https://cdn.example.com/a.png" />);

    fireEvent.click(screen.getByRole("button", { name: "预览图片 https://cdn.example.com/a.png" }));
    fireEvent.click(screen.getByRole("button", { name: "保存副本" }));

    await waitFor(() => expect(invokeMock).toHaveBeenCalledWith("save_external_image", {
      url: "https://cdn.example.com/a.png",
    }));
    expect(await screen.findByRole("button", { name: "已保存" })).toBeTruthy();
  });

  it("shows a bounded failure state when an image cannot be decoded", () => {
    render(<ImageCell url="https://cdn.example.com/broken.png" />);

    fireEvent.click(screen.getByRole("button", { name: "预览图片 https://cdn.example.com/broken.png" }));
    fireEvent.error(screen.getByRole("img", { name: "数据库单元格中的图片预览" }));

    expect(screen.getByRole("alert").textContent).toContain("图片无法预览");
  });

  it("does not offer external navigation for non-HTTPS image URLs", () => {
    render(<ImageCell url="http://cdn.example.com/a.png" />);

    expect((screen.getByRole("button", {
      name: "预览图片 http://cdn.example.com/a.png",
    }) as HTMLButtonElement).disabled).toBe(true);
    expect(invokeMock).not.toHaveBeenCalled();
  });
});
