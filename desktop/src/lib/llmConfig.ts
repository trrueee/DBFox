import type { AgentRunConfig, ApiConfig, SchemaSyncOptions } from "./api/types";
import { validateApiConfig } from "./api/types";
import { DEFAULT_LLM_API_BASE } from "./llmPresets";

export const DEFAULT_LLM_MODEL_NAME = "gpt-4o-mini";
export const API_CONFIG_STORAGE_KEY = "dbfox-api-config";

export const DEFAULT_API_CONFIG: ApiConfig = {
  apiKey: "",
  apiBase: DEFAULT_LLM_API_BASE,
  modelName: "",
};

export interface NormalizedProductLlmConfig {
  apiKey: string;
  apiBase: string;
  modelName: string;
  hasApiKey: boolean;
}

type LlmStorage = Pick<Storage, "getItem" | "setItem">;

export interface ConversationLlmPayload {
  api_key?: string;
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

export function getStoredApiConfig(storage: Pick<Storage, "getItem"> | null = browserStorage()): ApiConfig {
  if (!storage) return { ...DEFAULT_API_CONFIG };
  try {
    const raw = storage.getItem(API_CONFIG_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (validateApiConfig(parsed)) return parsed;
    }
  } catch {
    // Ignore invalid or unavailable browser storage.
  }
  return { ...DEFAULT_API_CONFIG };
}

export function saveStoredApiConfig(
  config: ApiConfig,
  storage: Pick<Storage, "setItem"> | null = browserStorage(),
): void {
  if (!storage) return;
  storage.setItem(API_CONFIG_STORAGE_KEY, JSON.stringify(config));
}

export function normalizeProductLlmConfig(config: Partial<ApiConfig> | null | undefined): NormalizedProductLlmConfig {
  const apiKey = clean(config?.apiKey);
  return {
    apiKey,
    apiBase: clean(config?.apiBase) || DEFAULT_LLM_API_BASE,
    modelName: clean(config?.modelName) || DEFAULT_LLM_MODEL_NAME,
    hasApiKey: Boolean(apiKey),
  };
}

export function buildAgentRunLlmConfig(config: Partial<ApiConfig> | null | undefined): Pick<AgentRunConfig, "apiKey" | "apiBase" | "model"> {
  const llm = normalizeProductLlmConfig(config);
  if (!llm.hasApiKey) return {};
  return {
    apiKey: llm.apiKey,
    apiBase: llm.apiBase,
    model: llm.modelName,
  };
}

export function buildConversationLlmPayload(config: Partial<ApiConfig> | null | undefined): ConversationLlmPayload {
  const llm = normalizeProductLlmConfig(config);
  if (!llm.hasApiKey) return {};
  return {
    api_key: llm.apiKey,
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
  if (!llm.hasApiKey) return { ai_enrich: true };
  return {
    ai_enrich: true,
    api_key: llm.apiKey,
    api_base: llm.apiBase,
    model_name: llm.modelName,
  };
}

export function buildLlmTestValues(config: Partial<ApiConfig> | null | undefined): {
  apiKey: string;
  apiBase: string;
  modelName: string;
} {
  const llm = normalizeProductLlmConfig(config);
  return {
    apiKey: llm.apiKey,
    apiBase: llm.apiBase,
    modelName: llm.modelName,
  };
}
