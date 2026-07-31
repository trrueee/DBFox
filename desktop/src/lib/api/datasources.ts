import {
  apiCheckDatasourceHealthApiV1DatasourcesIdHealthPost,
  apiCreateDatasourceApiV1DatasourcesPost,
  apiDeleteDatasourceApiV1DatasourcesIdDelete,
  apiListDatasourcesApiV1DatasourcesGet,
  apiReleaseDatasourceApiV1DatasourcesIdReleasePost,
  apiSyncSchemaApiV1DatasourcesIdSyncPost,
  apiTestConnectionApiV1DatasourcesTestPost,
  apiUpdateDatasourceApiV1DatasourcesIdPut,
} from "./generated/sdk.gen";
import type {
  DataSourceCreateParams,
  DataSourceTestParams,
  DataSourceUpdateParams,
  DeleteConfirm,
  SchemaSyncOptions,
} from "./types";

export const datasourcesApi = {
  async testConnection(params: DataSourceTestParams) {
    const { data } = await apiTestConnectionApiV1DatasourcesTestPost({
      body: params,
      throwOnError: true,
    });
    return data;
  },

  async createDatasource(params: DataSourceCreateParams) {
    const { data } = await apiCreateDatasourceApiV1DatasourcesPost({
      body: params,
      throwOnError: true,
    });
    return data;
  },

  async listDatasources(projectId?: string) {
    const { data } = await apiListDatasourcesApiV1DatasourcesGet({
      query: { project_id: projectId },
      throwOnError: true,
    });
    return data;
  },

  async checkDatasourceHealth(id: string) {
    const { data } = await apiCheckDatasourceHealthApiV1DatasourcesIdHealthPost({
      path: { id },
      throwOnError: true,
    });
    return data;
  },

  async deleteDatasource(id: string, confirm?: DeleteConfirm) {
    const { data } = await apiDeleteDatasourceApiV1DatasourcesIdDelete({
      path: { id },
      body: confirm,
      throwOnError: true,
    });
    return data;
  },

  async updateDatasource(id: string, params: DataSourceUpdateParams) {
    const { data } = await apiUpdateDatasourceApiV1DatasourcesIdPut({
      path: { id },
      body: params,
      throwOnError: true,
    });
    return data;
  },

  async syncSchema(id: string, options?: SchemaSyncOptions) {
    const { data } = await apiSyncSchemaApiV1DatasourcesIdSyncPost({
      path: { id },
      body: options,
      throwOnError: true,
    });
    return data;
  },

  async releaseDatasource(id: string) {
    const { data } = await apiReleaseDatasourceApiV1DatasourcesIdReleasePost({
      path: { id },
      throwOnError: true,
    });
    return data;
  },
};
