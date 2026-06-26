import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { ImageCell, isImageUrl } from "../ImageCell";

describe("ImageCell", () => {
  beforeEach(() => cleanup());

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
});
