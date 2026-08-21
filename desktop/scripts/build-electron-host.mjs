import { build } from "vite";

const shared = {
  configFile: false,
  logLevel: "warn",
};

await build({
  ...shared,
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
