/*
 * Regenerates src/components/brand/providerPaths.ts from the installed
 * simple-icons package (CC0). Run from desktop/: node scripts/extract-provider-icons.mjs
 */
import { writeFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const si = require("simple-icons");

const WANTED = {
  anthropic: "siAnthropic",
  deepseek: "siDeepseek",
  moonshot: "siMoonshotai",
  qwen: "siQwen",
  alibabacloud: "siAlibabacloud",
  bytedance: "siBytedance",
  minimax: "siMinimax",
  baidu: "siBaidu",
  openrouter: "siOpenrouter",
  ollama: "siOllama",
  google: "siGooglegemini",
  mistral: "siMistralai",
  huggingface: "siHuggingface",
  perplexity: "siPerplexity",
  xiaomi: "siXiaomi",
};

const lines = [
  "/*",
  " * Brand glyph paths for LLM providers, extracted at build time from the",
  " * simple-icons package (CC0; regenerate via scripts/extract-provider-icons.mjs).",
  " * Providers without an available upstream glyph (OpenAI, Zhipu, xAI,",
  " * SiliconFlow, Hunyuan) render as monogram tiles instead — see ProviderIcon.",
  " */",
  "",
  "export const PROVIDER_ICON_PATHS: Readonly<Record<string, string>> = Object.freeze({",
];
let count = 0;
for (const [id, key] of Object.entries(WANTED)) {
  const icon = si[key];
  if (!icon) {
    console.error(`MISSING ${key}`);
    continue;
  }
  lines.push(`  ${id}:`);
  lines.push(`    "${icon.path}",`);
  count += 1;
}
lines.push("});");
lines.push("");

writeFileSync(new URL("../src/components/brand/providerPaths.ts", import.meta.url), lines.join("\n"));
console.log(`wrote ${count} provider glyph paths`);
