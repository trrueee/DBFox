export * from "./types";
export * from "./agent";
export * from "./datasources";
export * from "./query";
export * from "./diagnostics";
export * from "./github";

import { agentApi } from "./agent";
import { datasourcesApi } from "./datasources";
import { queryApi } from "./query";
import { diagnosticsApi } from "./diagnostics";
import { githubApi } from "./github";

export const api = {
  ...datasourcesApi,
  ...agentApi,
  ...queryApi,
  ...diagnosticsApi,
  ...githubApi,
};
