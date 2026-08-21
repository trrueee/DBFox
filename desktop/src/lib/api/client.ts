import { userFacingErrorMessage } from "../presentation";
import {
  getDesktopEngineConfig,
  getDesktopEngineStatus,
  isEngineDesktopHost,
  subscribeDesktopEngineState,
} from "../desktopHost";
import { client as generatedApiClient } from "./generated/client.gen";
import type { ClientOptions } from "./generated/types.gen";
import { zProblemDetails } from "./generated/zod.gen";

const DEVELOPMENT_ENGINE_PORT = import.meta.env.DEV
  ? import.meta.env.VITE_LOCAL_ENGINE_PORT || "18625"
  : "18625";
const DEVELOPMENT_ENGINE_TOKEN = import.meta.env.DEV
  ? import.meta.env.VITE_LOCAL_ENGINE_TOKEN || ""
  : "";

export let ENGINE_PORT = DEVELOPMENT_ENGINE_PORT;
export let ENGINE_TOKEN = DEVELOPMENT_ENGINE_TOKEN;
export let BASE_URL = `http://127.0.0.1:${ENGINE_PORT}/api/v1`;

const ENGINE_PROTOCOL_VERSION = 1;
const REQUIRED_ENGINE_CAPABILITIES = ["http", "sse", "problem-details"] as const;

export type EngineStartupState = "starting" | "restarting" | "ready" | "failed" | "stopped";

export interface EngineStartupStatus {
  state: EngineStartupState;
  error?: string | null;
  stage?: string | null;
  generation?: number;
  restartCount?: number;
}

type EngineServerInfo = {
  name: string;
  version: string;
};

type EngineConfig = {
  port: number;
  token: string;
  generation: number;
  protocolVersion: number;
  serverInfo: EngineServerInfo;
  capabilities: string[];
};

export interface RuntimeSession {
  generation: number;
  port: number;
  baseUrl: string;
  token: string;
  protocolVersion: number;
  serverInfo: Readonly<EngineServerInfo>;
  capabilities: readonly string[];
}

let runtimeSession: RuntimeSession = Object.freeze({
  generation: 0,
  port: Number(ENGINE_PORT),
  baseUrl: BASE_URL,
  token: ENGINE_TOKEN,
  protocolVersion: ENGINE_PROTOCOL_VERSION,
  serverInfo: Object.freeze({ name: "dbfox-engine", version: "development" }),
  capabilities: Object.freeze([...REQUIRED_ENGINE_CAPABILITIES]),
});

export function getRuntimeSession(): RuntimeSession {
  return runtimeSession;
}

export async function subscribeEngineState(
  listener: (status: EngineStartupStatus) => void,
): Promise<() => void> {
  if (!isEngineDesktopHost()) return () => undefined;
  return subscribeDesktopEngineState(listener);
}

function validateEngineConfig(config: EngineConfig): void {
  const capabilities = Array.isArray(config.capabilities) ? config.capabilities : [];
  const valid = Number.isInteger(config.port)
    && config.port >= 1
    && config.port <= 65_535
    && Boolean(config.token?.trim())
    && Number.isInteger(config.generation)
    && config.generation >= 1
    && config.protocolVersion === ENGINE_PROTOCOL_VERSION
    && Boolean(config.serverInfo?.name?.trim())
    && Boolean(config.serverInfo?.version?.trim())
    && REQUIRED_ENGINE_CAPABILITIES.every((capability) => capabilities.includes(capability));
  if (!valid) {
    throw new ApiError("Desktop host returned an incompatible engine configuration", 503, "ENGINE_CONFIG_INVALID");
  }
}

export async function initEngineConfig(): Promise<void> {
  if (!isEngineDesktopHost()) return;
  const config = await getDesktopEngineConfig();
  validateEngineConfig(config);
  if (config.generation < runtimeSession.generation) return;
  ENGINE_PORT = String(config.port);
  ENGINE_TOKEN = config.token.trim();
  BASE_URL = `http://127.0.0.1:${ENGINE_PORT}/api/v1`;
  runtimeSession = Object.freeze({
    generation: config.generation,
    port: config.port,
    baseUrl: BASE_URL,
    token: ENGINE_TOKEN,
    protocolVersion: config.protocolVersion,
    serverInfo: Object.freeze({ ...config.serverInfo }),
    capabilities: Object.freeze([...config.capabilities]),
  });
  configureGeneratedApiClient();
}

