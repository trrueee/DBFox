import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ImageCell } from "../ImageCell";
import { isImageUrl } from "../imageUrl";

describe("ImageCell", () => {
  beforeEach(() => cleanup());
  afterEach(() => vi.restoreAllMocks());

  it("detects supported image URLs", () => {
    expect(isImageUrl("https://cdn.example.com/a.png")).toBe(true);
    expect(isImageUrl("https://cdn.example.com/a?x-oss-process=image/resize,w_100")).toBe(true);
    expect(isImageUrl("https://cdn.example.com/a.txt")).toBe(false);
    expect(isImageUrl("not-a-url.png")).toBe(false);
  });

  it("opens the full image in a dialog when clicked", () => {
    render(<ImageCell url="https://cdn.example.com/a.png" />);

    fireEvent.click(screen.getByRole("button", { name: "预览图片 https://cdn.example.com/a.png" }));

    const dialog = screen.getByRole("dialog", { name: "图片预览" });
    expect(dialog).toBeTruthy();
    expect(within(dialog).getAllByText("https://cdn.example.com/a.png").length).toBeGreaterThan(0);
  });

  it("opens an HTTPS original only after the user clicks the lightbox action", () => {
    const openedWindow = { opener: window } as unknown as Window;
    const openSpy = vi.spyOn(window, "open").mockReturnValue(openedWindow);
    render(<ImageCell url="https://cdn.example.com/a.png" />);

    expect(openSpy).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "预览图片 https://cdn.example.com/a.png" }));
    fireEvent.click(screen.getByRole("button", { name: "打开原图" }));

    expect(openSpy).toHaveBeenCalledWith("https://cdn.example.com/a.png", "_blank", "noopener,noreferrer");
    expect(openedWindow.opener).toBeNull();
  });

  it("does not offer external navigation for non-HTTPS image URLs", () => {
    render(<ImageCell url="http://cdn.example.com/a.png" />);

    fireEvent.click(screen.getByRole("button", { name: "预览图片 http://cdn.example.com/a.png" }));

    expect((screen.getByRole("button", { name: "打开原图" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
