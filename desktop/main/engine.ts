import { randomBytes } from "node:crypto";
import { createInterface } from "node:readline";
import type { Readable } from "node:stream";

import type { EngineConfig, EngineStartupStatus } from "../shared/desktopContract";

export type { EngineConfig, EngineStartupStatus } from "../shared/desktopContract";

const ENGINE_PROTOCOL_VERSION = 1;
const REQUIRED_ENGINE_CAPABILITIES = ["http", "sse", "problem-details"] as const;
const DEFAULT_STARTUP_TIMEOUT_MS = 20_000;
const DEFAULT_RESTART_LIMIT = 3;
const DEFAULT_RESTART_WINDOW_MS = 60_000;

export interface EngineExit {
  code: number | null;
  signal: NodeJS.Signals | null;
}

export interface EngineChild {
  readonly pid: number;
  readonly stdout: Readable;
  onExit(listener: (exit: EngineExit) => void): () => void;
  stop(): Promise<void>;
}

export interface EngineLauncher {
  launch(token: string): Promise<EngineChild>;
}

export interface EngineHealthProbe {
  waitUntilHealthy(port: number, token: string, signal: AbortSignal): Promise<void>;
}

interface EngineReadyPayload {
  port: number;
  protocolVersion: number;
  serverInfo: {
    name: string;
    version: string;
  };
  capabilities: string[];
}

interface EngineFatalPayload {
  stage: string;
  code: string;
  fingerprint: string;
}

class EngineFatalError extends Error {
  readonly fatal: EngineFatalPayload;

  constructor(fatal: EngineFatalPayload) {
    super("Python engine reported a safe startup failure");
    this.name = "EngineFatalError";
    this.fatal = fatal;
  }
}

interface EngineSupervisorOptions {
  startupTimeoutMs?: number;
  restartLimit?: number;
  restartWindowMs?: number;
  restartBackoffMs?: (restartCount: number) => number;
  tokenFactory?: () => string;
  now?: () => number;
}

type StatusListener = (status: EngineStartupStatus) => void;

export class EngineSupervisor {
  readonly #launcher: EngineLauncher;
  readonly #healthProbe: EngineHealthProbe;
  readonly #startupTimeoutMs: number;
  readonly #restartLimit: number;
  readonly #restartWindowMs: number;
  readonly #restartBackoffMs: (restartCount: number) => number;
  readonly #tokenFactory: () => string;
  readonly #now: () => number;
  readonly #listeners = new Set<StatusListener>();
  readonly #restartHistory: number[] = [];

