const DEFAULT_ENGINE_PORT = "18625";

export class EngineClientError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "EngineClientError";
    this.status = status;
    this.code = code;
  }
}

function getEngineBaseUrl() {
  const port = import.meta.env.VITE_LOCAL_ENGINE_PORT || DEFAULT_ENGINE_PORT;
  return `http://127.0.0.1:${port}/api/v1`;
}

function getEngineToken() {
  return import.meta.env.VITE_LOCAL_ENGINE_TOKEN || "";
}

export async function engineRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getEngineToken();
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("X-Local-Token", token);

  const response = await fetch(`${getEngineBaseUrl()}${path}`, {
    ...init,
    headers,
  });

  let payload: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text) as unknown;
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    const detail = isRecord(payload) ? payload.detail : undefined;
    const message = extractErrorMessage(detail) || extractErrorMessage(payload) || `Local engine request failed: ${response.status}`;
    const code = isRecord(detail) ? String(detail.code || "") : undefined;
    throw new EngineClientError(message, response.status, code);
  }

  return payload as T;
}

function extractErrorMessage(value: unknown) {
  if (typeof value === "string") return value;
  if (isRecord(value) && typeof value.message === "string") return value.message;
  return "";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
