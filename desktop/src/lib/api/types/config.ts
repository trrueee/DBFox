export interface ApiConfig {
  apiKey: string;
  apiBase: string;
  modelName: string;
}

export function validateApiConfig(config: unknown): config is ApiConfig {
  if (!config || typeof config !== "object") return false;
  const c = config as Record<string, unknown>;
  return typeof c.apiKey === "string"
    && typeof c.apiBase === "string"
    && typeof c.modelName === "string";
}
