import { execFile } from "node:child_process";
import { spawn, type ChildProcessByStdio } from "node:child_process";
import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { readFile, stat } from "node:fs/promises";
import { basename, dirname, join, resolve } from "node:path";
import type { Readable } from "node:stream";
import { promisify } from "node:util";

import type { EngineChild, EngineExit, EngineHealthProbe, EngineLauncher } from "./engine";

const execFileAsync = promisify(execFile);
const MAX_HEALTH_RESPONSE_BYTES = 64 * 1024;
const MAX_SIDECAR_MANIFEST_BYTES = 1024 * 1024;

class NodeEngineChild implements EngineChild {
  readonly #child: ChildProcessByStdio<null, Readable, Readable>;

  constructor(child: ChildProcessByStdio<null, Readable, Readable>) {
    this.#child = child;
  }

  get pid(): number {
    if (this.#child.pid === undefined) throw new Error("Python engine process has no pid");
    return this.#child.pid;
  }

  get stdout() {
    return this.#child.stdout;
  }

  onExit(listener: (exit: EngineExit) => void): () => void {
    const handler = (code: number | null, signal: NodeJS.Signals | null) => listener({ code, signal });
    this.#child.once("exit", handler);
    return () => this.#child.off("exit", handler);
  }

  async stop(): Promise<void> {
    if (this.#child.exitCode !== null || this.#child.signalCode !== null) return;
    const exited = new Promise<void>((resolveExit) => this.#child.once("exit", () => resolveExit()));
    let terminationRequested = false;
    if (process.platform === "win32") {
      try {
        await execFileAsync("taskkill", ["/PID", String(this.pid), "/T", "/F"], {
          windowsHide: true,
        });
        terminationRequested = true;
      } catch {
        // Fall through to the direct child kill when taskkill is unavailable.
      }
    } else {
      try {
        process.kill(-this.pid, "SIGTERM");
        terminationRequested = true;
      } catch {
        // Fall through to the direct child kill when the process group is already gone.
      }
    }
    if (!terminationRequested) this.#child.kill("SIGTERM");
    if (await settlesWithin(exited, 2_000)) return;
    if (process.platform !== "win32") {
      try {
        process.kill(-this.pid, "SIGKILL");
      } catch {
        this.#child.kill("SIGKILL");
      }
    } else {
      this.#child.kill("SIGKILL");
    }
    if (!await settlesWithin(exited, 2_000)) {
      throw new Error(`Python engine process tree ${this.pid} did not terminate`);
    }
  }
}

export function createDevelopmentEngineLauncher(
  rendererOrigin: string,
  onStderr: (byteCount: number) => void = () => undefined,
): EngineLauncher {
  const repositoryRoot = resolve(process.cwd(), "..");
  return {
    async launch(token: string): Promise<EngineChild> {
      return spawnEngine(
        process.env.DBFOX_ELECTRON_ENGINE_COMMAND ?? "python",
        ["-m", "engine.main", "--no-reload"],
        repositoryRoot,
        {
          ...process.env,
          PYTHONPATH: repositoryRoot,
          DBFOX_ENGINE_PORT: "0",
          DBFOX_ENGINE_TOKEN: token,
          DBFOX_DEV_CORS_ORIGINS: rendererOrigin,
        },
        onStderr,
      );
    },
  };
}

export function createPackagedEngineLauncher(
  rendererOrigin: string,
  resourcesPath: string,
  onStderr: (byteCount: number) => void = () => undefined,
): EngineLauncher {
  const sidecarDirectory = join(resourcesPath, "sidecar");
  const executable = join(sidecarDirectory, process.platform === "win32" ? "dbfox-engine.exe" : "dbfox-engine");
  const manifest = join(sidecarDirectory, "dbfox-engine-runtime-manifest.json");
  return {
    async launch(token: string): Promise<EngineChild> {
      await verifyPackagedSidecar(executable, manifest);
      return spawnEngine(executable, [], dirname(executable), {
        ...process.env,
        DBFOX_ENGINE_PORT: "0",
        DBFOX_ENGINE_TOKEN: token,
        DBFOX_DEV_CORS_ORIGINS: rendererOrigin,
      }, onStderr);
    },
  };
}

export async function verifyPackagedSidecar(executable: string, manifestPath: string): Promise<void> {
  const metadata = await stat(manifestPath);
  if (!metadata.isFile() || metadata.size > MAX_SIDECAR_MANIFEST_BYTES) {
    throw new Error("Packaged Sidecar manifest is missing or exceeds its size limit");
  }
  let value: unknown;
  try {
    value = JSON.parse(await readFile(manifestPath, "utf8"));
  } catch (error) {
    throw new Error("Packaged Sidecar manifest is invalid", { cause: error });
  }
  if (value === null || typeof value !== "object") throw new Error("Packaged Sidecar manifest is invalid");
  const manifest = value as Record<string, unknown>;
  if (manifest.schema_version !== 3 || manifest.sidecar_filename !== basename(executable)
    || typeof manifest.target_triplet !== "string" || manifest.target_triplet.length > 128
    || typeof manifest.sidecar_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(manifest.sidecar_sha256)) {
    throw new Error("Packaged Sidecar manifest does not match the Electron resource contract");
  }
  const executableMetadata = await stat(executable);
  if (!executableMetadata.isFile()) throw new Error("Packaged Sidecar executable is unavailable");
  const actual = await sha256(executable);
  if (actual !== manifest.sidecar_sha256) throw new Error("Packaged Sidecar integrity verification failed");
}

async function spawnEngine(
  command: string,
  args: readonly string[],
  cwd: string,
  env: NodeJS.ProcessEnv,
  onStderr: (byteCount: number) => void,
): Promise<EngineChild> {
  const child = spawn(command, args, {
    cwd,
    env,
    stdio: ["ignore", "pipe", "pipe"],
    detached: process.platform !== "win32",
    windowsHide: true,
  });
  child.stderr.on("data", (chunk: Buffer) => onStderr(chunk.byteLength));
  await new Promise<void>((resolveSpawn, reject) => {
    const onSpawn = () => {
      child.removeListener("error", onError);
      resolveSpawn();
    };
    const onError = (error: Error) => {
      child.removeListener("spawn", onSpawn);
      reject(error);
    };
    child.once("spawn", onSpawn);
    child.once("error", onError);
  });
  return new NodeEngineChild(child);
}

function sha256(path: string): Promise<string> {
  return new Promise((resolveDigest, reject) => {
    const digest = createHash("sha256");
    const stream = createReadStream(path);
    stream.on("data", (chunk) => digest.update(chunk));
    stream.once("error", reject);
    stream.once("end", () => resolveDigest(digest.digest("hex")));
  });
}

export function createEngineHealthProbe(rendererOrigin: string): EngineHealthProbe {
  return {
    async waitUntilHealthy(port: number, token: string, signal: AbortSignal): Promise<void> {
      const deadline = Date.now() + 20_000;
      let lastError = "health endpoint was not reachable";
      while (Date.now() < deadline) {
        if (signal.aborted) throw abortError();
        try {
          const response = await fetch(`http://127.0.0.1:${port}/api/v1/health`, {
            method: "GET",
            headers: {
              Origin: rendererOrigin,
              "X-Local-Token": token,
            },
            signal: AbortSignal.any([signal, AbortSignal.timeout(500)]),
          });
          const bytes = await readBoundedBody(response, MAX_HEALTH_RESPONSE_BYTES);
          const payload = JSON.parse(new TextDecoder().decode(bytes)) as { status?: unknown };
          if (response.ok && payload.status === "healthy") return;
          lastError = `health endpoint returned HTTP ${response.status}`;
        } catch (error) {
          if (signal.aborted) throw abortError();
          lastError = error instanceof Error ? error.message : lastError;
        }
        await delay(200, signal);
      }
      throw new Error(`Timed out waiting for Python engine health endpoint: ${lastError}`);
    },
  };
}

function delay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolveDelay, reject) => {
    const onAbort = () => {
      clearTimeout(timeout);
      signal.removeEventListener("abort", onAbort);
      reject(abortError());
    };
    const timeout = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolveDelay();
    }, ms);
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

export async function readBoundedBody(response: Response, maxBytes: number): Promise<Uint8Array> {
  if (response.body === null) return new Uint8Array();
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maxBytes) throw new Error("health response exceeded the maximum allowed size");
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const body = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body;
}

function abortError(): Error {
  const error = new Error("Python engine startup was cancelled");
  error.name = "AbortError";
  return error;
}

async function settlesWithin(task: Promise<void>, timeoutMs: number): Promise<boolean> {
  let timeout: ReturnType<typeof setTimeout> | undefined;
  const result = await Promise.race([
    task.then(() => true),
    new Promise<boolean>((resolveTimeout) => {
      timeout = setTimeout(() => resolveTimeout(false), timeoutMs);
    }),
  ]);
  if (timeout !== undefined) clearTimeout(timeout);
  return result;
}
