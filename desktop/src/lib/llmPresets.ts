/** LLM provider presets — model id maps to OpenAI-compatible API base URL. */

export const DEFAULT_LLM_API_BASE = "https://api.openai.com/v1";

export interface LlmModelPreset {
  value: string;
  label: string;
  apiBase: string;
  provider?: string;
}

export const LLM_MODEL_PRESETS: LlmModelPreset[] = [
  { value: "", label: "自动检测", apiBase: DEFAULT_LLM_API_BASE, provider: "auto" },
  { value: "gpt-4o", label: "GPT-4o", apiBase: "https://api.openai.com/v1", provider: "openai" },
  { value: "gpt-4o-mini", label: "GPT-4o Mini", apiBase: "https://api.openai.com/v1", provider: "openai" },
  { value: "claude-sonnet-4-6", label: "Claude Sonnet 4.6", apiBase: "https://openrouter.ai/api/v1", provider: "anthropic" },
  { value: "claude-opus-4-8", label: "Claude Opus 4.8", apiBase: "https://openrouter.ai/api/v1", provider: "anthropic" },
  { value: "claude-haiku-4-5", label: "Claude Haiku 4.5", apiBase: "https://openrouter.ai/api/v1", provider: "anthropic" },
  { value: "deepseek-v4-pro", label: "DeepSeek V4 Pro", apiBase: "https://api.deepseek.com/v1", provider: "deepseek" },
  { value: "qwen3-max", label: "Qwen3 Max", apiBase: "https://dashscope.aliyuncs.com/compatible-mode/v1", provider: "qwen" },
  { value: "qwen3-coder", label: "Qwen3 Coder", apiBase: "https://dashscope.aliyuncs.com/compatible-mode/v1", provider: "qwen" },
  { value: "qwen-plus", label: "Qwen Plus", apiBase: "https://dashscope.aliyuncs.com/compatible-mode/v1", provider: "qwen" },
];

export function findModelPreset(modelName: string): LlmModelPreset | undefined {
  return LLM_MODEL_PRESETS.find((p) => p.value === modelName);
}

export function resolveApiBaseForModel(modelName: string): string {
  const preset = findModelPreset(modelName);
  if (preset?.apiBase) return preset.apiBase;

  const lower = modelName.toLowerCase();
  if (lower.startsWith("qwen")) {
    return "https://dashscope.aliyuncs.com/compatible-mode/v1";
  }
  if (lower.startsWith("deepseek")) {
    return "https://api.deepseek.com/v1";
  }
  if (lower.startsWith("claude")) {
    return "https://openrouter.ai/api/v1";
  }
  return DEFAULT_LLM_API_BASE;
}

export function applyModelPresetSelection(
  modelName: string,
  currentApiBase: string,
): { modelName: string; apiBase: string } {
  if (!modelName) {
    return { modelName: "", apiBase: currentApiBase || DEFAULT_LLM_API_BASE };
  }
  return {
    modelName,
    apiBase: resolveApiBaseForModel(modelName),
  };
}
