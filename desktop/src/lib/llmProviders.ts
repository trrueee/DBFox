/** LLM provider catalog — OpenAI-compatible endpoints across global and
 * Chinese providers, plus the derived model presets consumed by settings.
 *
 * The catalog is the offline fallback: the live source of truth is each
 * provider's own `GET /models` route, fetched through the engine
 * (`POST /agent/llm/models`) and merged into the model selector at runtime.
 */

export const DEFAULT_LLM_API_BASE = "https://api.openai.com/v1";

export interface LlmProviderMeta {
  id: string;
  label: string;
  baseUrl: string;
  region: "global" | "cn" | "local";
  /** Small offline fallback of stable model ids; dynamic fetch supersedes it. */
  models: string[];
}

export const LLM_PROVIDERS: readonly LlmProviderMeta[] = Object.freeze([
  // ── 海外 ──
  { id: "openai", label: "OpenAI", baseUrl: "https://api.openai.com/v1", region: "global", models: ["gpt-4o", "gpt-4o-mini"] },
  { id: "anthropic", label: "Anthropic", baseUrl: "https://api.anthropic.com/v1", region: "global", models: [] },
  { id: "google", label: "Google Gemini", baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai", region: "global", models: ["gemini-2.5-pro", "gemini-2.5-flash"] },
  { id: "xai", label: "xAI", baseUrl: "https://api.x.ai/v1", region: "global", models: [] },
  { id: "mistral", label: "Mistral AI", baseUrl: "https://api.mistral.ai/v1", region: "global", models: ["mistral-large-latest"] },
  { id: "openrouter", label: "OpenRouter", baseUrl: "https://openrouter.ai/api/v1", region: "global", models: ["anthropic/claude-sonnet-4.6", "anthropic/claude-opus-4.8", "anthropic/claude-haiku-4.5"] },
  { id: "perplexity", label: "Perplexity", baseUrl: "https://api.perplexity.ai", region: "global", models: [] },
  // ── 国内 ──
  { id: "deepseek", label: "DeepSeek", baseUrl: "https://api.deepseek.com/v1", region: "cn", models: ["deepseek-chat", "deepseek-reasoner"] },
  { id: "qwen", label: "通义千问 Qwen", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", region: "cn", models: ["qwen-plus", "qwen-max", "qwen3-coder-plus"] },
  { id: "moonshot", label: "月之暗面 Kimi", baseUrl: "https://api.moonshot.cn/v1", region: "cn", models: ["moonshot-v1-8k", "moonshot-v1-32k"] },
  { id: "zhipu", label: "智谱 GLM", baseUrl: "https://open.bigmodel.cn/api/paas/v4", region: "cn", models: ["glm-4-plus"] },
  { id: "doubao", label: "火山方舟 Doubao", baseUrl: "https://ark.cn-beijing.volces.com/api/v3", region: "cn", models: [] },
  { id: "minimax", label: "MiniMax", baseUrl: "https://api.minimax.chat/v1", region: "cn", models: [] },
  { id: "hunyuan", label: "腾讯混元", baseUrl: "https://api.hunyuan.cloud.tencent.com/v1", region: "cn", models: [] },
  { id: "xiaomi", label: "小米 MiMo", baseUrl: "https://api.xiaomimimo.com/v1", region: "cn", models: [] },
  { id: "siliconflow", label: "硅基流动", baseUrl: "https://api.siliconflow.cn/v1", region: "cn", models: [] },
  { id: "baidu", label: "百度千帆", baseUrl: "https://qianfan.baidubce.com/v2", region: "cn", models: [] },
  { id: "ollama", label: "Ollama 本地", baseUrl: "http://127.0.0.1:11434/v1", region: "local", models: [] },
] as const);

export function findProvider(providerId: string): LlmProviderMeta | undefined {
  return LLM_PROVIDERS.find((provider) => provider.id === providerId);
}

export function detectProviderFromBaseUrl(apiBase: string): LlmProviderMeta | undefined {
  let host = "";
  try {
    host = new URL(apiBase).host.toLowerCase();
  } catch {
    return undefined;
  }
  return LLM_PROVIDERS.find((provider) => {
    try {
      return new URL(provider.baseUrl).host.toLowerCase() === host;
    } catch {
      return false;
    }
  });
}

/* ── Derived model presets (kept for the settings form contract) ── */

export interface LlmModelPreset {
  value: string;
  label: string;
  apiBase: string;
  provider: string;
}

export const LLM_MODEL_PRESETS: LlmModelPreset[] = LLM_PROVIDERS.flatMap((provider) =>
  provider.models.map((model) => ({
    value: model,
    label: model,
    apiBase: provider.baseUrl,
    provider: provider.id,
  })),
);

export function findModelPreset(modelName: string): LlmModelPreset | undefined {
  return LLM_MODEL_PRESETS.find((p) => p.value === modelName);
}

export function resolveApiBaseForModel(modelName: string): string {
  const preset = findModelPreset(modelName);
  if (preset?.apiBase) return preset.apiBase;

  const lower = modelName.toLowerCase();
  if (lower.startsWith("qwen") || lower.startsWith("qwq")) return providerBaseUrl("qwen");
  if (lower.includes("deepseek")) return providerBaseUrl("deepseek");
  if (lower.includes("kimi") || lower.startsWith("moonshot")) return providerBaseUrl("moonshot");
  if (lower.startsWith("glm")) return providerBaseUrl("zhipu");
  if (lower.includes("claude")) return providerBaseUrl("openrouter");
  if (lower.startsWith("gemini")) return providerBaseUrl("google");
  if (lower.startsWith("grok")) return providerBaseUrl("xai");
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

function providerBaseUrl(providerId: string): string {
  return findProvider(providerId)?.baseUrl ?? DEFAULT_LLM_API_BASE;
}
