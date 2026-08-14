import { useCallback, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { datasourceQueryKeys } from "../../datasource/useDatasourceState";
import {
  schemaApi,
  type EngineColumn,
  type EngineSchemaTable,
} from "../../../lib/api/schema";

const COLUMN_STALE_TIME_MS = 5 * 60 * 1000;

interface UseSqlCompletionCatalogOptions {
  datasourceId: string;
  connectionGeneration: number;
  enabled: boolean;
}

export interface SqlCompletionCatalog {
  tables: EngineSchemaTable[];
  loading: boolean;
  loadColumns: (tableId: string) => Promise<EngineColumn[]>;
}

export function useSqlCompletionCatalog({
  datasourceId,
  connectionGeneration,
  enabled,
}: UseSqlCompletionCatalogOptions): SqlCompletionCatalog {
  const queryClient = useQueryClient();
  const tablesQuery = useQuery({
    queryKey: datasourceQueryKeys.tables(datasourceId, connectionGeneration),
    queryFn: () => schemaApi.listTables(datasourceId),
    enabled: enabled && Boolean(datasourceId),
  });

  const loadColumns = useCallback(
    (tableId: string) =>
      queryClient.fetchQuery({
        queryKey: ["datasources", datasourceId, "tables", tableId, "columns", connectionGeneration],
        queryFn: () => schemaApi.listColumns(tableId),
        staleTime: COLUMN_STALE_TIME_MS,
      }),
    [connectionGeneration, datasourceId, queryClient],
  );

  return useMemo(
    () => ({
      tables: tablesQuery.data ?? [],
      loading: tablesQuery.isPending && enabled,
      loadColumns,
    }),
    [enabled, loadColumns, tablesQuery.data, tablesQuery.isPending],
  );
}
