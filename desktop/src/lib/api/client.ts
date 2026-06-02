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
    const error = new Error(payload?.detail?.message || payload?.message || "Request failed") as Error & {
      code?: string;
      checks?: unknown[];
    };
    error.code = payload?.detail?.code || payload?.code;
    error.checks = payload?.detail?.checks || payload?.checks || [];
    throw error;
  }

  return payload as T;
}
