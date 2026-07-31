import type { CreateClientConfig } from "./generated/client.gen";

const defaultEnginePort = import.meta.env.VITE_LOCAL_ENGINE_PORT || "18625";
const defaultEngineToken = import.meta.env.VITE_LOCAL_ENGINE_TOKEN || "";

export const createClientConfig: CreateClientConfig = (config) => ({
  ...config,
  baseUrl: `http://127.0.0.1:${defaultEnginePort}/api/v1`,
  headers: {
    ...config?.headers,
    "X-Local-Token": defaultEngineToken,
  },
});
