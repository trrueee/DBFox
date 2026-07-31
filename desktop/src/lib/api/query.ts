import {
  apiCancelSqlApiV1QueryCancelPost,
  apiValidateSqlApiV1QueryValidatePost,
} from "./generated/sdk.gen";

export const queryApi = {
  async validateSql(
    sql: string,
    options?: { datasourceId?: string; signal?: AbortSignal },
  ) {
    const { data } = await apiValidateSqlApiV1QueryValidatePost({
      body: { sql, datasource_id: options?.datasourceId },
      signal: options?.signal,
      throwOnError: true,
    });
    return data;
  },

  async cancelQuery(executionId: string) {
    const { data } = await apiCancelSqlApiV1QueryCancelPost({
      body: { execution_id: executionId },
      throwOnError: true,
    });
    return data;
  },
};
