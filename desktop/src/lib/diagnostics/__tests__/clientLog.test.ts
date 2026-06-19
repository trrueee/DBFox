import { afterEach, describe, expect, it, vi } from "vitest";
import { getClientLogSource, recordClientLog } from "../clientLog";

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("clientLog", () => {
  it("stores frontend runtime logs as a sanitized diagnostic source", () => {
    recordClientLog("error", "Request failed api_key=secret-key", {
      password: "plain-password",
    });

    const source = getClientLogSource();

    expect(source.name).toBe("frontend-client");
    expect(source.exists).toBe(true);
    expect(source.content).toContain("Request failed api_key=[REDACTED]");
    expect(source.content).toContain('"password":"[REDACTED]"');
    expect(source.content).not.toContain("secret-key");
    expect(source.content).not.toContain("plain-password");
  });
});
