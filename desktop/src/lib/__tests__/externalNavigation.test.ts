import { afterEach, describe, expect, it, vi } from "vitest";
import {
  canOpenExternalHttpsUrl,
  openUserConfirmedExternalHttpsUrl,
  parseExternalHttpsUrl,
} from "../externalNavigation";

describe("externalNavigation", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("accepts absolute HTTPS URLs without credentials", () => {
    const parsed = parseExternalHttpsUrl("https://cdn.example.com/assets/image.png?width=640");

    expect(parsed?.href).toBe("https://cdn.example.com/assets/image.png?width=640");
    expect(canOpenExternalHttpsUrl("https://cdn.example.com/assets/image.png")).toBe(true);
  });

  it.each([
    "javascript:alert(1)",
    "file:///C:/Users/Lenovo/private.png",
    "http://cdn.example.com/image.png",
    "https://alice:secret@cdn.example.com/image.png",
    "https://alice@cdn.example.com/image.png",
    " https://cdn.example.com/image.png",
    "https://cdn.example.com/image.png ",
    "not-a-url",
  ])("rejects unsafe external URL %s", (unsafeUrl) => {
    expect(parseExternalHttpsUrl(unsafeUrl)).toBeNull();
    expect(canOpenExternalHttpsUrl(unsafeUrl)).toBe(false);
  });

  it("opens only an approved URL with noopener and noreferrer", () => {
    const openedWindow = { opener: window } as unknown as Window;
    const openSpy = vi.spyOn(window, "open").mockReturnValue(openedWindow);

    expect(openUserConfirmedExternalHttpsUrl("https://cdn.example.com/image.png")).toBe(true);

    expect(openSpy).toHaveBeenCalledWith(
      "https://cdn.example.com/image.png",
      "_blank",
      "noopener,noreferrer",
    );
    expect(openedWindow.opener).toBeNull();
  });

  it("never invokes window.open for a rejected URL", () => {
    const openSpy = vi.spyOn(window, "open");

    expect(openUserConfirmedExternalHttpsUrl("file:///C:/Users/Lenovo/private.png")).toBe(false);

    expect(openSpy).not.toHaveBeenCalled();
  });
});
