import {
  apiGetTableScopeApiV1SemanticTableScopeGet,
  apiUpdateTableScopeApiV1SemanticTableScopePost,
} from "./generated/sdk.gen";
import type {
  WorkspaceTableScopeResponse,
  WorkspaceTableScopeUpdateRequest,
} from "./generated/types.gen";

export type {
  WorkspaceTableScopeResponse,
  WorkspaceTableScopeUpdateRequest,
};

export const semanticApi = {
  async getTableScope(projectId: string, datasourceId: string) {
    const { data } = await apiGetTableScopeApiV1SemanticTableScopeGet({
      query: {
        project_id: projectId,
        datasource_id: datasourceId,
      },
      throwOnError: true,
    });
    return data;
  },

  async updateTableScope(params: WorkspaceTableScopeUpdateRequest) {
    const { data } = await apiUpdateTableScopeApiV1SemanticTableScopePost({
      body: params,
      throwOnError: true,
    });
    return data;
  },
};
