export * from "./types";
export * from "./agent";
export * from "./datasources";
export * from "./query";
export * from "./semantic";
export * from "./diagnostics";

import { agentApi } from "./agent";
import { datasourcesApi } from "./datasources";
import { queryApi } from "./query";
import { semanticApi } from "./semantic";
import { diagnosticsApi } from "./diagnostics";

export const api = {
  ...datasourcesApi,
  ...agentApi,
  ...queryApi,
  ...semanticApi,
  ...diagnosticsApi,
};
