import type { ApiConfig, LlmConfigDraft, SchemaSyncOptions } from "./api/types";
import { validateApiConfig } from "./api/types";
import { DEFAULT_LLM_API_BASE } from "./llmPresets";

export const DEFAULT_LLM_MODEL_NAME = "gpt-4o-mini";
export const API_CONFIG_STORAGE_KEY = "dbfox-api-config";

export const DEFAULT_API_CONFIG: ApiConfig = {
  credentialId: "",
  apiBase: DEFAULT_LLM_API_BASE,
  modelName: "",
};

export interface NormalizedProductLlmConfig {
  credentialId: string;
  apiBase: string;
  modelName: string;
  hasCredential: boolean;
}

type LlmStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export interface ConversationLlmPayload {
  llm_credential_id?: string;
  api_base?: string;
  model_name?: string;
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
  return {
    credentialId: clean(config.credentialId),
    apiBase: clean(config.apiBase) || DEFAULT_LLM_API_BASE,
    modelName: clean(config.modelName),
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
  return {
    credentialId,
    apiBase: clean(config?.apiBase) || DEFAULT_LLM_API_BASE,
    modelName: clean(config?.modelName) || DEFAULT_LLM_MODEL_NAME,
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
    model_name: llm.modelName,
  };
}

export function buildSchemaSyncOptions(
  aiEnrich: boolean,
  config: Partial<ApiConfig> | null | undefined = getStoredApiConfig(),
): SchemaSyncOptions | undefined {
  if (!aiEnrich) return undefined;
  const llm = normalizeProductLlmConfig(config);
  if (!llm.hasCredential) return { ai_enrich: true };
  return {
    ai_enrich: true,
    llm_credential_id: llm.credentialId,
    api_base: llm.apiBase,
    model_name: llm.modelName,
  };
}

export function buildLlmTestValues(config: Partial<ApiConfig> | null | undefined): {
  llmCredentialId: string;
  apiBase: string;
  modelName: string;
} {
  const llm = normalizeProductLlmConfig(config);
  return {
    llmCredentialId: llm.credentialId,
    apiBase: llm.apiBase,
    modelName: llm.modelName,
  };
}
