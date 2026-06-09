export * from "./types";
export * from "./agent";
export * from "./backup";
export * from "./datasources";
export * from "./projects";
export * from "./query";
export * from "./schema";

export * from "./tableDesign";
export * from "./semantic";

import { agentApi } from "./agent";
import { backupApi } from "./backup";
import { datasourcesApi } from "./datasources";
import { projectsApi } from "./projects";
import { queryApi } from "./query";
import { schemaApi } from "./schema";

import { tableDesignApi } from "./tableDesign";
import { semanticApi } from "./semantic";

export const api = {
  ...projectsApi,
  ...datasourcesApi,
  ...backupApi,
  ...schemaApi,
  ...queryApi,

  ...agentApi,
  ...tableDesignApi,
  ...semanticApi,
};