type EngineHealthOptions = {
  attempts?: number;
  intervalMs?: number;
  signal?: AbortSignal;
};

type EngineConfigWaitOptions = EngineHealthOptions & {
  onStatus?: (status: EngineStartupStatus) => void;
  afterGeneration?: number;
};

function abortError(): Error {
  const error = new Error("Engine startup wait was cancelled");
  error.name = "AbortError";
  return error;
}

function throwIfAborted(signal?: AbortSignal): void {
  if (signal?.aborted) throw abortError();
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  throwIfAborted(signal);
  if (!signal) return new Promise((resolve) => setTimeout(resolve, ms));

  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      window.clearTimeout(timeout);
      signal.removeEventListener("abort", onAbort);
      reject(abortError());
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

async function getEngineStartupStatus(): Promise<EngineStartupStatus> {
  return getDesktopEngineStatus();
}

/**
 * The Electron Host starts the engine in the background. Poll its explicit
 * lifecycle state instead of probing a guessed port while it is still
 * starting. Browser-only development paths remain a no-op.
 */
export async function waitForEngineConfig(options: EngineConfigWaitOptions = {}): Promise<void> {
  if (!isEngineDesktopHost()) return;

  const attempts = options.attempts;
  const intervalMs = options.intervalMs ?? 250;
  let lastError: unknown;
  let attempt = 0;

  while (attempts === undefined || attempt < attempts) {
    throwIfAborted(options.signal);
    try {
      const status = await getEngineStartupStatus();
      throwIfAborted(options.signal);
      options.onStatus?.(status);
      if (status.state === "ready" && (options.afterGeneration === undefined
        || (status.generation ?? 0) > options.afterGeneration)) {
        await initEngineConfig();
        return;
      }
      if (status.state === "failed" || status.state === "stopped") {
        throw new ApiError(
          status.error || "Local engine is unavailable.",
          503,
          status.state === "failed" ? "ENGINE_STARTUP_FAILED" : "ENGINE_STOPPED",
        );
      }
    } catch (error) {
      if (options.signal?.aborted) throw error;
      lastError = error;
      if (error instanceof ApiError && (error.code === "ENGINE_STARTUP_FAILED" || error.code === "ENGINE_STOPPED")) {
        throw error;
      }
    }
    attempt += 1;
    if (attempts === undefined || attempt < attempts) {
      await delay(intervalMs, options.signal);
    }
  }

  const message = lastError instanceof Error ? lastError.message : "Timed out waiting for the local engine to start";
  throw new ApiError(message, 503, "ENGINE_STARTUP_TIMEOUT");
}

export async function waitEngineHealth(options: EngineHealthOptions = {}): Promise<void> {
  const attempts = options.attempts ?? 20;
  const intervalMs = options.intervalMs ?? 250;
  let lastError: unknown;

  for (let attempt = 0; attempt < attempts; attempt++) {
    throwIfAborted(options.signal);
    try {
      const response = await fetchEnginePath("/health", { method: "GET", signal: options.signal });
      if (response.ok) {
        const text = await response.text();
        const payload = text ? JSON.parse(text) : null;
        if (payload?.status === "healthy") return;
      }
      lastError = new Error(`Engine health check failed with status ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    if (attempt < attempts - 1) {
      await delay(intervalMs, options.signal);
    }
  }

  const message = lastError instanceof Error ? lastError.message : "Engine health check failed";
  throw new ApiError(message, 503, "ENGINE_HEALTH_UNAVAILABLE");
}

export class ApiError extends Error {
  status?: number;
  code?: string;
  checks: unknown[];
  detail?: unknown;

  constructor(message: string, status?: number, code?: string, checks: unknown[] = [], detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.checks = checks;
    this.detail = detail;
  }
}

function apiErrorFromPayload(
  payload: unknown,
  status?: number,
): ApiError {
  const parsed = zProblemDetails.safeParse(payload);
  if (!parsed.success || (status !== undefined && parsed.data.status !== status)) {
    return new ApiError(
      "Engine returned an invalid Problem Details response",
      status,
      "INVALID_PROBLEM_DETAILS",
      [],
      parsed.success ? payload : parsed.error,
    );
  }
  const problem = parsed.data;
  return new ApiError(
    problem.detail,
    problem.status,
    problem.code,
    problem.checks ?? [],
    problem,
  );
}

let hostSnapshotRefresh: Promise<void> | null = null;

function refreshHostSnapshot(): Promise<void> {
  hostSnapshotRefresh ??= initEngineConfig().finally(() => {
    hostSnapshotRefresh = null;
  });
  return hostSnapshotRefresh;
}

function awaitWithoutCancellingSharedTask(task: Promise<void>, signal?: AbortSignal): Promise<void> {
  throwIfAborted(signal);
  if (!signal) return task;
  return new Promise((resolve, reject) => {
    const onAbort = () => reject(abortError());
    signal.addEventListener("abort", onAbort, { once: true });
    task.then(resolve, reject).finally(() => signal.removeEventListener("abort", onAbort));
  });
}

async function refreshEngineConfig(requiredGeneration?: number, signal?: AbortSignal): Promise<void> {
  try {
    await awaitWithoutCancellingSharedTask(refreshHostSnapshot(), signal);
  } catch (error) {
    if (requiredGeneration === undefined || signal?.aborted) throw error;
  }
  throwIfAborted(signal);
  if (requiredGeneration !== undefined && runtimeSession.generation <= requiredGeneration) {
    await waitForEngineConfig({
      afterGeneration: requiredGeneration,
      attempts: 40,
      intervalMs: 250,
      signal,
    });
  }
}

function isReplaySafe(method: string): boolean {
  return method === "GET" || method === "HEAD" || method === "OPTIONS";
}

function rebaseEngineUrl(url: string, session: RuntimeSession): string {
  const parsed = new URL(url);
  if (!parsed.pathname.startsWith("/api/v1")) return url;
  return `${new URL(session.baseUrl).origin}${parsed.pathname}${parsed.search}${parsed.hash}`;
}

async function requestForSession(template: Request, session: RuntimeSession): Promise<Request> {
  const headers = new Headers(template.headers);
  headers.set("X-Local-Token", session.token);
  const hasBody = template.method !== "GET" && template.method !== "HEAD";
  return new Request(rebaseEngineUrl(template.url, session), {
    method: template.method,
    headers,
    body: hasBody ? await template.clone().arrayBuffer() : undefined,
    cache: template.cache,
    credentials: template.credentials,
    integrity: template.integrity,
    keepalive: template.keepalive,
    mode: template.mode,
    redirect: template.redirect,
    referrer: template.referrer,
    referrerPolicy: template.referrerPolicy,
    signal: template.signal,
  });
}

async function engineAwareFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  let request = new Request(input, init);
  if (isEngineDesktopHost() && runtimeSession.generation === 0) {
    await refreshEngineConfig();
    request = await requestForSession(request, runtimeSession);
  }
  const retryTemplate = request.clone();
  const initialGeneration = runtimeSession.generation;
  let response: Response;
  try {
    response = await globalThis.fetch(request);
  } catch (error) {
    if (!isEngineDesktopHost() || !isReplaySafe(request.method) || request.signal.aborted) throw error;
    await refreshEngineConfig(initialGeneration, request.signal);
    return globalThis.fetch(await requestForSession(retryTemplate, runtimeSession));
  }
  if (response.status !== 401 || !isEngineDesktopHost() || !isReplaySafe(request.method)) return response;

  await refreshEngineConfig(undefined, request.signal);
  return globalThis.fetch(await requestForSession(retryTemplate, runtimeSession));
}

export async function fetchEnginePath(path: string, init?: RequestInit): Promise<Response> {
  const session = runtimeSession;
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const headers = new Headers(init?.headers);
  headers.set("X-Local-Token", session.token);
  return engineAwareFetch(`${session.baseUrl}${normalizedPath}`, { ...init, headers });
}

function configureGeneratedApiClient(): void {
  generatedApiClient.setConfig({
    // OpenAPI operation paths already begin with /api/v1. Supplying the API
    // prefix here would produce /api/v1/api/v1/... in the packaged WebView.
    baseUrl: new URL(BASE_URL).origin as ClientOptions["baseUrl"],
    fetch: engineAwareFetch,
    headers: {
      "X-Local-Token": ENGINE_TOKEN,
    },
  });
}

generatedApiClient.interceptors.error.use((error, response) => {
  if (error instanceof ApiError) return error;
  if (error instanceof Error && response === undefined) return error;
  return apiErrorFromPayload(error, response?.status);
});
configureGeneratedApiClient();

export function getUserErrorMessage(error: unknown, fallback = "操作失败，请重试"): string {
  return userFacingErrorMessage(error, fallback);
}
