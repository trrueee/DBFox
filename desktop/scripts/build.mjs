import { createBuilder } from "vite";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

import { CHART_BUDGET, ENTRY_BUDGET } from "./bundleBudget.mjs";

const chunkSizeWarningLimit = Math.ceil(
  Math.max(ENTRY_BUDGET.maxRawBytes, CHART_BUDGET.maxRawBytes) / 1024,
);

const builder = await createBuilder(
  {
    // Use relative paths so assets load correctly under Tauri's custom
    // protocol.  Without this, absolute /assets/… paths cause a white
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

// Tauri's custom protocol (tauri://localhost) does not send CORS headers.
// Vite/Rolldown adds `crossorigin` on <script type="module"> and <link>
// tags by default, which causes the browser to require CORS headers the
// custom protocol cannot supply → all JS/CSS loads fail → white screen.
const distDir = resolve(import.meta.dirname, "..", "dist");
const htmlPath = resolve(distDir, "index.html");
let html = readFileSync(htmlPath, "utf-8");
html = html.replace(/\s+crossorigin(?:="[^"]*")?/g, "");
writeFileSync(htmlPath, html);
console.log("  ✓ Stripped crossorigin attributes for Tauri compatibility");
