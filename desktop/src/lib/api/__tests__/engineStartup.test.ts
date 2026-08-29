import { afterEach, describe, expect, it, vi } from "vitest";

const { invokeMock, desktopHostMock } = vi.hoisted(() => ({
  invokeMock: vi.fn(),
  desktopHostMock: vi.fn(() => false),
}));

vi.mock("../../desktopHost", () => ({
  isEngineDesktopHost: desktopHostMock,
  getDesktopEngineConfig: () => invokeMock("get_engine_config"),
  getDesktopEngineStatus: () => invokeMock("get_engine_startup_status"),
  subscribeDesktopEngineState: () => Promise.resolve(() => undefined),
}));

import { fetchEnginePath, initEngineConfig, waitForEngineConfig } from "../client";
import { listConversations } from "../../../features/conversation/conversationRepository";

function engineConfig(port: number, token: string, generation = 1) {
  return {
    port,
    token,
    generation,
    protocolVersion: 1,
    serverInfo: { name: "dbfox-engine", version: "1.0.3" },
    capabilities: ["http", "sse", "problem-details"],
  };
}

function enableDesktopRuntime(): void {
  desktopHostMock.mockReturnValue(true);
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

afterEach(() => {
  invokeMock.mockReset();
  desktopHostMock.mockReset();
  desktopHostMock.mockReturnValue(false);
  vi.unstubAllGlobals();
});
describe("local engine startup coordination", () => {
  it("waits for the host lifecycle to become ready before requesting a port", async () => {
    enableDesktopRuntime();
    const states: string[] = [];
    invokeMock
      .mockResolvedValueOnce({ state: "starting", error: null })
      .mockResolvedValueOnce({ state: "ready", error: null, generation: 1 })
      .mockResolvedValueOnce(engineConfig(18731, "test-engine-token"));

    await waitForEngineConfig({
      attempts: 3,
      intervalMs: 0,
      onStatus(status) {
        states.push(status.state);
      },
    });

    expect(states).toEqual(["starting", "ready"]);
    expect(invokeMock.mock.calls.map(([command]) => command)).toEqual([
      "get_engine_startup_status",
      "get_engine_startup_status",
      "get_engine_config",
    ]);
  });

  it("fails fast when the host reports a terminal startup failure", async () => {
    enableDesktopRuntime();
    invokeMock.mockResolvedValueOnce({ state: "failed", error: "sidecar exited" });

    await expect(waitForEngineConfig({ attempts: 3, intervalMs: 0 })).rejects.toMatchObject({
      code: "ENGINE_STARTUP_FAILED",
      status: 503,
    });
    expect(invokeMock).toHaveBeenCalledTimes(1);
  });

  it("rejects an invalid host engine configuration", async () => {
    enableDesktopRuntime();
    invokeMock.mockResolvedValueOnce(engineConfig(0, ""));

    await expect(initEngineConfig()).rejects.toMatchObject({
      code: "ENGINE_CONFIG_INVALID",
      status: 503,
    });
  });

  it("refreshes the desktop token once and retries a rejected request", async () => {
    enableDesktopRuntime();
    invokeMock
      .mockResolvedValueOnce(engineConfig(18731, "stale-token"))
      .mockResolvedValueOnce(engineConfig(18732, "fresh-token", 2));
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        type: "urn:dbfox:problem:unauthorized-engine-access",
        title: "Unauthorized",
        status: 401,
        detail: "A valid local engine token is required.",
        instance: "/api/v1/conversations",
        code: "UNAUTHORIZED_ENGINE_ACCESS",
        request_id: "request-1",
      }), {
        status: 401,
        headers: { "Content-Type": "application/problem+json" },
      }))
      .mockResolvedValueOnce(new Response("[]", {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }));
    vi.stubGlobal("fetch", fetchMock);

    await initEngineConfig();
    await expect(listConversations()).resolves.toEqual([]);

    expect(invokeMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const firstRequest = fetchMock.mock.calls[0][0] as Request;
    const secondRequest = fetchMock.mock.calls[1][0] as Request;
    expect(new URL(firstRequest.url).pathname).toBe("/api/v1/conversations");
    expect(new URL(secondRequest.url).pathname).toBe("/api/v1/conversations");
    expect(firstRequest.headers.get("X-Local-Token")).toBe("stale-token");
    expect(secondRequest.headers.get("X-Local-Token")).toBe("fresh-token");
    expect(new URL(firstRequest.url).port).toBe("18731");
    expect(new URL(secondRequest.url).port).toBe("18732");
  });

  it("waits for a newer generation before replaying a failed safe request", async () => {
    enableDesktopRuntime();
    invokeMock
      .mockResolvedValueOnce(engineConfig(18731, "old-token", 7))
      .mockRejectedValueOnce(new Error("engine is restarting"))
      .mockResolvedValueOnce({ state: "restarting", generation: 7, restartCount: 1 })
      .mockResolvedValueOnce({ state: "ready", generation: 8, restartCount: 1 })
      .mockResolvedValueOnce(engineConfig(18744, "new-token", 8));
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("fetch failed"))
      .mockResolvedValueOnce(new Response("[]", {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }));
    vi.stubGlobal("fetch", fetchMock);

    await initEngineConfig();
    await expect(listConversations()).resolves.toEqual([]);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const retriedRequest = fetchMock.mock.calls[1][0] as Request;
    expect(new URL(retriedRequest.url).port).toBe("18744");
    expect(retriedRequest.headers.get("X-Local-Token")).toBe("new-token");
  });

  it("keeps crash recovery independent when a concurrent 401 caller is cancelled", async () => {
    enableDesktopRuntime();
    const sharedSnapshot = deferred<ReturnType<typeof engineConfig>>();
    invokeMock
      .mockResolvedValueOnce(engineConfig(18731, "old-token", 10))
      .mockReturnValueOnce(sharedSnapshot.promise)
      .mockResolvedValueOnce({ state: "ready", generation: 11, restartCount: 1 })
      .mockResolvedValueOnce(engineConfig(18744, "new-token", 11));
    const firstController = new AbortController();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        type: "about:blank",
        title: "Unauthorized",
        status: 401,
        detail: "Token expired",
        code: "UNAUTHORIZED",
      }), { status: 401, headers: { "Content-Type": "application/problem+json" } }))
      .mockRejectedValueOnce(new TypeError("old engine exited"))
      .mockResolvedValueOnce(new Response("[]", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await initEngineConfig();
    const cancelled401 = fetchEnginePath("/conversations", {
      method: "GET",
      signal: firstController.signal,
    });
    const recoveredNetworkRequest = fetchEnginePath("/conversations", { method: "GET" });
    await vi.waitFor(() => expect(invokeMock).toHaveBeenCalledTimes(2));

    firstController.abort();
    sharedSnapshot.resolve(engineConfig(18731, "old-token", 10));

    await expect(cancelled401).rejects.toMatchObject({ name: "AbortError" });
    await expect(recoveredNetworkRequest).resolves.toMatchObject({ status: 200 });
    const replay = fetchMock.mock.calls[2][0] as Request;
    expect(new URL(replay.url).port).toBe("18744");
    expect(replay.headers.get("X-Local-Token")).toBe("new-token");
  });

  it("does not let a cancelled crash recovery abort a concurrent ordinary refresh", async () => {
    enableDesktopRuntime();
    const sharedSnapshot = deferred<ReturnType<typeof engineConfig>>();
    invokeMock
      .mockResolvedValueOnce(engineConfig(18800, "old-token", 20))
      .mockReturnValueOnce(sharedSnapshot.promise);
    const recoveryController = new AbortController();
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("engine exited"))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        type: "about:blank",
        title: "Unauthorized",
        status: 401,
        detail: "Token expired",
        code: "UNAUTHORIZED",
      }), { status: 401, headers: { "Content-Type": "application/problem+json" } }))
      .mockResolvedValueOnce(new Response("[]", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await initEngineConfig();
    const cancelledRecovery = fetchEnginePath("/conversations", {
      method: "GET",
      signal: recoveryController.signal,
    });
    const ordinaryRefresh = fetchEnginePath("/conversations", { method: "GET" });
    await vi.waitFor(() => expect(invokeMock).toHaveBeenCalledTimes(2));

    recoveryController.abort();
    sharedSnapshot.resolve(engineConfig(18801, "fresh-token", 21));

    await expect(cancelledRecovery).rejects.toMatchObject({ name: "AbortError" });
    await expect(ordinaryRefresh).resolves.toMatchObject({ status: 200 });
    const replay = fetchMock.mock.calls[2][0] as Request;
    expect(new URL(replay.url).port).toBe("18801");
    expect(replay.headers.get("X-Local-Token")).toBe("fresh-token");
  });

  it("evaluates different required generations independently after one shared snapshot", async () => {
    enableDesktopRuntime();
    const sharedSnapshot = deferred<ReturnType<typeof engineConfig>>();
    let configRequest = 0;
    invokeMock.mockImplementation((command: string) => {
      if (command === "get_engine_startup_status") {
        return Promise.resolve({ state: "ready", generation: 32, restartCount: 2 });
      }
      configRequest += 1;
      if (configRequest === 1) return Promise.resolve(engineConfig(19030, "token-30", 30));
      if (configRequest === 2) return sharedSnapshot.promise;
      if (configRequest === 3) return Promise.resolve(engineConfig(19031, "token-31", 31));
      return Promise.resolve(engineConfig(19032, "token-32", 32));
    });
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("generation 30 exited"))
      .mockRejectedValueOnce(new TypeError("generation 31 exited"))
      .mockResolvedValueOnce(new Response("first", { status: 200 }))
      .mockResolvedValueOnce(new Response("second", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await initEngineConfig();
    const needsAfter30 = fetchEnginePath("/health", { method: "GET" });
    await vi.waitFor(() => expect(configRequest).toBe(2));
    await initEngineConfig();
    const needsAfter31 = fetchEnginePath("/health", { method: "GET" });
    sharedSnapshot.resolve(engineConfig(19030, "token-30", 30));

    await expect(needsAfter30).resolves.toMatchObject({ status: 200 });
    await expect(needsAfter31).resolves.toMatchObject({ status: 200 });
    const replayPorts = fetchMock.mock.calls.slice(2).map(([request]) => new URL((request as Request).url).port);
    expect(replayPorts).toEqual(["19031", "19032"]);
  });

  it("never replays a non-idempotent request after an ambiguous network failure", async () => {
    enableDesktopRuntime();
    invokeMock.mockResolvedValueOnce(engineConfig(18731, "write-token", 9));
    const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError("connection reset"));
    vi.stubGlobal("fetch", fetchMock);

    await initEngineConfig();
    await expect(fetchEnginePath("/conversations", {
      method: "POST",
      body: JSON.stringify({ title: "do not replay" }),
      headers: { "Content-Type": "application/json" },
    })).rejects.toThrow("connection reset");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(invokeMock).toHaveBeenCalledTimes(1);
  });

  it("does not refresh or replay a non-idempotent request rejected by a rotated token", async () => {
    enableDesktopRuntime();
    invokeMock.mockResolvedValueOnce(engineConfig(18731, "stale-write-token", 12));
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({
      type: "urn:dbfox:problem:unauthorized-engine-access",
      title: "Unauthorized",
      status: 401,
      detail: "The local engine generation changed while the command was in flight.",
      instance: "/api/v1/conversations",
      code: "UNAUTHORIZED_ENGINE_ACCESS",
      request_id: "request-write-1",
    }), {
      status: 401,
      headers: { "Content-Type": "application/problem+json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    await initEngineConfig();
    const response = await fetchEnginePath("/conversations", {
      method: "POST",
      body: JSON.stringify({ title: "do not replay after token rotation" }),
      headers: { "Content-Type": "application/json" },
    });

    expect(response.status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(invokeMock).toHaveBeenCalledTimes(1);
  });

  it("parses Problem Details as the only formal error contract", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({
        type: "urn:dbfox:problem:conversation-storage-unavailable",
        title: "Service Unavailable",
        status: 503,
        detail: "Conversation storage is unavailable",
        instance: "/api/v1/conversations",
        code: "CONVERSATION_STORAGE_UNAVAILABLE",
        request_id: "request-2",
      }), {
        status: 503,
        headers: { "Content-Type": "application/problem+json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(listConversations()).rejects.toMatchObject({
      message: "Conversation storage is unavailable",
      status: 503,
      code: "CONVERSATION_STORAGE_UNAVAILABLE",
    });
  });

  it.each([
    { detail: "legacy detail" },
    { message: "legacy message" },
    [{ loc: ["body"], msg: "legacy validation" }],
  ])("rejects a legacy error payload: %j", async (payload) => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify(payload), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(listConversations()).rejects.toMatchObject({
      message: "Engine returned an invalid Problem Details response",
      status: 400,
      code: "INVALID_PROBLEM_DETAILS",
    });
  });
});
