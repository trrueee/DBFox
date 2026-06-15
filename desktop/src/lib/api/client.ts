export const ENGINE_PORT = import.meta.env.VITE_LOCAL_ENGINE_PORT || "18625";
export const ENGINE_TOKEN = import.meta.env.VITE_LOCAL_ENGINE_TOKEN || "";
export const BASE_URL = `http://127.0.0.1:${ENGINE_PORT}/api/v1`;

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

function _getCacheKey(path: string, options: RequestInit): string | null {
  if (options.method && options.method !== "GET") return null;
  return options.cacheKey || path;
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

        const error = new Error(message) as Error & {
          code?: string;
          checks?: unknown[];
        };
        error.code = code;
        error.checks = (detail && typeof detail === "object" && !Array.isArray(detail) ? detail.checks : payload?.checks) || [];
        // Don't retry client errors (4xx)
        if (response.status >= 400 && response.status < 500) throw error;
        throw error;
      }

      return payload as T;
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
      // Don't retry client errors (4xx)
      if (lastError instanceof Error && "code" in lastError) break;
      if (attempt < retries) {
        await new Promise((r) => setTimeout(r, 200 * (attempt + 1)));
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
  const cacheKey = _getCacheKey(path, options);
  const isGet = !options.method || options.method === "GET";

  // Check cache
  if (cacheKey && policy.cacheTtlMs) {
    const cached = _getCached<T>(cacheKey);
    if (cached !== undefined) return cached;
  }

  // Deduplicate in-flight requests
  if (cacheKey && _inflight.has(cacheKey)) {
    return _inflight.get(cacheKey) as Promise<T>;
  }

  const retries = policy.retry === "local-engine-startup" ? 2 : 0;

  const promise = _fetchWithRetry<T>(path, options, retries).then((result) => {
    // Cache successful GET responses
    if (cacheKey && policy.cacheTtlMs && isGet) {
      _setCache(cacheKey, result, policy.cacheTtlMs);
    }
    _inflight.delete(cacheKey!);
    return result;
  }).catch((err) => {
    _inflight.delete(cacheKey!);
    throw err;
  });

  if (cacheKey) _inflight.set(cacheKey, promise);
  return promise;
}
