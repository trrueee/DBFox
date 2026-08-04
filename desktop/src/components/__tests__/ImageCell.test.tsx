import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

  it("does not load a database-controlled remote image inside the WebView", () => {
    render(<ImageCell url="https://cdn.example.com/a.png" />);

    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByText("https://cdn.example.com/a.png")).toBeTruthy();
  });

  it("opens an HTTPS image only after a direct user action", async () => {
    render(<ImageCell url="https://cdn.example.com/a.png" />);

    expect(invokeMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "在系统浏览器打开图片 https://cdn.example.com/a.png" }));

    await waitFor(() => expect(invokeMock).toHaveBeenCalledWith("open_external_https_url", {
      url: "https://cdn.example.com/a.png",
    }));
  });

  it("does not offer external navigation for non-HTTPS image URLs", () => {
    render(<ImageCell url="http://cdn.example.com/a.png" />);

    expect((screen.getByRole("button", {
      name: "在系统浏览器打开图片 http://cdn.example.com/a.png",
    }) as HTMLButtonElement).disabled).toBe(true);
    expect(invokeMock).not.toHaveBeenCalled();
  });
});
