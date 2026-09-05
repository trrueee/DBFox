import { spawn } from "node:child_process";
import { once } from "node:events";

import { describe, expect, it } from "vitest";

import { EngineSupervisor } from "../engine";

describe("Engine stdout after the startup handshake", () => {
  it("keeps a real child pipe drained after ready without publishing its contents", async () => {
    let writeCompleted = false;
    const child = spawn(process.execPath, ["-e", `
      process.stdout.write('DBFOX_ENGINE_READY '+JSON.stringify({port:18625,protocolVersion:1,
        serverInfo:{name:'dbfox-engine',version:'pipe-test'},capabilities:['http','sse','problem-details']})+'\\n');
      setTimeout(()=>process.stdout.write(Buffer.alloc(4*1024*1024,120),
        ()=>process.stderr.write('WRITE_COMPLETED')),100);
      setInterval(()=>{},1000);
    `], { stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
    child.stderr.on("data", (value: Buffer) => {
      if (value.toString().includes("WRITE_COMPLETED")) writeCompleted = true;
    });
    const host = new EngineSupervisor({
      async launch() {
        return {
          pid: child.pid as number,
          stdout: child.stdout,
          onExit(listener) {
            const handler = (code: number | null, signal: NodeJS.Signals | null) => listener({ code, signal });
            child.on("exit", handler);
            return () => child.off("exit", handler);
          },
          async stop() {
            const closed = once(child, "close");
            child.kill();
            await closed;
          },
        };
      },
    }, { async waitUntilHealthy() {} }, { restartLimit: 0 });
    try {
      await host.start();
      expect(host.status().state).toBe("ready");
      await expect.poll(() => writeCompleted, { timeout: 2_000 }).toBe(true);
      expect(child.stdout.readableLength).toBe(0);
    } finally {
      await host.stop();
    }
  }, 5_000);
});