  #status: EngineStartupStatus = {
    state: "stopped",
    error: null,
    stage: null,
    generation: 0,
    restartCount: 0,
    failure: null,
  };
  #config: EngineConfig | null = null;
  #child: EngineChild | null = null;
  #removeExitListener: (() => void) | null = null;
  #startupAbort: AbortController | null = null;
  #activeAttempt: Promise<void> | null = null;
  #epoch = 0;
  #stopping = false;

  constructor(
    launcher: EngineLauncher,
    healthProbe: EngineHealthProbe,
    options: EngineSupervisorOptions = {},
  ) {
    this.#launcher = launcher;
    this.#healthProbe = healthProbe;
    this.#startupTimeoutMs = options.startupTimeoutMs ?? DEFAULT_STARTUP_TIMEOUT_MS;
    this.#restartLimit = options.restartLimit ?? DEFAULT_RESTART_LIMIT;
    this.#restartWindowMs = options.restartWindowMs ?? DEFAULT_RESTART_WINDOW_MS;
    this.#restartBackoffMs = options.restartBackoffMs
      ?? ((restartCount) => 500 * (2 ** Math.min(restartCount - 1, 3)));
    this.#tokenFactory = options.tokenFactory ?? (() => randomBytes(32).toString("hex"));
    this.#now = options.now ?? Date.now;
  }

  status(): EngineStartupStatus {
    return { ...this.#status };
  }

  config(): EngineConfig {
    if (this.#status.state !== "ready" || this.#config === null) {
      throw new Error("Python engine configuration is unavailable until the current generation is ready");
    }
    return {
      ...this.#config,
      serverInfo: { ...this.#config.serverInfo },
      capabilities: [...this.#config.capabilities],
    };
  }

  subscribe(listener: StatusListener): () => void {
    this.#listeners.add(listener);
    listener(this.status());
    return () => this.#listeners.delete(listener);
  }

  async start(): Promise<void> {
    if (this.#child !== null || this.#activeAttempt !== null) {
      throw new Error("Python engine supervisor is already running");
    }
    this.#stopping = false;
    await this.#runStartAttempt("starting");
  }

  async restart(): Promise<void> {
    this.#stopping = true;
    this.#epoch += 1;
    this.#startupAbort?.abort();
    this.#startupAbort = null;
    const activeAttempt = this.#activeAttempt;
    const child = this.#detachChild();
    this.#config = null;
    this.#restartHistory.length = 0;
    this.#setStatus({ state: "starting", error: null, stage: "starting", restartCount: 0, failure: null });
    try {
      if (child !== null) await child.stop();
      if (activeAttempt !== null) await activeAttempt;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Python engine termination failed";
      this.#setStatus({ state: "failed", error: message, stage: "shutdown_failed" });
      throw error;
    }
    this.#stopping = false;
    await this.#runStartAttempt("starting");
  }

  async stop(): Promise<void> {
    this.#stopping = true;
    this.#epoch += 1;
    this.#startupAbort?.abort();
    this.#startupAbort = null;
    const activeAttempt = this.#activeAttempt;
    const child = this.#detachChild();
    this.#config = null;
    try {
      if (child !== null) await child.stop();
      if (activeAttempt !== null) await activeAttempt;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Python engine termination failed";
      this.#setStatus({ state: "failed", error: message, stage: "shutdown_failed" });
      throw error;
    }
    this.#setStatus({ state: "stopped", error: null, stage: null, failure: null });
  }

  async #runStartAttempt(state: "starting" | "restarting"): Promise<void> {
    if (this.#activeAttempt !== null) {
      throw new Error("Python engine startup attempt is already running");
    }
    const attempt = this.#startAttempt(state);
    this.#activeAttempt = attempt;
    try {
      await attempt;
    } finally {
      if (this.#activeAttempt === attempt) this.#activeAttempt = null;
    }
  }

  async #startAttempt(state: "starting" | "restarting"): Promise<void> {
    const epoch = ++this.#epoch;
    const abort = new AbortController();
    this.#startupAbort = abort;
    this.#config = null;
    this.#setStatus({ state, error: null, stage: "launching", failure: null });
    const token = this.#tokenFactory();
    let child: EngineChild | null = null;
    try {
      child = await this.#launcher.launch(token);
      if (!this.#isCurrent(epoch, abort)) {
        try {
          await child.stop();
        } catch (error) {
          const message = error instanceof Error ? error.message : "Python engine termination failed";
          this.#setStatus({ state: "failed", error: message, stage: "shutdown_failed" });
          throw error;
        }
        return;
      }
      this.#child = child;
      this.#removeExitListener = child.onExit((exit) => {
        void this.#handleUnexpectedExit(child as EngineChild, exit);
      });
      const ready = await waitForEngineReady(
        child.stdout,
        abort.signal,
        this.#startupTimeoutMs,
        (stage) => {
          if (this.#isCurrent(epoch, abort)) this.#setStatus({ stage });
        },
      );
      validateEngineHandshake(ready);
      this.#setStatus({ stage: "health-check" });
      await this.#healthProbe.waitUntilHealthy(ready.port, token, abort.signal);
      if (!this.#isCurrent(epoch, abort) || child !== this.#child) return;
      const generation = this.#status.generation + 1;
      this.#config = {
        port: ready.port,
        token,
        generation,
        protocolVersion: ready.protocolVersion,
        serverInfo: { ...ready.serverInfo },
        capabilities: [...ready.capabilities],
      };
      this.#startupAbort = null;
      this.#setStatus({ state: "ready", error: null, stage: null, generation, failure: null });
    } catch (error) {
      if (!this.#isCurrent(epoch, abort)) return;
      this.#startupAbort = null;
      if (child !== null && child === this.#child) {
        this.#detachChild();
        try {
          await child.stop();
        } catch (stopError) {
          const message = stopError instanceof Error
            ? stopError.message
            : "Python engine termination failed";
          this.#config = null;
          this.#setStatus({ state: "failed", error: message, stage: "shutdown_failed" });
          throw stopError;
        }
      }
      this.#config = null;
      this.#setStatus({
        state: "failed",
        error: error instanceof EngineFatalError
          ? "Python engine startup failed"
          : error instanceof Error ? error.message : "Python engine startup failed",
        stage: error instanceof EngineFatalError ? error.fatal.stage : "failed",
        failure: error instanceof EngineFatalError
          ? {
            code: error.fatal.code,
            fingerprint: error.fatal.fingerprint,
          }
          : null,
      });
    }
  }

  async #handleUnexpectedExit(child: EngineChild, exit: EngineExit): Promise<void> {
    if (this.#stopping || child !== this.#child) return;
    this.#epoch += 1;
    this.#startupAbort?.abort();
    this.#startupAbort = null;
    this.#detachChild();
    this.#config = null;
    const restartCount = this.#recordRestart();
    const exitMessage = describeExit(exit);
    if (restartCount > this.#restartLimit) {
      this.#setStatus({
        state: "failed",
        error: `Python engine exited more than ${this.#restartLimit} times within ${Math.floor(this.#restartWindowMs / 1_000)} seconds (${exitMessage})`,
        stage: "crash_loop",
        restartCount,
      });
      return;
    }
    const recoveryEpoch = this.#epoch;
    const interruptedAttempt = this.#activeAttempt;
    this.#setStatus({
      state: "restarting",
      error: null,
      stage: "backoff",
      restartCount,
    });
    await delay(this.#restartBackoffMs(restartCount));
    if (this.#stopping || recoveryEpoch !== this.#epoch) return;
    if (interruptedAttempt !== null) await interruptedAttempt;
    if (this.#stopping || recoveryEpoch !== this.#epoch) return;
    await this.#runStartAttempt("restarting");
  }

  #recordRestart(): number {
    const now = this.#now();
    while (this.#restartHistory[0] !== undefined
      && now - this.#restartHistory[0] > this.#restartWindowMs) {
      this.#restartHistory.shift();
    }
    this.#restartHistory.push(now);
    return this.#restartHistory.length;
  }

  #detachChild(): EngineChild | null {
    this.#removeExitListener?.();
    this.#removeExitListener = null;
    const child = this.#child;
    this.#child = null;
    return child;
  }

  #isCurrent(epoch: number, abort: AbortController): boolean {
    return !abort.signal.aborted && epoch === this.#epoch && !this.#stopping;
  }

  #setStatus(update: Partial<EngineStartupStatus>): void {
    this.#status = { ...this.#status, ...update };
    const snapshot = this.status();
    for (const listener of this.#listeners) listener(snapshot);
  }
}

