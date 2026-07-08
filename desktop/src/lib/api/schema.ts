import { request } from "./client";

export interface EngineSchemaTable {
  id: string;
  table_schema?: string | null;
  table_name: string;
  table_comment: string;
  table_type?: string | null;
  row_count_estimate?: number | null;
  columns_count?: number | null;
  module_tag?: string | null;
  ai_description?: string | null;
  semantic_tags?: string | null;
  business_terms?: string | null;
  ai_confidence?: number | null;
  subject_area?: string | null;
}

export interface EngineColumn {
  id: string;
  column_name: string;
  data_type: string;
  column_type: string;
  is_nullable: boolean;
  column_default: string;
  column_comment: string;
  is_primary_key: boolean;
  is_foreign_key: boolean;
  foreign_table_id?: string | null;
  foreign_column_id?: string | null;
  ai_description?: string | null;
  semantic_tags?: string | null;
  business_terms?: string | null;
  ai_confidence?: number | null;
}

export const schemaApi = {
  listTables: (datasourceId: string) =>
    request<EngineSchemaTable[]>("/schema/tables?datasource_id=" + encodeURIComponent(datasourceId)),

  listColumns: (tableId: string) =>
    request<EngineColumn[]>("/schema/tables/" + encodeURIComponent(tableId) + "/columns"),

  findTableByName: async (datasourceId: string, tableName: string) => {
    const tables = await schemaApi.listTables(datasourceId);
    return tables.find((item) => item.table_name === tableName) ?? null;
  },
};

export const listTables = schemaApi.listTables;
export const listColumns = schemaApi.listColumns;
export const findTableByName = schemaApi.findTableByName;
