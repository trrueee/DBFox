import { mkdtemp, rm } from "node:fs/promises";
import { resolve } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { EngineSupervisor } from "../engine";
import { createDevelopmentEngineLauncher, createEngineHealthProbe } from "../nodeEngineHost";

const runtimeRoots: string[] = [];

afterEach(async () => {
  delete process.env.DBFOX_RUNTIME_DIR;
  delete process.env.DBFOX_ELECTRON_ENGINE_COMMAND;
  for (const runtimeRoot of runtimeRoots.splice(0)) {
    await rm(runtimeRoot, { recursive: true, force: true });
  }
});

describe("Electron development engine host", () => {
  it("reports a missing engine command as failed startup instead of crashing Main", async () => {
    process.env.DBFOX_ELECTRON_ENGINE_COMMAND = "dbfox-command-that-does-not-exist";
    const rendererOrigin = "http://127.0.0.1:5173";
    const host = new EngineSupervisor(
      createDevelopmentEngineLauncher(rendererOrigin),
      createEngineHealthProbe(rendererOrigin),
      { startupTimeoutMs: 1_000 },
    );

    await host.start();

    expect(host.status()).toMatchObject({ state: "failed", stage: "failed" });
    expect(host.status().error).toContain("ENOENT");
    expect(() => host.config()).toThrow("unavailable");
  });

  it("rotates generation, disconnects SSE, and restores the durable snapshot from the real Python Engine", async () => {
    const runtimeRoot = await mkdtemp(resolve(process.cwd(), ".electron-engine-smoke-"));
    runtimeRoots.push(runtimeRoot);
    process.env.DBFOX_RUNTIME_DIR = runtimeRoot;
    const rendererOrigin = "http://127.0.0.1:5173";
    const host = new EngineSupervisor(
      createDevelopmentEngineLauncher(rendererOrigin),
      createEngineHealthProbe(rendererOrigin),
    );

    try {
      await host.start();
      const first = host.config();
      const authenticated = await fetch(`http://127.0.0.1:${first.port}/api/v1/health`, {
        headers: { Origin: rendererOrigin, "X-Local-Token": first.token },
      });
      expect(authenticated.status).toBe(200);
      const rejected = await fetch(`http://127.0.0.1:${first.port}/api/v1/health`, {
        headers: { Origin: rendererOrigin, "X-Local-Token": "wrong-token" },
      });
      expect(rejected.status).toBe(401);

      const projectResponse = await fetch(`http://127.0.0.1:${first.port}/api/v1/projects`, {
        method: "POST",
        headers: {
          Origin: rendererOrigin,
          "X-Local-Token": first.token,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ name: "Electron generation recovery" }),
      });
      expect(projectResponse.status).toBe(200);
      const project = await projectResponse.json() as { id: string };
      const conversationResponse = await fetch(`http://127.0.0.1:${first.port}/api/v1/conversations`, {
        method: "POST",
        headers: {
          Origin: rendererOrigin,
          "X-Local-Token": first.token,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          project_id: project.id,
          title: "Durable generation snapshot",
          resource_intents: [],
        }),
      });
      expect(conversationResponse.status).toBe(200);
      const conversation = await conversationResponse.json() as {
        session: { id: string; title: string };
        cursor: number;
      };
      const streamResponse = await fetch(
        `http://127.0.0.1:${first.port}/api/v1/conversations/${conversation.session.id}/stream?after_sequence=0`,
        { headers: { Origin: rendererOrigin, "X-Local-Token": first.token } },
      );
      expect(streamResponse.status).toBe(200);
      const streamReader = streamResponse.body?.getReader();
      expect(streamReader).toBeDefined();

      await host.restart();
      const second = host.config();
      expect(second.generation).toBe(2);
      expect(second.token).not.toBe(first.token);
      const staleToken = await fetch(`http://127.0.0.1:${second.port}/api/v1/health`, {
        headers: { Origin: rendererOrigin, "X-Local-Token": first.token },
      });
      expect(staleToken.status).toBe(401);
      const disconnectResult = await readUntilDisconnected(streamReader as ReadableStreamDefaultReader<Uint8Array>);
      expect(["closed", "errored"]).toContain(disconnectResult);
      const recoveredSnapshot = await fetch(
        `http://127.0.0.1:${second.port}/api/v1/conversations/${conversation.session.id}`,
        { headers: { Origin: rendererOrigin, "X-Local-Token": second.token } },
      );
      expect(recoveredSnapshot.status).toBe(200);
      await expect(recoveredSnapshot.json()).resolves.toMatchObject({
        session: {
          id: conversation.session.id,
          title: "Durable generation snapshot",
        },
        cursor: conversation.cursor,
      });
      if (second.port !== first.port) {
        await expect(fetch(`http://127.0.0.1:${first.port}/api/v1/health`, {
          headers: { Origin: rendererOrigin, "X-Local-Token": first.token },
          signal: AbortSignal.timeout(500),
        })).rejects.toThrow();
      }
    } finally {
      await host.stop();
    }
    expect(host.status().state).toBe("stopped");
  }, 45_000);
});

async function readUntilDisconnected(
  reader: ReadableStreamDefaultReader<Uint8Array>,
): Promise<"closed" | "errored"> {
  return Promise.race([
    (async () => {
      try {
        while (!(await reader.read()).done) {
          // A final buffered SSE chunk may arrive while the old Sidecar exits.
        }
        return "closed" as const;
      } catch {
        return "errored" as const;
      }
    })(),
    new Promise<never>((_, reject) => {
      setTimeout(() => reject(new Error("Timed out waiting for the old SSE generation to disconnect")), 5_000);
    }),
  ]);
}
