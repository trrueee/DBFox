import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { api } from "../lib/api";
import type { DataSource, SchemaTable } from "../lib/api";
import { DataTable } from "../components/DataTable";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { TableDataToolbar } from "../features/table-data/TableDataToolbar";
import { TableDataStatusBar } from "../features/table-data/TableDataStatusBar";
import { TableDataEmptyState } from "../features/table-data/TableDataEmptyState";
import { TableDataErrorState, TableDataLoadingState, TableDataNoRowsState } from "../features/table-data/TableDataStateViews";
import "../features/table-data/table-data.css";

interface DataPageProps {
  datasource: DataSource;
  selectedTableName: string | null;
  schemaTables: SchemaTable[];
  onSelectTable: (tableName: string) => void;
}

type ColumnTypeMap = Record<string, { dataType: string; isPrimaryKey: boolean; isForeignKey: boolean }>;

function getErrorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function escapeSqlLike(value: string) {
  return value.replace(/'/g, "''");
}

function buildPreviewSql({
  tableName,
  columns,
  filter,
  page,
  pageSize,
}: {
  tableName: string;
  columns: string[];
  filter: string;
  page: number;
  pageSize: number;
}) {
  const offset = (page - 1) * pageSize;
  let whereClause = "";

  if (filter && columns.length > 0) {
    const escapedFilter = escapeSqlLike(filter);
    const orConditions = columns.map((column) => `\`${column}\` LIKE '%${escapedFilter}%'`).join(" OR ");
    whereClause = ` WHERE ${orConditions}`;
  }

  return `SELECT * FROM \`${tableName}\`${whereClause} LIMIT ${pageSize} OFFSET ${offset};`;
}

export const DataPage = ({ datasource, selectedTableName, schemaTables, onSelectTable }: DataPageProps) => {
  const [columns, setColumns] = useState<string[]>([]);
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [columnTypes, setColumnTypes] = useState<ColumnTypeMap>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(100);
  const [filterText, setFilterText] = useState("");
  const [appliedFilter, setAppliedFilter] = useState("");
  const [latencyMs, setLatencyMs] = useState<number | null>(null);

  const activeTableMeta = useMemo(() => {
    return schemaTables.find((table) => table.table_name === selectedTableName) || null;
  }, [schemaTables, selectedTableName]);

  const fetchTableData = useCallback(async (nextColumns = columns) => {
    if (!selectedTableName) return;
    setLoading(true);
    setError(null);
    try {
      const sql = buildPreviewSql({
        tableName: selectedTableName,
        columns: nextColumns,
        filter: appliedFilter,
        page,
        pageSize,
      });
      const result = await api.executeSql(datasource.id, sql);
      if (!result.success) {
        setError("查询未成功返回结果");
        return;
      }
      setRows(result.rows || []);
      if (result.columns && result.columns.length > 0) setColumns(result.columns);
      setLatencyMs(result.latencyMs || result.totalMs || null);
    } catch (error: unknown) {
      setError(getErrorMessage(error, "数据加载出错，请检查 SQL 权限或过滤语法"));
    } finally {
      setLoading(false);
    }
  }, [appliedFilter, columns, datasource.id, page, pageSize, selectedTableName]);

  const loadInitialSchemaAndData = useCallback(async () => {
    if (!selectedTableName) return;
    setLoading(true);
    setError(null);
    try {
      const sample = await api.executeSql(datasource.id, `SELECT * FROM \`${selectedTableName}\` LIMIT 1;`);
      const nextColumns = sample.success ? sample.columns || [] : [];
      setColumns(nextColumns);
      await fetchTableData(nextColumns);
    } catch (error: unknown) {
      setError(getErrorMessage(error, "加载表格架构失败"));
      setLoading(false);
    }
  }, [datasource.id, fetchTableData, selectedTableName]);

  useEffect(() => {
    setPage(1);
    setFilterText("");
    setAppliedFilter("");
    setRows([]);
    setColumns([]);
    if (selectedTableName) void loadInitialSchemaAndData();
  }, [datasource.id, loadInitialSchemaAndData, selectedTableName]);

  useEffect(() => {
    if (selectedTableName) void fetchTableData();
  }, [appliedFilter, fetchTableData, page, pageSize, selectedTableName]);

  useEffect(() => {
    if (!selectedTableName) {
      setColumnTypes({});
      return;
    }

    const tableInfo = schemaTables.find((table) => table.table_name.toLowerCase().trim() === selectedTableName.toLowerCase().trim());
    if (!tableInfo) {
      setColumnTypes({});
      return;
    }

    let cancelled = false;
    const loadColumnMeta = async () => {
      try {
        const schemaColumns = await api.listColumns(tableInfo.id);
        if (cancelled) return;
        const nextTypes: ColumnTypeMap = {};
        for (const column of schemaColumns) {
          nextTypes[column.column_name] = {
            dataType: column.column_type || column.data_type,
            isPrimaryKey: column.is_primary_key,
            isForeignKey: column.is_foreign_key,
          };
        }
        setColumnTypes(nextTypes);
      } catch (error) {
        console.error("Failed to load columns metadata for data grid:", error);
      }
    };

    void loadColumnMeta();
    return () => {
      cancelled = true;
    };
  }, [schemaTables, selectedTableName]);

  const handleApplyFilter = (event: FormEvent) => {
    event.preventDefault();
    setPage(1);
    setAppliedFilter(filterText.trim());
  };

  const handleClearFilter = () => {
    setFilterText("");
    setAppliedFilter("");
    setPage(1);
  };

  const handlePageSizeChange = (nextPageSize: number) => {
    setPage(1);
    setPageSize(nextPageSize);
  };

  if (!selectedTableName) {
    return <TableDataEmptyState schemaTables={schemaTables} onSelectTable={onSelectTable} />;
  }

  return (
    <div className="table-data-page">
      <TableDataToolbar
        tableName={selectedTableName}
        tableMeta={activeTableMeta}
        filterText={filterText}
        appliedFilter={appliedFilter}
        loading={loading}
        onFilterTextChange={setFilterText}
        onApplyFilter={handleApplyFilter}
        onClearFilter={handleClearFilter}
        onRefresh={() => void fetchTableData()}
      />

      <main className="table-data-content">
        {error ? (
          <TableDataErrorState error={error} onRetry={() => void loadInitialSchemaAndData()} />
        ) : loading && rows.length === 0 ? (
          <TableDataLoadingState />
        ) : rows.length === 0 ? (
          <TableDataNoRowsState appliedFilter={appliedFilter} onClearFilter={handleClearFilter} />
        ) : (
          <div className="table-data-grid-wrap">
            <ErrorBoundary title="数据网格渲染崩溃">
              <DataTable
                columns={columns}
                rows={rows}
                tableName={selectedTableName}
                databaseName={datasource.database_name}
                maxHeight="100%"
                columnTypes={columnTypes}
              />
            </ErrorBoundary>
          </div>
        )}
      </main>

      {!error && rows.length > 0 && (
        <TableDataStatusBar
          tableMeta={activeTableMeta}
          columnsCount={columns.length}
          rowsCount={rows.length}
          latencyMs={latencyMs}
          page={page}
          pageSize={pageSize}
          loading={loading}
          onPageChange={setPage}
          onPageSizeChange={handlePageSizeChange}
        />
      )}
    </div>
  );
};
