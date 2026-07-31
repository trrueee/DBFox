import { userFacingErrorMessage } from "../presentation";
import { client as generatedApiClient } from "./generated/client.gen";
import type { ClientOptions } from "./generated/types.gen";

export let ENGINE_PORT = import.meta.env.VITE_LOCAL_ENGINE_PORT || "18625";
export let ENGINE_TOKEN = import.meta.env.VITE_LOCAL_ENGINE_TOKEN || "";
export let BASE_URL = `http://127.0.0.1:${ENGINE_PORT}/api/v1`;

export type EngineStartupState = "starting" | "ready" | "failed" | "stopped";

export interface EngineStartupStatus {
  state: EngineStartupState;
  error?: string | null;
  stage?: string | null;
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
  configureGeneratedApiClient();
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

function apiErrorFromPayload(
  payload: unknown,
  status?: number,
): ApiError {
  const record =
    payload && typeof payload === "object"
      ? payload as Record<string, unknown>
      : {};
  const detail = record.detail;
  const detailRecord =
    detail && typeof detail === "object" && !Array.isArray(detail)
      ? detail as Record<string, unknown>
      : undefined;
  const validationDetail = Array.isArray(detail) ? detail[0] : undefined;
  const validationRecord =
    validationDetail && typeof validationDetail === "object"
      ? validationDetail as Record<string, unknown>
      : undefined;
  const message = String(
    detailRecord?.message
      ?? record.message
      ?? validationRecord?.msg
      ?? "Request failed",
  );
  const code = String(
    detailRecord?.code
      ?? record.code
      ?? (validationRecord ? "VALIDATION_ERROR" : "REQUEST_FAILED"),
  );
  const checks = detailRecord?.checks ?? record.checks;
  return new ApiError(
    message,
    status,
    code,
    Array.isArray(checks) ? checks : [],
    detail ?? payload,
  );
}

function configureGeneratedApiClient(): void {
  generatedApiClient.setConfig({
    baseUrl: BASE_URL as ClientOptions["baseUrl"],
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
