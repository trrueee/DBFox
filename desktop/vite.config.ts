import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  // Relative base so Tauri's custom protocol (tauri://localhost) resolves
  // assets correctly.  Absolute /assets/… paths cause white screen.
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
    // The programmatic build (scripts/build.mjs) also strips crossorigin
    // from the output HTML because Tauri's custom protocol lacks CORS.
    // Note: codeSplitting groups are deliberately NOT set here because
    // manual chunk naming can break ES module resolution under Tauri's
    // custom protocol, yielding "a is not a function" in production.
  },
});
