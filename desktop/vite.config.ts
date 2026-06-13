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
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: "react-vendor",
              test: /node_modules[\/](react|react-dom|scheduler)[\/]/,
              priority: 100,
            },
            {
              name: "charting",
              test: /node_modules[\/](echarts|echarts-for-react|zrender)[\/]/,
              priority: 80,
            },
            {
              name: "vendor",
              test: /node_modules[\/]/,
              maxSize: 350 * 1024,
              priority: 10,
            },
          ],
        },
      },
    },
  },
});
