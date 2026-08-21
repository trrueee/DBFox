import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  canOpenExternalHttpsUrl,
  canSaveExternalImage,
  openUserConfirmedExternalHttpsUrl,
  parseExternalHttpsUrl,
  saveUserConfirmedExternalImage,
} from "../externalNavigation";

const { hostAvailableMock, openExternalMock, saveImageMock } = vi.hoisted(() => ({
  hostAvailableMock: vi.fn(),
  openExternalMock: vi.fn(),
  saveImageMock: vi.fn(),
}));

vi.mock("../desktopHost", () => ({
  isEngineDesktopHost: hostAvailableMock,
  openDesktopExternalHttps: openExternalMock,
  saveDesktopExternalImage: saveImageMock,
}));

describe("externalNavigation", () => {
  beforeEach(() => {
    openExternalMock.mockReset().mockResolvedValue(undefined);
    saveImageMock.mockReset();
    hostAvailableMock.mockReset().mockReturnValue(true);
  });

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

  it("delegates an approved URL to the policy-validated Electron Host", async () => {
    await expect(openUserConfirmedExternalHttpsUrl("https://cdn.example.com/image.png")).resolves.toBe(true);

    expect(openExternalMock).toHaveBeenCalledWith("https://cdn.example.com/image.png");
  });

  it("delegates image saving to the dedicated Electron boundary", async () => {
    saveImageMock.mockResolvedValueOnce({ status: "saved", fileName: "image.png", byteCount: 12 });

    await expect(saveUserConfirmedExternalImage("https://cdn.example.com/image.png")).resolves.toEqual({
      status: "saved",
      fileName: "image.png",
      byteCount: 12,
    });
    expect(canSaveExternalImage("https://cdn.example.com/image.png")).toBe(true);
    expect(saveImageMock).toHaveBeenCalledWith("https://cdn.example.com/image.png");
  });

  it("never invokes the host for a rejected URL", async () => {
    await expect(openUserConfirmedExternalHttpsUrl("file:///C:/Users/Lenovo/private.png")).resolves.toBe(false);

    expect(openExternalMock).not.toHaveBeenCalled();
  });

  it("does not add a browser fallback outside Electron", async () => {
    hostAvailableMock.mockReturnValue(false);

    await expect(openUserConfirmedExternalHttpsUrl("https://cdn.example.com/image.png")).resolves.toBe(false);
    expect(canSaveExternalImage("https://cdn.example.com/image.png")).toBe(false);
    expect(openExternalMock).not.toHaveBeenCalled();
  });
});
