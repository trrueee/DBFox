import { useEffect, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { datasourcesApi } from "../../lib/api/datasources";
import { schemaApi } from "../../lib/api/schema";
import type {
  DataSource,
  DataSourceCreateParams,
  DataSourceUpdateParams,
  DeleteConfirm,
  SchemaSyncOptions,
} from "../../lib/api/types";
import { useDatasourceSelectionStore } from "../../stores/datasourceSelectionStore";

export const datasourceQueryKeys = {
  all: ["datasources"] as const,
  tables: (datasourceId: string, connectionGeneration: number) =>
    ["datasources", datasourceId, "tables", connectionGeneration] as const,
};

const EMPTY_DATASOURCES: DataSource[] = [];

function errorMessage(error: unknown, fallback: string): string {
  if (!error) return "";
  return error instanceof Error ? error.message : fallback;
}

export function useDatasourceState() {
  const queryClient = useQueryClient();
  const activeDatasourceId = useDatasourceSelectionStore((state) => state.activeDatasourceId);
  const setSelectedDatasourceId = useDatasourceSelectionStore((state) => state.setActiveDatasourceId);

  const datasourcesQuery = useQuery({
    queryKey: datasourceQueryKeys.all,
    queryFn: () => datasourcesApi.listDatasources(),
  });
  const datasources = datasourcesQuery.data ?? EMPTY_DATASOURCES;
  const activeDatasource = useMemo(
    () => datasources.find((item) => item.id === activeDatasourceId) ?? null,
    [activeDatasourceId, datasources],
  );

  useEffect(() => {
    if (datasourcesQuery.isPending) return;
    if (activeDatasourceId && datasources.some((item) => item.id === activeDatasourceId)) return;
    setSelectedDatasourceId(datasources[0]?.id ?? "");
  }, [activeDatasourceId, datasources, datasourcesQuery.isPending, setSelectedDatasourceId]);

  const tablesQuery = useQuery({
    queryKey: datasourceQueryKeys.tables(
      activeDatasource?.id ?? "",
      activeDatasource?.connection_generation ?? 0,
    ),
    queryFn: () => schemaApi.listTables(activeDatasource!.id),
    enabled: Boolean(activeDatasource),
  });

  const invalidateDatasourceList = () =>
    queryClient.invalidateQueries({ queryKey: datasourceQueryKeys.all });

  const createMutation = useMutation({
    mutationFn: (params: DataSourceCreateParams) => datasourcesApi.createDatasource(params),
    onSuccess: invalidateDatasourceList,
  });
  const updateMutation = useMutation({
    mutationFn: ({ id, params }: { id: string; params: DataSourceUpdateParams }) =>
      datasourcesApi.updateDatasource(id, params),
    onSuccess: invalidateDatasourceList,
  });
  const deleteMutation = useMutation({
    mutationFn: ({ id, confirm }: { id: string; confirm?: DeleteConfirm }) =>
      datasourcesApi.deleteDatasource(id, confirm),
    onSuccess: async (result, { id }) => {
      if ("requires_confirmation" in result) return;
      queryClient.removeQueries({ queryKey: ["datasources", id] });
      if (useDatasourceSelectionStore.getState().activeDatasourceId === id) {
        setSelectedDatasourceId("");
      }
      await invalidateDatasourceList();
    },
  });
  const syncMutation = useMutation({
    mutationFn: ({ id, options }: { id: string; options?: SchemaSyncOptions }) =>
      datasourcesApi.syncSchema(id, options),
    onSuccess: async (_result, { id }) => {
      await Promise.all([
        invalidateDatasourceList(),
        queryClient.invalidateQueries({ queryKey: ["datasources", id, "tables"] }),
      ]);
    },
  });
  const healthMutation = useMutation({
    mutationFn: (id: string) => datasourcesApi.checkDatasourceHealth(id),
    onSuccess: invalidateDatasourceList,
  });

  const setActiveDatasourceId = (id: string) => {
    const previousId = useDatasourceSelectionStore.getState().activeDatasourceId;
    setSelectedDatasourceId(id);
    if (previousId && previousId !== id) {
      void datasourcesApi.releaseDatasource(previousId).catch((error) => {
        console.warn("Failed to release datasource pool on switch:", error);
      });
    }
  };

  return {
    datasources,
    activeDatasourceId,
    activeDatasource,
    setActiveDatasourceId,
    tables: tablesQuery.data ?? [],
    loadingDatasources: datasourcesQuery.isPending,
    loadingSchema: datasourcesQuery.isPending || tablesQuery.isPending,
    datasourceError: errorMessage(datasourcesQuery.error, "读取数据源失败"),
    schemaError: errorMessage(tablesQuery.error, "读取数据库结构失败"),
    refreshDatasources: async () => {
      await datasourcesQuery.refetch();
    },
    refreshSchema: async () => {
      if (activeDatasource) {
        await tablesQuery.refetch();
      } else {
        await datasourcesQuery.refetch();
      }
    },
    createDatasource: createMutation.mutateAsync,
    updateDatasource: (id: string, params: DataSourceUpdateParams) =>
      updateMutation.mutateAsync({ id, params }),
    deleteDatasource: (id: string, confirm?: DeleteConfirm) =>
      deleteMutation.mutateAsync({ id, confirm }),
    syncSchema: (id: string, options?: SchemaSyncOptions) =>
      syncMutation.mutateAsync({ id, options }),
    checkHealth: healthMutation.mutateAsync,
  };
}
