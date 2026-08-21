import { createBuilder } from "vite";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

import { CHART_BUDGET, ENTRY_BUDGET } from "./bundleBudget.mjs";

const chunkSizeWarningLimit = Math.ceil(
  Math.max(ENTRY_BUDGET.maxRawBytes, CHART_BUDGET.maxRawBytes) / 1024,
);

const builder = await createBuilder(
  {
    // Use relative paths so assets load correctly under packaged custom
    // protocols. Without this, absolute /assets/… paths cause a white
    // screen in production builds.
    base: "./",
    build: {
      // Keep Vite's generic warning aligned with the explicit raw/gzip
      // budgets enforced by bundleBudget.mjs after every production build.
      chunkSizeWarningLimit,
    },
  },
  true,
);
await builder.buildApp();

// Packaged custom protocols do not share HTTP's CORS behavior. Vite/Rolldown
// adds `crossorigin` by default, so strip it from the desktop bundle.
const distDir = resolve(import.meta.dirname, "..", "dist");
const htmlPath = resolve(distDir, "index.html");
let html = readFileSync(htmlPath, "utf-8");
html = html.replace(/\s+crossorigin(?:="[^"]*")?/g, "");
writeFileSync(htmlPath, html);
console.log("  ✓ Stripped crossorigin attributes for the packaged desktop protocol");
