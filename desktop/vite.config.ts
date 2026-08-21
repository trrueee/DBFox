import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig(({ command }) => ({
  // `.env.local` exists solely for the explicit browser-development entry.
  // Vite eagerly substitutes exposed variables before dead-code elimination,
  // so release builds must not expose the VITE_ namespace at all.
  envPrefix: command === "serve" ? "VITE_" : "DBFOX_RELEASE_CLIENT_",
  // Relative base keeps assets valid under packaged desktop protocols.
  base: "./",

  plugins: [react()],

  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },

  clearScreen: false,

  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    watch: {
      ignored: ["**/src-tauri/**"],
    },
  },

  build: {
    // The programmatic build also strips crossorigin from packaged custom-
    // protocol assets so the renderer does not depend on HTTP CORS behavior.
    // Note: codeSplitting groups are deliberately NOT set here because
    // manual chunk naming can break ES module resolution under custom
    // protocols, yielding "a is not a function" in production.
  },
}));
