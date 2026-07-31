import {
  apiListColumnsApiV1SchemaTablesTableIdColumnsGet,
  apiListTablesApiV1SchemaTablesGet,
} from "./generated/sdk.gen";
import type {
  SchemaColumnResponse,
  SchemaTableResponse,
} from "./generated/types.gen";

export type EngineSchemaTable = SchemaTableResponse;
export type EngineColumn = SchemaColumnResponse;

export const schemaApi = {
  async listTables(datasourceId: string) {
    const { data } = await apiListTablesApiV1SchemaTablesGet({
      query: { datasource_id: datasourceId },
      throwOnError: true,
    });
    return data;
  },

  async listColumns(tableId: string) {
    const { data } = await apiListColumnsApiV1SchemaTablesTableIdColumnsGet({
      path: { table_id: tableId },
      throwOnError: true,
    });
    return data;
  },

  async findTableByName(datasourceId: string, tableName: string) {
    const tables = await schemaApi.listTables(datasourceId);
    return tables.find((item) => item.table_name === tableName) ?? null;
  },
};

export const listTables = schemaApi.listTables;
export const listColumns = schemaApi.listColumns;
export const findTableByName = schemaApi.findTableByName;
