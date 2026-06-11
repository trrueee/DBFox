import { describe, expect, it } from "vitest";
import { applyModelPresetSelection, resolveApiBaseForModel } from "../llmPresets";

describe("llmPresets", () => {
  it("maps qwen models to dashscope compatible endpoint", () => {
    expect(resolveApiBaseForModel("qwen3-max")).toBe(
      "https://dashscope.aliyuncs.com/compatible-mode/v1",
    );
  });

  it("maps deepseek models to deepseek endpoint", () => {
    expect(resolveApiBaseForModel("deepseek-v4-pro")).toBe("https://api.deepseek.com/v1");
  });

  it("updates api base when selecting preset model", () => {
    expect(applyModelPresetSelection("gpt-4o", "https://api.deepseek.com/v1")).toEqual({
      modelName: "gpt-4o",
      apiBase: "https://api.openai.com/v1",
    });
  });
});
