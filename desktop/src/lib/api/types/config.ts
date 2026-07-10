/** Safe LLM preferences that may be persisted in browser storage. */
export interface ApiConfig {
  credentialId: string;
  apiBase: string;
  modelName: string;
}

/**
 * Transient form state. `apiKey` is intentionally excluded from ApiConfig and
 * must only be posted to the dedicated credential enrollment endpoint.
 */
export interface LlmConfigDraft extends ApiConfig {
  apiKey: string;
}

export function validateApiConfig(config: unknown): config is ApiConfig {
  if (!config || typeof config !== "object") return false;
  const value = config as Record<string, unknown>;
  return typeof value.credentialId === "string"
    && typeof value.apiBase === "string"
    && typeof value.modelName === "string";
}
