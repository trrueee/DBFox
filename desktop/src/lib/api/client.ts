import { userFacingErrorMessage } from "../presentation";

export let ENGINE_PORT = import.meta.env.VITE_LOCAL_ENGINE_PORT || "18625";
export let ENGINE_TOKEN = import.meta.env.VITE_LOCAL_ENGINE_TOKEN || "";
export let BASE_URL = `http://127.0.0.1:${ENGINE_PORT}/api/v1`;

export type EngineStartupState = "starting" | "ready" | "failed" | "stopped";

export interface EngineStartupStatus {
  state: EngineStartupState;
  error?: string | null;
}

type EngineConfig = {
  port: number;
  token: string;
};

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function initEngineConfig(): Promise<void> {
  if (!isTauriRuntime()) return;
  const { invoke } = await import("@tauri-apps/api/core");
  const config = await invoke<EngineConfig>("get_engine_config");
  ENGINE_PORT = String(config.port);
  ENGINE_TOKEN = config.token;
  BASE_URL = `http://127.0.0.1:${ENGINE_PORT}/api/v1`;
  console.log(`[DBFox] Loaded dynamic engine config: port=${ENGINE_PORT}`);
}

type EngineHealthOptions = {
  attempts?: number;
  intervalMs?: number;
  signal?: AbortSignal;
};

type EngineConfigWaitOptions = EngineHealthOptions & {
  onStatus?: (status: EngineStartupStatus) => void;
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
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<EngineStartupStatus>("get_engine_startup_status");
}

/**
 * The Rust host starts the engine in the background.  Poll its explicit
 * lifecycle state instead of probing a guessed port while it is still
 * starting. Browser-only development paths remain a no-op.
 */
