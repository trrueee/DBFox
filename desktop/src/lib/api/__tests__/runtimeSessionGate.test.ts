import { afterEach, describe, expect, it, vi } from "vitest";

const { configMock } = vi.hoisted(() => ({ configMock: vi.fn() }));

vi.mock("../../desktopHost", () => ({
  isEngineDesktopHost: () => true,
  getDesktopEngineConfig: configMock,
  getDesktopEngineStatus: vi.fn(),
  subscribeDesktopEngineState: vi.fn(),
}));

afterEach(() => {
  configMock.mockReset();
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe("production runtime session gate", () => {
  it("obtains the IPC runtime configuration before the first engine request", async () => {
    configMock.mockResolvedValueOnce({
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

    expect(configMock).toHaveBeenCalledOnce();
    const request = fetchMock.mock.calls[0][0] as Request;
    expect(new URL(request.url).port).toBe("18901");
    expect(request.headers.get("X-Local-Token")).toBe("ipc-runtime-token");
  });
});
