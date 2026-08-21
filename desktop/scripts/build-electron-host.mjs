import { build } from "vite";

const shared = {
  configFile: false,
  logLevel: "warn",
  publicDir: false,
};

await build({
  ...shared,
  ssr: {
    // The staged Electron application is intentionally dependency-free. Keep
    // updater implementation details inside the trusted Main bundle rather
    // than shipping the renderer's entire production dependency graph.
    noExternal: true,
  },
  build: {
    outDir: "dist-electron/main",
    emptyOutDir: true,
    target: "node22",
    ssr: "main/index.ts",
    rollupOptions: {
      external: ["electron"],
      output: { entryFileNames: "index.js", format: "es" },
    },
  },
});

await build({
  ...shared,
  build: {
    outDir: "dist-electron/preload",
    emptyOutDir: true,
    target: "node22",
    lib: {
      entry: "preload/index.ts",
      formats: ["cjs"],
      fileName: () => "index.cjs",
    },
    rollupOptions: {
      external: ["electron"],
    },
  },
});

console.log("  ✓ Built Electron Main and sandboxed Preload host bundles");