export function validateEngineHandshake(ready: EngineReadyPayload): void {
  if (ready.protocolVersion !== ENGINE_PROTOCOL_VERSION) {
    throw new Error(
      `Incompatible Python engine protocol: expected ${ENGINE_PROTOCOL_VERSION}, received ${ready.protocolVersion}`,
    );
  }
  if (ready.serverInfo.name !== "dbfox-engine" || !ready.serverInfo.version.trim()) {
    throw new Error("Python engine reported an invalid server identity");
  }
  if (!Number.isInteger(ready.port) || ready.port < 1 || ready.port > 65_535) {
    throw new Error("Python engine reported an invalid local port");
  }
  for (const capability of REQUIRED_ENGINE_CAPABILITIES) {
    if (!ready.capabilities.includes(capability)) {
      throw new Error(`Python engine is missing required capability: ${capability}`);
    }
  }
}

function waitForEngineReady(
  stdout: Readable,
  signal: AbortSignal,
  timeoutMs: number,
  onStage: (stage: string) => void,
): Promise<EngineReadyPayload> {
  return new Promise((resolve, reject) => {
    const lines = createInterface({ input: stdout });
    const timeout = setTimeout(
      () => finish(new Error("Timed out waiting for Python engine ready line")),
      timeoutMs,
    );
    const onAbort = () => finish(abortError());
    const onLine = (line: string) => {
      const stage = parsePrefixedJson<{ stage?: unknown }>(line, "DBFOX_ENGINE_STAGE");
      if (typeof stage?.stage === "string" && stage.stage.trim()) onStage(stage.stage);
      const fatal = parsePrefixedJson<EngineFatalPayload>(line, "DBFOX_ENGINE_FATAL");
      if (isEngineFatalPayload(fatal)) {
        finish(new EngineFatalError(fatal));
        return;
      }
      const ready = parsePrefixedJson<EngineReadyPayload>(line, "DBFOX_ENGINE_READY");
      if (ready !== null) finish(null, ready);
    };
    const finish = (error: Error | null, ready?: EngineReadyPayload) => {
      clearTimeout(timeout);
      signal.removeEventListener("abort", onAbort);
      lines.removeListener("line", onLine);
      lines.close();
      if (error !== null) reject(error);
      else if (ready !== undefined) resolve(ready);
    };
    signal.addEventListener("abort", onAbort, { once: true });
    lines.on("line", onLine);
  });
}

function isEngineFatalPayload(value: EngineFatalPayload | null): value is EngineFatalPayload {
  return value !== null
    && typeof value.stage === "string"
    && /^[a-z][a-z0-9_-]{0,63}$/.test(value.stage)
    && typeof value.code === "string"
    && /^[A-Z][A-Z0-9_]{2,95}$/.test(value.code)
    && typeof value.fingerprint === "string"
    && /^[a-f0-9]{24}$/.test(value.fingerprint);
}

function parsePrefixedJson<T>(line: string, prefix: string): T | null {
  if (!line.startsWith(prefix)) return null;
  try {
    return JSON.parse(line.slice(prefix.length).trim()) as T;
  } catch {
    return null;
  }
}

function abortError(): Error {
  const error = new Error("Python engine startup was cancelled");
  error.name = "AbortError";
  return error;
}

function describeExit(exit: EngineExit): string {
  if (exit.code !== null) return `exit code ${exit.code}`;
  if (exit.signal !== null) return `signal ${exit.signal}`;
  return "unknown exit status";
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
