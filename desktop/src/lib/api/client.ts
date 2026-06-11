export const ENGINE_PORT = import.meta.env.VITE_LOCAL_ENGINE_PORT || "18625";
export const ENGINE_TOKEN = import.meta.env.VITE_LOCAL_ENGINE_TOKEN || "";
export const BASE_URL = `http://127.0.0.1:${ENGINE_PORT}/api/v1`;

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Local-Token": ENGINE_TOKEN,
      ...(options.headers || {}),
    },
  });

  const text = await response.text();
  const payload = (() => { if (!text) return null; try { return JSON.parse(text); } catch { return { message: text }; } })();
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

    const error = new Error(message) as Error & {
      code?: string;
      checks?: unknown[];
    };
    error.code = code;
    error.checks = (detail && typeof detail === "object" && !Array.isArray(detail) ? detail.checks : payload?.checks) || [];
    throw error;
  }

  return payload as T;
}
