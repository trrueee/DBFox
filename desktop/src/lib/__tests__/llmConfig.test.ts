import { beforeEach, describe, expect, it } from "vitest";

import {
  API_CONFIG_STORAGE_KEY,
  DEFAULT_API_CONFIG,
  discardLlmConfigDraft,
  getStoredApiConfig,
  saveStoredApiConfig,
} from "../llmConfig";

describe("llmConfig credential boundary", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("serializes only the opaque credential reference and LLM preferences", () => {
    saveStoredApiConfig({
      credentialId: "cred_llm_api_key_123",
      apiBase: " https://example.test/v1 ",
      modelName: " qwen-plus ",
    });

    const raw = localStorage.getItem(API_CONFIG_STORAGE_KEY);
    expect(raw).not.toContain("apiKey");
    expect(JSON.parse(raw ?? "{}")).toEqual({
      credentialId: "cred_llm_api_key_123",
      apiBase: "https://example.test/v1",
      modelName: "qwen-plus",
    });
  });

  it("deletes a legacy localStorage value containing a plaintext API key", () => {
    localStorage.setItem(API_CONFIG_STORAGE_KEY, JSON.stringify({
      apiKey: "sk-phase1-storage-sentinel",
      apiBase: "https://example.test/v1",
      modelName: "qwen-plus",
    }));

    expect(getStoredApiConfig()).toEqual(DEFAULT_API_CONFIG);
    expect(localStorage.getItem(API_CONFIG_STORAGE_KEY)).toBeNull();
  });

  it("discarding a draft does not change the saved credential preference", () => {
    saveStoredApiConfig({
      credentialId: "cred_llm_api_key_saved",
      apiBase: "https://example.test/v1",
      modelName: "saved-model",
    });

    const saved = getStoredApiConfig();
    const discarded = discardLlmConfigDraft({
      apiKey: "sk-phase1-draft-sentinel",
      apiBase: "https://other.test/v1",
      modelName: "draft-model",
    }, saved);

    expect(discarded).toEqual({
      apiKey: "",
      credentialId: "cred_llm_api_key_saved",
      apiBase: "https://example.test/v1",
      modelName: "saved-model",
    });
    expect(getStoredApiConfig()).toEqual(saved);
  });
});
