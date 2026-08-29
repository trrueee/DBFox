import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: [
      "main/**/__tests__/**/*.test.ts",
      "scripts/**/__tests__/**/*.test.mjs",
    ],
    environment: "node",
    maxWorkers: 1,
    testTimeout: 30_000,
  },
});
