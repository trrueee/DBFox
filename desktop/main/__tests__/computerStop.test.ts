import { describe, expect, it, vi } from "vitest";
import { stopComputerTargets } from "../computerStop";
import type { EngineConfig } from "../../shared/desktopContract";

const config: EngineConfig = { port: 18001, token: "fixture-ephemeral", generation: 3, protocolVersion: 1,
  serverInfo: { name: "fixture", version: "1" }, capabilities: [] };

describe("global computer stop", () => {
  it("uses the current engine's fixed authenticated endpoint without replay", async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 202 }));
    await stopComputerTargets(config, "dbfox-app://localhost", request);
    expect(request).toHaveBeenCalledOnce();
    expect(request).toHaveBeenCalledWith("http://127.0.0.1:18001/api/v1/computer/stop", expect.objectContaining({
      method: "POST", headers: { "X-Local-Token": "fixture-ephemeral", Origin: "dbfox-app://localhost" },
    }));
  });
  it("does not report a stop when the engine rejects it", async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 401 }));
    await expect(stopComputerTargets(config, "dbfox-app://localhost", request)).rejects.toThrow("not acknowledged");
    expect(request).toHaveBeenCalledOnce();
  });
});
