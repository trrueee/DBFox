export * from "./types";
export * from "./agent";
export * from "./diagnostics";

import { agentApi } from "./agent";
import { diagnosticsApi } from "./diagnostics";

export const api = {
  ...agentApi,
  ...diagnosticsApi,
};
