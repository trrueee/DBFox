export * from "./types";
export * from "./agent";
export * from "./datasources";
export * from "./query";
export * from "./semantic";

import { agentApi } from "./agent";
import { datasourcesApi } from "./datasources";
import { queryApi } from "./query";
import { semanticApi } from "./semantic";

export const api = {
  ...datasourcesApi,
  ...agentApi,
  ...queryApi,
  ...semanticApi,
};
