import { describe, expect, it } from "vitest";
import {
  applyModelPresetSelection,
  LLM_MODEL_PRESETS,
  resolveApiBaseForModel,
} from "../llmPresets";

describe("llmPresets", () => {
  it("maps qwen models to dashscope compatible endpoint", () => {
    expect(resolveApiBaseForModel("qwen3-max")).toBe(
      "https://dashscope.aliyuncs.com/compatible-mode/v1",
    );
  });

  it("maps deepseek models to deepseek endpoint", () => {
    expect(resolveApiBaseForModel("deepseek-v4-flash")).toBe("https://api.deepseek.com/v1");
  });

  it("updates api base when selecting preset model", () => {
    expect(applyModelPresetSelection("gpt-4o", "https://api.deepseek.com/v1")).toEqual({
      modelName: "gpt-4o",
      apiBase: "https://api.openai.com/v1",
    });
  });

  it("uses provider-supported model identifiers in production presets", () => {
    expect(LLM_MODEL_PRESETS.map((preset) => preset.value)).toEqual(expect.arrayContaining([
      "anthropic/claude-sonnet-4.6",
      "anthropic/claude-opus-4.8",
      "anthropic/claude-haiku-4.5",
      "deepseek-v4-flash",
      "qwen3-coder-plus",
    ]));
    expect(LLM_MODEL_PRESETS.map((preset) => preset.value)).not.toEqual(expect.arrayContaining([
      "claude-sonnet-4-6",
      "deepseek-v4-pro",
      "qwen3-coder",
    ]));
  });
});
