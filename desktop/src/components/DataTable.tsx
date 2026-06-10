import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import gsap from "gsap";
import { MoreVertical } from "lucide-react";
import { buildInsertSql, buildRowJson, normalizeCopyValue } from "../lib/sqlCopy";
import { useDataTableView } from "../hooks/useDataTableView";
import { DataGridToolbar } from "./data-grid/DataGridToolbar";
import { DataGridHeaderCell } from "./data-grid/DataGridHeaderCell";
import { DataGridCell } from "./data-grid/DataGridCell";
import { DataGridInspector } from "./data-grid/DataGridInspector";
import { DataGridContextMenu } from "./data-grid/DataGridContextMenu";
import { JsonTree, tryParseJson } from "./data-grid/json";
import type { DataGridContextMenuState, DataGridDensity, DataGridInspectState } from "./data-grid/types";
import "./data-grid/data-grid.css";

interface DataTableProps {
  columns: string[];
  rows: Record<string, unknown>[];
  numericColumns?: string[];
  maxHeight?: string;
  tableName?: string;
  databaseName?: string;
  columnTypes?: Record<string, { dataType: string; isPrimaryKey: boolean; isForeignKey: boolean }>;
}

function isNumericValue(value: unknown) {
  return typeof value === "number";
}

function makeSelectColumnSql(column: string, tableName: string, databaseName?: string) {
  const table = databaseName ? `\`${databaseName}\`.\`${tableName}\`` : `\`${tableName}\``;
  return `SELECT \`${column}\`\nFROM ${table}\nLIMIT 100;`;
}

function normalizeFilterValue(value: unknown) {
  if (value === null || value === undefined) return "";
  return String(value);
}

