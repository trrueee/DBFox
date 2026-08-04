import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  canOpenExternalHttpsUrl,
  openUserConfirmedExternalHttpsUrl,
  parseExternalHttpsUrl,
} from "../externalNavigation";

const { invokeMock, isTauriMock } = vi.hoisted(() => ({
  invokeMock: vi.fn(),
  isTauriMock: vi.fn(),
}));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: invokeMock,
  isTauri: isTauriMock,
}));

describe("externalNavigation", () => {
  beforeEach(() => {
    invokeMock.mockReset().mockResolvedValue(undefined);
    isTauriMock.mockReset().mockReturnValue(true);
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

  it("delegates an approved URL to the policy-validated Rust command", async () => {
    await expect(openUserConfirmedExternalHttpsUrl("https://cdn.example.com/image.png")).resolves.toBe(true);

    expect(invokeMock).toHaveBeenCalledWith("open_external_https_url", {
      url: "https://cdn.example.com/image.png",
    });
  });

  it("never invokes the host for a rejected URL", async () => {
    await expect(openUserConfirmedExternalHttpsUrl("file:///C:/Users/Lenovo/private.png")).resolves.toBe(false);

    expect(invokeMock).not.toHaveBeenCalled();
  });

  it("does not add a browser fallback outside Tauri", async () => {
    isTauriMock.mockReturnValue(false);

    await expect(openUserConfirmedExternalHttpsUrl("https://cdn.example.com/image.png")).resolves.toBe(false);
    expect(invokeMock).not.toHaveBeenCalled();
  });
});
