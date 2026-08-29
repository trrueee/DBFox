import { describe, expect, it } from "vitest";
import {
  applyModelPresetSelection,
  detectProviderFromBaseUrl,
  LLM_MODEL_PRESETS,
  LLM_PROVIDERS,
  resolveApiBaseForModel,
} from "../llmProviders";

describe("llmProviders", () => {
  it("maps qwen models to dashscope compatible endpoint", () => {
    expect(resolveApiBaseForModel("qwen3-max")).toBe(
      "https://dashscope.aliyuncs.com/compatible-mode/v1",
    );
  });

  it("maps deepseek models to deepseek endpoint", () => {
    expect(resolveApiBaseForModel("deepseek-chat")).toBe("https://api.deepseek.com/v1");
  });

  it("updates api base when selecting preset model", () => {
    expect(applyModelPresetSelection("gpt-4o", "https://api.deepseek.com/v1")).toEqual({
      modelName: "gpt-4o",
      apiBase: "https://api.openai.com/v1",
    });
  });

  it("covers global and Chinese providers with unique base URLs", () => {
    const ids = LLM_PROVIDERS.map((provider) => provider.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toEqual(expect.arrayContaining([
      "openai", "anthropic", "google", "openrouter",
      "deepseek", "qwen", "moonshot", "zhipu", "doubao", "xiaomi", "siliconflow",
    ]));
    const bases = LLM_PROVIDERS.map((provider) => provider.baseUrl);
    expect(new Set(bases).size).toBe(bases.length);
  });

  it("derives the built-in model presets from the provider catalog", () => {
    const values = LLM_MODEL_PRESETS.map((preset) => preset.value);
    expect(values).toEqual(expect.arrayContaining([
      "deepseek-chat",
      "qwen-plus",
      "anthropic/claude-sonnet-4.6",
      "gemini-2.5-pro",
    ]));
    for (const preset of LLM_MODEL_PRESETS) {
      const provider = LLM_PROVIDERS.find((item) => item.id === preset.provider);
      expect(provider, `unknown provider ${preset.provider}`).toBeTruthy();
      expect(preset.apiBase).toBe(provider!.baseUrl);
    }
  });

  it("detects the provider from a base URL host", () => {
    expect(detectProviderFromBaseUrl("https://api.deepseek.com/v1")?.id).toBe("deepseek");
    expect(detectProviderFromBaseUrl("https://dashscope.aliyuncs.com/compatible-mode/v1")?.id).toBe("qwen");
    expect(detectProviderFromBaseUrl("https://api.xiaomimimo.com/v1")?.id).toBe("xiaomi");
    expect(detectProviderFromBaseUrl("https://example.com/v1")).toBeUndefined();
  });
});
