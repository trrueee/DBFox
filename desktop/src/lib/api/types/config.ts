/** Safe LLM preferences that may be persisted in browser storage. */
import type { LlmProviderProtocol } from "./llmProtocol";

export interface ApiConfig {
  credentialId: string;
  apiBase: string;
  modelName: string;
  provider?: LlmProviderProtocol;
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
  const provider = value.provider;
  return typeof value.credentialId === "string"
    && typeof value.apiBase === "string"
    && typeof value.modelName === "string"
    && (provider === undefined
      || provider === "openai-responses"
      || provider === "openai-chat");
}
