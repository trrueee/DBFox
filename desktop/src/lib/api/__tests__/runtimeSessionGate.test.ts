import { afterEach, describe, expect, it, vi } from "vitest";

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: invokeMock,
  isTauri: () => true,
}));

afterEach(() => {
  invokeMock.mockReset();
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe("production runtime session gate", () => {
  it("obtains the IPC runtime configuration before the first engine request", async () => {
    invokeMock.mockResolvedValueOnce({
      port: 18901,
      token: "ipc-runtime-token",
      generation: 1,
      protocolVersion: 1,
      serverInfo: { name: "dbfox-engine", version: "1.0.3" },
      capabilities: ["http", "sse", "problem-details"],
    });
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const { fetchEnginePath } = await import("../client");

    await fetchEnginePath("/health");

    expect(invokeMock).toHaveBeenCalledWith("get_engine_config");
    const request = fetchMock.mock.calls[0][0] as Request;
    expect(new URL(request.url).port).toBe("18901");
    expect(request.headers.get("X-Local-Token")).toBe("ipc-runtime-token");
  });
});
