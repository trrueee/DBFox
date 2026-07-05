import { beforeEach, describe, expect, it } from "vitest";

import {
  DEFAULT_API_CONFIG,
  buildAgentRunLlmConfig,
  buildConversationLlmPayload,
  buildLlmTestValues,
  buildSchemaSyncOptions,
  getStoredApiConfig,
  normalizeProductLlmConfig,
  saveStoredApiConfig,
} from "../llmConfig";

describe("llmConfig", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("loads the default product config when storage is empty or invalid", () => {
    expect(getStoredApiConfig()).toEqual(DEFAULT_API_CONFIG);

    localStorage.setItem("dbfox-api-config", JSON.stringify({ apiKey: "sk-test" }));

    expect(getStoredApiConfig()).toEqual(DEFAULT_API_CONFIG);
  });

  it("persists and reads the product LLM config from the shared storage key", () => {
    saveStoredApiConfig({
      apiKey: " sk-test ",
      apiBase: " https://example.test/v1 ",
      modelName: " qwen-plus ",
    });

    expect(getStoredApiConfig()).toEqual({
      apiKey: " sk-test ",
      apiBase: " https://example.test/v1 ",
      modelName: " qwen-plus ",
    });
  });

  it("normalizes request config by trimming values and applying product defaults", () => {
    expect(
      normalizeProductLlmConfig({
        apiKey: " sk-test ",
        apiBase: " ",
        modelName: " ",
      }),
    ).toEqual({
      apiKey: "sk-test",
      apiBase: "https://api.openai.com/v1",
      modelName: "gpt-4o-mini",
      hasApiKey: true,
    });
  });

  it("maps the same normalized config into agent and conversation request payloads", () => {
    const config = {
      apiKey: " sk-test ",
      apiBase: " https://dashscope.aliyuncs.com/compatible-mode/v1 ",
      modelName: " qwen-plus ",
    };

    expect(buildAgentRunLlmConfig(config)).toEqual({
      apiKey: "sk-test",
      apiBase: "https://dashscope.aliyuncs.com/compatible-mode/v1",
      model: "qwen-plus",
    });
    expect(buildConversationLlmPayload(config)).toEqual({
      api_key: "sk-test",
      api_base: "https://dashscope.aliyuncs.com/compatible-mode/v1",
      model_name: "qwen-plus",
    });
  });

  it("builds schema sync options only when AI enrichment is requested", () => {
    const config = {
      apiKey: " sk-test ",
      apiBase: "",
      modelName: " qwen-plus ",
    };

    expect(buildSchemaSyncOptions(false, config)).toBeUndefined();
    expect(buildSchemaSyncOptions(true, config)).toEqual({
      ai_enrich: true,
      api_key: "sk-test",
      api_base: "https://api.openai.com/v1",
      model_name: "qwen-plus",
    });
  });

  it("does not send base or model to schema sync without a product API key", () => {
    expect(
      buildSchemaSyncOptions(true, {
        apiKey: " ",
        apiBase: "https://dashscope.aliyuncs.com/compatible-mode/v1",
        modelName: "qwen-plus",
      }),
    ).toEqual({ ai_enrich: true });
  });

  it("builds LLM test values from the same normalized config", () => {
    expect(
      buildLlmTestValues({
        apiKey: " sk-test ",
        apiBase: "",
        modelName: "",
      }),
    ).toEqual({
      apiKey: "sk-test",
      apiBase: "https://api.openai.com/v1",
      modelName: "gpt-4o-mini",
    });
  });
});
