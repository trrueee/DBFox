export * from "./types";
export * from "./agent";
export * from "./datasources";
export * from "./query";

import { agentApi } from "./agent";
import { datasourcesApi } from "./datasources";
import { queryApi } from "./query";

export const api = {
  ...datasourcesApi,
  ...agentApi,
  ...queryApi,
};