export async function waitForEngineConfig(options: EngineConfigWaitOptions = {}): Promise<void> {
  if (!isTauriRuntime()) return;

  const attempts = options.attempts ?? 180;
  const intervalMs = options.intervalMs ?? 250;
  let lastError: unknown;

  for (let attempt = 0; attempt < attempts; attempt++) {
    throwIfAborted(options.signal);
    try {
      const status = await getEngineStartupStatus();
      throwIfAborted(options.signal);
      options.onStatus?.(status);
      if (status.state === "ready") {
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
    if (attempt < attempts - 1) await delay(intervalMs, options.signal);
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
      const response = await fetch(`${BASE_URL}/health`, { method: "GET", signal: options.signal });
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

export function getUserErrorMessage(error: unknown, fallback = "操作失败，请重试"): string {
  return userFacingErrorMessage(error, fallback);
}

type RequestPolicy = {
  retry?: "none" | "local-engine-startup";
  cacheKey?: string;
  cacheTtlMs?: number;
};

// In-memory cache for GET requests with size limit
const _cache = new Map<string, { data: unknown; expiry: number }>();
const _CACHE_MAX_ENTRIES = 100;
// Deduplicate in-flight requests by cache key
const _inflight = new Map<string, Promise<unknown>>();

function _getCacheKey(path: string, options: RequestInit, policy: RequestPolicy): string | null {
  if (options.method && options.method !== "GET") return null;
  return policy.cacheKey || path;
}

function _getCached<T>(key: string): T | undefined {
  const entry = _cache.get(key);
  if (!entry) return undefined;
  if (Date.now() > entry.expiry) {
    _cache.delete(key);
    return undefined;
  }
  return entry.data as T;
}

function _setCache(key: string, data: unknown, ttlMs: number): void {
  // Evict oldest entries if at capacity
  if (_cache.size >= _CACHE_MAX_ENTRIES) {
    const oldestKey = _cache.keys().next().value;
    if (oldestKey !== undefined) _cache.delete(oldestKey);
  }
  _cache.set(key, { data, expiry: Date.now() + ttlMs });
}

export function invalidateApiCache(prefix?: string): void {
  if (!prefix) {
    _cache.clear();
    return;
  }
  for (const key of _cache.keys()) {
    if (key.startsWith(prefix)) _cache.delete(key);
  }
}

async function _fetchWithRetry<T>(
  path: string,
  options: RequestInit,
  retries: number,
): Promise<T> {
  let lastError: Error | undefined;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const response = await fetch(`${BASE_URL}${path}`, {
        ...options,
        headers: {
          "Content-Type": "application/json",
          "X-Local-Token": ENGINE_TOKEN,
          ...(options.headers || {}),
        },
      });

      const text = await response.text();
      const payload = (() => {
        if (!text) return null;
        try { return JSON.parse(text); } catch { return { message: text }; }
      })();
      if (!response.ok) {
        const detail = payload?.detail;
        let message = payload?.message || "Request failed";
        let code = payload?.code as string | undefined;

        if (detail && typeof detail === "object" && !Array.isArray(detail)) {
          message = detail.message || message;
          code = detail.code || code;
        } else if (Array.isArray(detail) && detail.length > 0) {
          const first = detail[0];
          if (first && typeof first === "object" && "msg" in first) {
            message = String((first as { msg?: string }).msg || message);
          }
          code = code || "VALIDATION_ERROR";
        }

        const checks = (detail && typeof detail === "object" && !Array.isArray(detail) ? detail.checks : payload?.checks) || [];
        const error = new ApiError(message, response.status, code, checks, detail || payload);
        // Don't retry client errors (4xx)
        if (response.status >= 400 && response.status < 500) throw error;
        throw error;
      }

      return payload as T;
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
      if (options.signal?.aborted) throw lastError;
      // Don't retry client errors (4xx)
      if (lastError instanceof ApiError && lastError.status && lastError.status >= 400 && lastError.status < 500) {
        break;
      }
      if (attempt < retries) {
        await delay(200 * (attempt + 1), options.signal ?? undefined);
      }
    }
  }
  throw lastError!;
}

export async function request<T>(
  path: string,
  options: RequestInit = {},
  policy: RequestPolicy = {},
): Promise<T> {
  const cacheKey = _getCacheKey(path, options, policy);
  const inflightKey = options.signal ? null : cacheKey;
  const isGet = !options.method || options.method === "GET";

  // Check cache
  if (cacheKey && policy.cacheTtlMs) {
    const cached = _getCached<T>(cacheKey);
    if (cached !== undefined) return cached;
  }

  // Deduplicate in-flight requests
  if (inflightKey && _inflight.has(inflightKey)) {
    return _inflight.get(inflightKey) as Promise<T>;
  }

  const retries = policy.retry === "local-engine-startup" ? 2 : 0;

  const promise = _fetchWithRetry<T>(path, options, retries).then((result) => {
    // Cache successful GET responses
    if (cacheKey && policy.cacheTtlMs && isGet) {
      _setCache(cacheKey, result, policy.cacheTtlMs);
    }
    if (inflightKey) _inflight.delete(inflightKey);
    return result;
  }).catch((err) => {
    if (inflightKey) _inflight.delete(inflightKey);
    throw err;
  });

  if (inflightKey) _inflight.set(inflightKey, promise);
  return promise;
}

export async function requestBlob(path: string, options: RequestInit = {}): Promise<Blob> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Local-Token": ENGINE_TOKEN,
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    const text = await response.text();
    const payload = (() => {
      if (!text) return null;
      try { return JSON.parse(text); } catch { return { message: text }; }
    })();
    const detail = payload?.detail;
    let message = payload?.message || "Request failed";
    let code = payload?.code as string | undefined;

    if (detail && typeof detail === "object" && !Array.isArray(detail)) {
      message = detail.message || message;
      code = detail.code || code;
    }

    const checks = (detail && typeof detail === "object" && !Array.isArray(detail) ? detail.checks : payload?.checks) || [];
    throw new ApiError(message, response.status, code, checks, detail || payload);
  }

  return response.blob();
}
