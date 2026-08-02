import { afterEach, describe, expect, it, vi } from "vitest";
import { getClientLogSource, recordClientLog } from "../clientLog";
import redactionContractJson from "../../../../../test-fixtures/redaction-contract.json";

const redactionContract = redactionContractJson as {
  textCases: Array<{ id: string; input: string; forbidden: string[]; required: string[] }>;
  structuredCases: Array<{ id: string; input: unknown; forbidden: string[]; required: string[] }>;
  recursiveCase: { safeValue: string; secretValue: string };
  oversizedCase: { prefix: string; fill: string; repeat: number; forbidden: string[] };
};

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("clientLog", () => {
  it("satisfies the shared cross-language redaction contract", () => {
    for (const testCase of redactionContract.textCases) {
      recordClientLog("error", testCase.input);
    }
    for (const testCase of redactionContract.structuredCases) {
      recordClientLog("error", testCase.id, testCase.input);
    }

    const content = getClientLogSource().content;
    for (const testCase of [...redactionContract.textCases, ...redactionContract.structuredCases]) {
      for (const forbidden of testCase.forbidden) expect(content).not.toContain(forbidden);
      for (const required of testCase.required) expect(content).toContain(required);
    }
  });

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

  it("preserves structured error diagnostics without retaining secrets", () => {
    const error = Object.assign(new Error("Request failed"), {
      status: 401,
      code: "UNAUTHORIZED_ENGINE_ACCESS",
      detail: { token: "local-secret", reason: "expired" },
    });

    recordClientLog("error", "Conversation initialization failed", error);

    const content = getClientLogSource().content;
    expect(content).toContain('"status":401');
    expect(content).toContain('"code":"UNAUTHORIZED_ENGINE_ACCESS"');
    expect(content).toContain('"token":"[REDACTED]"');
    expect(content).not.toContain("local-secret");
  });

  it("drops diagnostic entries older than the seven-day retention window", () => {
    localStorage.setItem("dbfox.clientLogs.v1", JSON.stringify([
      {
        at: new Date(Date.now() - 8 * 24 * 60 * 60 * 1_000).toISOString(),
        level: "error",
        message: "stale failure",
      },
      {
        at: new Date().toISOString(),
        level: "info",
        message: "current entry",
      },
    ]));

    const content = getClientLogSource().content;
    expect(content).not.toContain("stale failure");
    expect(content).toContain("current entry");
  });

  it("records circular values without breaking the application", () => {
    const circular: Record<string, unknown> = { phase: "render" };
    circular.self = circular;

    expect(() => recordClientLog("error", "Circular diagnostic", circular)).not.toThrow();
    expect(getClientLogSource().content).toContain('"self":"[Circular]"');
  });

  it("bounds a single diagnostic detail", () => {
    recordClientLog("error", "Large diagnostic", { value: "x".repeat(32 * 1024) });

    expect(getClientLogSource().content.length).toBeLessThan(17 * 1024);
  });

  it("applies shared recursive and oversized contracts without throwing", () => {
    const recursive: Record<string, unknown> = {
      safe: redactionContract.recursiveCase.safeValue,
      token: redactionContract.recursiveCase.secretValue,
    };
    recursive.self = recursive;
    expect(() => recordClientLog("error", "recursive", recursive)).not.toThrow();

    const oversized = redactionContract.oversizedCase;
    const oversizedText = oversized.prefix + oversized.fill.repeat(oversized.repeat);
    recordClientLog("error", oversizedText, {
      value: oversizedText,
    });
    const content = getClientLogSource().content;
    expect(content).toContain(redactionContract.recursiveCase.safeValue);
    expect(content).not.toContain(redactionContract.recursiveCase.secretValue);
    for (const forbidden of oversized.forbidden) expect(content).not.toContain(forbidden);
    expect(content.length).toBeLessThan(20 * 1024);
  });
});
