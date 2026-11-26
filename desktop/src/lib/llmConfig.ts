import type { ApiConfig, LlmConfigDraft } from "./api/types";
import type { LlmProviderProtocol } from "./api/types/llmProtocol";
import { validateApiConfig } from "./api/types";
import { DEFAULT_LLM_API_BASE } from "./llmProviders";

export const API_CONFIG_STORAGE_KEY = "dbfox-api-config";
export const API_CONFIG_CHANGED_EVENT = "dbfox-api-config-changed";

export const DEFAULT_API_CONFIG: ApiConfig = {
  credentialId: "",
  apiBase: DEFAULT_LLM_API_BASE,
  modelName: "",
  provider: "openai-responses",
};

export interface NormalizedProductLlmConfig {
  credentialId: string;
  apiBase: string;
  modelName: string;
  provider: LlmProviderProtocol;
  hasCredential: boolean;
}

type LlmStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export interface ConversationLlmPayload {
  llm_credential_id?: string;
  api_base?: string;
  model_name?: string;
  provider?: LlmProviderProtocol;
}

function clean(value: string | null | undefined): string {
  return String(value || "").trim();
}

function browserStorage(): LlmStorage | null {
  try {
    if (typeof localStorage === "undefined") return null;
    return localStorage;
  } catch {
    return null;
  }
}

function normalizedStoredConfig(config: ApiConfig): ApiConfig {
  const apiBase = clean(config.apiBase) || DEFAULT_LLM_API_BASE;
  return {
    credentialId: clean(config.credentialId),
    apiBase,
    modelName: clean(config.modelName),
    provider: config.provider ?? "openai-responses",
  };
}

export function getStoredApiConfig(storage: LlmStorage | null = browserStorage()): ApiConfig {
  if (!storage) return { ...DEFAULT_API_CONFIG };
  try {
    const raw = storage.getItem(API_CONFIG_STORAGE_KEY);
    if (!raw) return { ...DEFAULT_API_CONFIG };
    const parsed: unknown = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && "apiKey" in parsed) {
      storage.removeItem(API_CONFIG_STORAGE_KEY);
      return { ...DEFAULT_API_CONFIG };
    }
    if (validateApiConfig(parsed)) return normalizedStoredConfig(parsed);
  } catch {
    // Invalid storage never becomes a credential source.
  }
  return { ...DEFAULT_API_CONFIG };
}

export function saveStoredApiConfig(
  config: ApiConfig,
  storage: LlmStorage | null = browserStorage(),
): void {
  if (!storage) return;
  storage.setItem(API_CONFIG_STORAGE_KEY, JSON.stringify(normalizedStoredConfig(config)));
  if (typeof window !== "undefined" && storage === browserStorage()) {
    window.dispatchEvent(new Event(API_CONFIG_CHANGED_EVENT));
  }
}

export function createLlmConfigDraft(config: ApiConfig): LlmConfigDraft {
  return { ...normalizedStoredConfig(config), apiKey: "" };
}

export function discardLlmConfigDraft(_draft: LlmConfigDraft, saved: ApiConfig): LlmConfigDraft {
  return createLlmConfigDraft(saved);
}

export function normalizeProductLlmConfig(
  config: Partial<ApiConfig> | null | undefined,
): NormalizedProductLlmConfig {
  const credentialId = clean(config?.credentialId);
  const apiBase = clean(config?.apiBase) || DEFAULT_LLM_API_BASE;
  return {
    credentialId,
    apiBase,
    modelName: clean(config?.modelName),
    provider: config?.provider ?? "openai-responses",
    hasCredential: Boolean(credentialId),
  };
}

export function buildConversationLlmPayload(
  config: Partial<ApiConfig> | null | undefined,
): ConversationLlmPayload {
  const llm = normalizeProductLlmConfig(config);
  if (!llm.hasCredential) return {};
  return {
    llm_credential_id: llm.credentialId,
    api_base: llm.apiBase,
    model_name: llm.modelName || undefined,
    provider: llm.provider,
  };
}

export function buildLlmTestValues(config: Partial<ApiConfig> | null | undefined): {
  llmCredentialId: string;
  apiBase: string;
  modelName: string;
  provider: LlmProviderProtocol;
} {
  const llm = normalizeProductLlmConfig(config);
  return {
    llmCredentialId: llm.credentialId,
    apiBase: llm.apiBase,
    modelName: llm.modelName,
    provider: llm.provider,
  };
}
