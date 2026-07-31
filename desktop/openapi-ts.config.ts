import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "./src/lib/api/generated/openapi.json",
  output: "./src/lib/api/generated",
  plugins: [
    {
      name: "@hey-api/client-fetch",
      runtimeConfigPath: "./src/lib/api/generatedClientConfig.ts",
    },
    "@hey-api/sdk",
    "zod",
  ],
});
