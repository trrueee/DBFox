import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const panelSource = join(process.cwd(), "src/components/LlmConfigPanel.tsx");
const panelCss = join(process.cwd(), "src/components/LlmConfigPanel.css");

const requiredSelectors = [
  ".hifi-settings-secret-field",
  ".hifi-settings-input--secret",
  ".hifi-settings-input--mono",
  ".hifi-settings-input--custom-model",
  ".hifi-settings-status-badge",
  ".hifi-settings-status-value",
  ".hifi-settings-submit-btn",
  ".hifi-settings-validation",
];

describe("LlmConfigPanel form foundation", () => {
  it("uses react-hook-form and zod while keeping visual classes local", () => {
    const source = readFileSync(panelSource, "utf8");
    const css = readFileSync(panelCss, "utf8");

    expect(source).toContain('from "react-hook-form"');
    expect(source).toContain('from "@hookform/resolvers/zod"');
    expect(source).toContain('from "zod"');
    expect(source).toContain("useForm<ApiConfig>");
    expect(source).toContain("zodResolver");
    expect(source).toContain("llmConfigSchema");
    expect(source).toContain('import "./LlmConfigPanel.css"');
    expect(source).not.toMatch(/\b(pr-\d|mt-\d|gap-\d(?:\.\d)?|font-mono|truncate|max-w-\[|text-\[)/);
    for (const selector of requiredSelectors) {
      expect(css).toContain(selector);
    }
  });
});
