import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import type { DataSource, ERDiagramData, QueryResult, SchemaColumn, SchemaTable } from "../lib/api";
import { SchemaBrowserHeader, type SchemaBrowserTab } from "../features/schema-browser/SchemaBrowserHeader";
import { SchemaFieldsView } from "../features/schema-browser/SchemaFieldsView";
import { SchemaErView } from "../features/schema-browser/SchemaErView";
import { SchemaPreviewView } from "../features/schema-browser/SchemaPreviewView";
import { TestDataGeneratorDialog } from "../features/schema-browser/TestDataGeneratorDialog";
import "../features/schema-browser/schema-browser.css";

interface SchemaPageProps {
  datasource: DataSource;
  initialViewTab?: SchemaBrowserTab;
  selectedTableName?: string | null;
  onOpenSql?: (sql: string, title?: string) => void;
}

function getErrorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function buildPreviewSql(tableName: string) {
  return `SELECT * FROM \`${tableName}\` LIMIT 100;`;
}

export const SchemaPage = ({ datasource, initialViewTab, selectedTableName, onOpenSql }: SchemaPageProps) => {
  const [tables, setTables] = useState<SchemaTable[]>([]);
  const [selectedTable, setSelectedTable] = useState<SchemaTable | null>(null);
  const [columns, setColumns] = useState<SchemaColumn[]>([]);
  const [columnsLoading, setColumnsLoading] = useState(false);
  const [viewTab, setViewTab] = useState<SchemaBrowserTab>(initialViewTab || "fields");
  const [erData, setErData] = useState<ERDiagramData | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewData, setPreviewData] = useState<QueryResult | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewSqlCopied, setPreviewSqlCopied] = useState(false);
  const [erFocusTable, setErFocusTable] = useState<string | null>(null);
  const [erViewMode, setErViewMode] = useState<"focus" | "module" | "full">("focus");
  const [erDepth, setErDepth] = useState<1 | 2>(1);
  const [erShowInferred, setErShowInferred] = useState(true);
  const [testDataDialogOpen, setTestDataDialogOpen] = useState(false);

  const safeErData = useMemo<ERDiagramData>(() => ({
    nodes: Array.isArray(erData?.nodes) ? erData.nodes : [],
    edges: Array.isArray(erData?.edges) ? erData.edges : [],
  }), [erData]);

  const previewSql = selectedTable ? buildPreviewSql(selectedTable.table_name) : "";

  const handleSelectTable = useCallback(async (table: SchemaTable) => {
    setSelectedTable(table);
    setErFocusTable(table.table_name);
    setColumnsLoading(true);
    setPreviewData(null);
    setPreviewError(null);
    try {
      setColumns(await api.listColumns(table.id));
    } catch (error) {
      console.error("Failed to load schema columns:", error);
      setColumns([]);
    } finally {
      setColumnsLoading(false);
    }
  }, []);

  const fetchTables = useCallback(async (selectName?: string | null) => {
    try {
      const data = await api.listTables(datasource.id);
      setTables(data);
      if (data.length === 0) {
        setSelectedTable(null);
        setColumns([]);
        return;
      }
      const nextTable = selectName ? data.find((table) => table.table_name === selectName) : null;
      await handleSelectTable(nextTable || data[0]);
    } catch (error) {
      console.error("Failed to load schema tables:", error);
      setTables([]);
      setSelectedTable(null);
      setColumns([]);
    }
  }, [datasource.id, handleSelectTable]);

  const fetchERDiagram = useCallback(async () => {
    try {
      setErData(await api.getERDiagram(datasource.id));
    } catch (error) {
      console.error("ER load failed", error);
      setErData({ nodes: [], edges: [] });
    }
  }, [datasource.id]);

  const fetchPreviewData = useCallback(async (tableName: string) => {
    setPreviewLoading(true);
    setPreviewError(null);
    setPreviewData(null);
    try {
      const result = await api.executeSql(datasource.id, buildPreviewSql(tableName));
      setPreviewData(result);
    } catch (error: unknown) {
      setPreviewError(getErrorMessage(error, "预览失败"));
    } finally {
      setPreviewLoading(false);
    }
  }, [datasource.id]);

  useEffect(() => {
    void fetchTables(selectedTableName ?? undefined);
    void fetchERDiagram();
  }, [datasource.id, fetchERDiagram, fetchTables, selectedTableName]);

  useEffect(() => {
    if (initialViewTab) setViewTab(initialViewTab);
  }, [initialViewTab]);

  useEffect(() => {
    if (!selectedTableName || tables.length === 0) return;
    const nextTable = tables.find((table) => table.table_name === selectedTableName);
    if (nextTable && nextTable.id !== selectedTable?.id) void handleSelectTable(nextTable);
  }, [handleSelectTable, selectedTable?.id, selectedTableName, tables]);

  useEffect(() => {
    if (viewTab === "data" && selectedTable) void fetchPreviewData(selectedTable.table_name);
  }, [fetchPreviewData, selectedTable, viewTab]);

  const handleCopyPreviewSql = async () => {
    if (!previewSql) return;
    await navigator.clipboard.writeText(previewSql);
    setPreviewSqlCopied(true);
    window.setTimeout(() => setPreviewSqlCopied(false), 1400);
  };

  const handleOpenPreviewSql = () => {
    if (!previewSql || !selectedTable) return;
    onOpenSql?.(previewSql, `Preview ${selectedTable.table_name}`);
  };

  const handleErFocusChange = async (tableName: string) => {
    setErFocusTable(tableName);
    const found = tables.find((table) => table.table_name === tableName);
    if (found) await handleSelectTable(found);
  };

  return (
    <div className="schema-browser">
      <SchemaBrowserHeader
        selectedTable={selectedTable}
        viewTab={viewTab}
        embedded={Boolean(initialViewTab)}
        onTabChange={setViewTab}
      />

      {viewTab === "fields" && (
        <SchemaFieldsView table={selectedTable} columns={columns} loading={columnsLoading} />
      )}

      {viewTab === "er" && (
        <SchemaErView
          data={safeErData}
          focusTable={erFocusTable}
          viewMode={erViewMode}
          depth={erDepth}
          showInferred={erShowInferred}
          onFocusTableChange={(tableName) => void handleErFocusChange(tableName)}
          onViewModeChange={setErViewMode}
          onDepthChange={setErDepth}
          onShowInferredChange={setErShowInferred}
        />
      )}

      {viewTab === "data" && (
        <SchemaPreviewView
          table={selectedTable}
          databaseName={datasource.database_name}
          previewData={previewData}
          previewSql={previewSql}
          loading={previewLoading}
          error={previewError}
          copied={previewSqlCopied}
          onCopySql={() => void handleCopyPreviewSql()}
          onOpenSql={handleOpenPreviewSql}
          onRefresh={() => selectedTable && void fetchPreviewData(selectedTable.table_name)}
          onGenerateTestData={() => setTestDataDialogOpen(true)}
        />
      )}

      <TestDataGeneratorDialog
        datasource={datasource}
        table={selectedTable}
        open={testDataDialogOpen}
        onClose={() => setTestDataDialogOpen(false)}
        onGenerated={() => selectedTable && void fetchPreviewData(selectedTable.table_name)}
      />
    </div>
  );
};