export function DataTable({
  columns,
  rows,
  numericColumns,
  maxHeight,
  tableName,
  databaseName,
  columnTypes,
}: DataTableProps) {
  const numericSet = useMemo(() => new Set(numericColumns ?? []), [numericColumns]);
  const tbodyRef = useRef<HTMLTableSectionElement>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [openColumnMenu, setOpenColumnMenu] = useState<string | null>(null);
  const [density, setDensity] = useState<DataGridDensity>("compact");
  const [selectedCell, setSelectedCell] = useState<{ rowIndex: number; column: string } | null>(null);
  const [contextMenu, setContextMenu] = useState<DataGridContextMenuState | null>(null);
  const [inspect, setInspect] = useState<DataGridInspectState | null>(null);
  const [preview, setPreview] = useState<{ value: string; isJson: boolean; rect: DOMRect } | null>(null);

  const {
    visibleColumns,
    visibleRows,
    sortState,
    setSortState,
    filters,
    setFilter,
    clearFilter,
    clearAllFilters,
    hiddenColumns,
    toggleHideColumn,
    showAllColumns,
  } = useDataTableView({ columns, rows });

  useEffect(() => {
    if (!tbodyRef.current) return;
    const rowNodes = tbodyRef.current.querySelectorAll("tr");
    gsap.fromTo(rowNodes, { opacity: 0, y: 4 }, { opacity: 1, y: 0, duration: 0.16, stagger: 0.018, ease: "power1.out" });
  }, [visibleRows]);

  const showToast = useCallback((message: string) => {
    setToast(message);
    window.setTimeout(() => setToast((current) => (current === message ? null : current)), 1500);
  }, []);

  const copyText = useCallback(async (text: string, message: string) => {
    await navigator.clipboard.writeText(text);
    showToast(message);
  }, [showToast]);

  const handleCopyCell = useCallback(async (value: unknown) => {
    await copyText(normalizeCopyValue(value), "已复制单元格");
  }, [copyText]);

  const handleCopyRowJson = useCallback(async (row: Record<string, unknown>) => {
    await copyText(buildRowJson(columns, row), "已复制行 JSON");
  }, [columns, copyText]);

  const handleCopyInsert = useCallback(async (row: Record<string, unknown>) => {
    if (!tableName) {
      showToast("缺少表名，无法生成 INSERT");
      return;
    }
    await copyText(buildInsertSql(tableName, columns, row, databaseName), "已复制 INSERT SQL");
  }, [columns, copyText, databaseName, showToast, tableName]);

  const handleCopyColumnName = useCallback(async (column: string) => {
    await copyText(column, "已复制列名");
    setOpenColumnMenu(null);
  }, [copyText]);

  const handleCopySelectColumn = useCallback(async (column: string) => {
    if (!tableName) {
      showToast("缺少表名，无法生成 SELECT");
      return;
    }
    await copyText(makeSelectColumnSql(column, tableName, databaseName), "已复制 SELECT 当前列");
    setOpenColumnMenu(null);
  }, [copyText, databaseName, showToast, tableName]);

  const handleHideColumn = useCallback((column: string) => {
    toggleHideColumn(column);
    setOpenColumnMenu(null);
    showToast(`已隐藏列 ${column}`);
  }, [showToast, toggleHideColumn]);

  const handleResetView = useCallback(() => {
    clearAllFilters();
    showAllColumns();
    setSortState(null);
    setOpenColumnMenu(null);
  }, [clearAllFilters, setSortState, showAllColumns]);

  const activeContextRow = contextMenu ? visibleRows[contextMenu.rowIndex] : undefined;
  const activeContextValue = contextMenu?.column && activeContextRow ? activeContextRow[contextMenu.column] : undefined;

  if (columns.length === 0) {
    return <div className="data-grid-empty">暂无列信息</div>;
  }

  return (
    <div className="data-grid-root" style={{ maxHeight: maxHeight ?? "100%" }} onClick={() => setOpenColumnMenu(null)}>
      {toast && <div className="data-grid-toast">{toast}</div>}

      <DataGridToolbar
        rowsCount={rows.length}
        visibleRowsCount={visibleRows.length}
        filters={filters}
        sortState={sortState}
        hiddenColumnsCount={hiddenColumns.size}
        density={density}
        onClearFilter={clearFilter}
        onClearSort={() => setSortState(null)}
        onShowAllColumns={showAllColumns}
        onResetView={handleResetView}
        onToggleDensity={() => setDensity((current) => current === "compact" ? "comfortable" : "compact")}
      />

      {visibleRows.length === 0 ? (
        <div className="data-grid-empty">没有匹配当前视图条件的数据</div>
      ) : (
        <table className={`data-grid-table ${density === "comfortable" ? "data-grid-table--comfortable" : ""}`}>
          <thead>
            <tr>
              <th className="data-grid-index-cell">#</th>
              {visibleColumns.map((column) => (
                <th key={column}>
                  <DataGridHeaderCell
                    column={column}
                    typeInfo={columnTypes?.[column]}
                    filter={filters[column]}
                    sortState={sortState}
                    menuOpen={openColumnMenu === column}
                    onToggleMenu={() => setOpenColumnMenu((current) => current === column ? null : column)}
                    onSort={(direction) => {
                      setSortState({ column, direction });
                      setOpenColumnMenu(null);
                    }}
                    onClearSort={() => {
                      setSortState(null);
                      setOpenColumnMenu(null);
                    }}
                    onFilter={(mode, value) => setFilter(column, mode, value)}
                    onClearFilter={() => clearFilter(column)}
                    onCopyColumnName={() => void handleCopyColumnName(column)}
                    onCopySelectColumn={() => void handleCopySelectColumn(column)}
                    onHideColumn={() => handleHideColumn(column)}
                  />
                </th>
              ))}
            </tr>
          </thead>
          <tbody ref={tbodyRef}>
            {visibleRows.map((row, rowIndex) => {
              const rowSelected = selectedCell?.rowIndex === rowIndex;
              return (
                <tr key={rowIndex} className={rowSelected ? "data-grid-row--selected" : undefined}>
                  <td
                    className="data-grid-index-cell"
                    onContextMenu={(event) => {
                      event.preventDefault();
                      setContextMenu({ rowIndex, x: event.clientX, y: event.clientY });
                    }}
                  >
                    <button
                      type="button"
                      className="border-0 bg-transparent cursor-pointer text-[var(--text-muted)]"
                      onClick={(event) => {
                        event.stopPropagation();
                        const rect = event.currentTarget.getBoundingClientRect();
                        setContextMenu({ rowIndex, x: rect.left, y: rect.bottom + 4 });
                      }}
                    >
                      <MoreVertical size={11} />
                    </button>
                    <span className="ml-1">{rowIndex + 1}</span>
                  </td>

                  {visibleColumns.map((column) => {
                    const value = row[column];
                    const numeric = numericSet.has(column) || isNumericValue(value);
                    const selected = selectedCell?.rowIndex === rowIndex && selectedCell.column === column;
                    return (
                      <DataGridCell
                        key={`${rowIndex}-${column}`}
                        value={value}
                        numeric={numeric}
                        selected={selected}
                        onSelect={() => {
                          setSelectedCell({ rowIndex, column });
                          void handleCopyCell(value);
                        }}
                        onContextMenu={(event) => {
                          event.preventDefault();
                          setSelectedCell({ rowIndex, column });
                          setContextMenu({ rowIndex, column, x: event.clientX, y: event.clientY });
                        }}
                        onInspect={(valueText, isJson) => setInspect({ column, value: valueText, isJson })}
                        onPreviewChange={setPreview}
                      />
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {preview && (
        <div className="data-grid-preview" style={{ left: Math.min(preview.rect.left, window.innerWidth - 560), top: preview.rect.bottom + 8 }}>
          {preview.isJson && tryParseJson(preview.value) ? (
            <JsonTree data={tryParseJson(preview.value)!} />
          ) : (
            <pre className="data-grid-inspector-pre">{preview.value}</pre>
          )}
        </div>
      )}

      <DataGridContextMenu
        menu={contextMenu}
        row={activeContextRow}
        value={activeContextValue}
        onClose={() => setContextMenu(null)}
        onCopyCell={handleCopyCell}
        onCopyRowJson={handleCopyRowJson}
        onCopyInsert={handleCopyInsert}
        onFilterEquals={(column, value) => setFilter(column, "contains", normalizeFilterValue(value))}
        onFilterNotNull={(column) => setFilter(column, "is_not_null")}
        onClearColumnFilter={clearFilter}
      />

      <DataGridInspector
        inspect={inspect}
        onClose={() => setInspect(null)}
        onCopy={(value) => copyText(value, "已复制完整内容")}
      />
    </div>
  );
}
