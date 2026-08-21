import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["main/**/__tests__/**/*.test.ts"],
    environment: "node",
    maxWorkers: 1,
    testTimeout: 30_000,
  },
});
