export * from "./types";
export * from "./agent";
export * from "./backup";
export * from "./datasources";
export * from "./projects";
export * from "./query";
export * from "./schema";
export * from "./ai";
export * from "./tableDesign";

import { agentApi } from "./agent";
import { backupApi } from "./backup";
import { datasourcesApi } from "./datasources";
import { projectsApi } from "./projects";
import { queryApi } from "./query";
import { schemaApi } from "./schema";
import { aiApi } from "./ai";
import { tableDesignApi } from "./tableDesign";

export const api = {
  ...projectsApi,
  ...datasourcesApi,
  ...backupApi,
  ...schemaApi,
  ...queryApi,
  ...aiApi,
  ...agentApi,
  ...tableDesignApi,
};
