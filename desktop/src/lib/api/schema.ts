import { request } from "./client";
import type { ERDiagramData, SchemaColumn, SchemaTable, TableDesignDDLRequest, TableDesignDDLResponse } from "./types";

export const schemaApi = {
  listTables: (datasourceId: string) =>
    request<SchemaTable[]>(`/schema/tables?datasource_id=${datasourceId}`),

  listColumns: (tableId: string) =>
    request<SchemaColumn[]>(`/schema/tables/${tableId}/columns`),

  getERDiagram: (datasourceId: string) =>
    request<ERDiagramData>(`/schema/er-diagram?datasource_id=${datasourceId}`),

  generateCreateTableDDL: (params: TableDesignDDLRequest) =>
    request<TableDesignDDLResponse>("/schema/design/create-table-ddl", {
      method: "POST",
      body: JSON.stringify(params),
    }),
};
