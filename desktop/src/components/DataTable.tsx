import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import gsap from "gsap";
import {
  observeElementOffset,
  useVirtualizer,
  type Rect,
  type Virtualizer,
} from "@tanstack/react-virtual";
import {
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type ColumnFiltersState,
  type Row,
  type SortingState,
  type VisibilityState,
} from "@tanstack/react-table";
import { Copy, FileJson, MoreVertical } from "lucide-react";
import { buildInsertSql, buildRowJson, normalizeCopyValue } from "../lib/sqlCopy";
import { DataGridToolbar } from "./data-grid/DataGridToolbar";
import { DataGridHeaderCell } from "./data-grid/DataGridHeaderCell";
import { DataGridCell } from "./data-grid/DataGridCell";
import { DataGridInspector } from "./data-grid/DataGridInspector";
import { DataGridContextMenu } from "./data-grid/DataGridContextMenu";
import {
  ContextMenu,
  ContextMenuTrigger,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "./ui";
import type { ColumnFilter, DataGridDensity, DataGridInspectState, FilterMode, SortState } from "./data-grid/types";
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

const VIRTUAL_FALLBACK_RECT: Rect = { width: 1024, height: 640 };

type DataTableRow = Record<string, unknown>;

function observeDataGridRect(instance: Virtualizer<HTMLDivElement, HTMLTableRowElement>, cb: (rect: Rect) => void) {
  const emitRect = () => {
    const rect = instance.scrollElement?.getBoundingClientRect();
    cb({
      width: rect?.width || VIRTUAL_FALLBACK_RECT.width,
      height: rect?.height || VIRTUAL_FALLBACK_RECT.height,
    });
  };

  emitRect();

  const scrollElement = instance.scrollElement;
  if (!scrollElement || !globalThis.ResizeObserver) return undefined;

  const observer = new ResizeObserver(emitRect);
  observer.observe(scrollElement);
  return () => observer.disconnect();
}

function observeDataGridOffset(instance: Virtualizer<HTMLDivElement, HTMLTableRowElement>, cb: (offset: number, isScrolling: boolean) => void) {
  cb(instance.scrollElement?.scrollTop ?? 0, false);
  return observeElementOffset(instance, cb);
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

function buildColumnFilter(column: string, mode: FilterMode, value?: string): ColumnFilter {
  return { column, mode, value };
}

function dataGridFilterFn(row: Row<DataTableRow>, columnId: string, filterValue: unknown) {
  const filter = filterValue as ColumnFilter | undefined;
  if (!filter) return true;

  const value = row.getValue(columnId);
  if (filter.mode === "is_null") return value === null || value === undefined;
  if (filter.mode === "is_not_null") return value !== null && value !== undefined;
  if (!filter.value) return true;
  if (value === null || value === undefined) return false;

  return String(value).toLowerCase().includes(filter.value.toLowerCase());
}

function dataGridSortingFn(rowA: Row<DataTableRow>, rowB: Row<DataTableRow>, columnId: string) {
  const valueA = rowA.getValue(columnId);
  const valueB = rowB.getValue(columnId);
  const isNullA = valueA === null || valueA === undefined;
  const isNullB = valueB === null || valueB === undefined;

  if (isNullA && isNullB) return 0;
  if (isNullA) return 1;
  if (isNullB) return -1;

  const isDateA = valueA instanceof Date || (typeof valueA === "string" && !Number.isNaN(Date.parse(valueA)) && Number.isNaN(Number(valueA)));
  const isDateB = valueB instanceof Date || (typeof valueB === "string" && !Number.isNaN(Date.parse(valueB)) && Number.isNaN(Number(valueB)));

  if (typeof valueA === "number" && typeof valueB === "number") return valueA - valueB;
  if (isDateA && isDateB) {
    const timeA = valueA instanceof Date ? valueA.getTime() : new Date(String(valueA)).getTime();
    const timeB = valueB instanceof Date ? valueB.getTime() : new Date(String(valueB)).getTime();
    return timeA - timeB;
  }

  return String(valueA).localeCompare(String(valueB), "zh-Hans-CN", { numeric: true });
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
  const tableColumns = useMemo<Array<ColumnDef<DataTableRow, unknown>>>(() => columns.map((column) => ({
    id: column,
    accessorFn: (row) => row[column],
    filterFn: dataGridFilterFn,
    sortingFn: dataGridSortingFn,
  })), [columns]);
  const scrollRootRef = useRef<HTMLDivElement>(null);
  const [scrollRootElement, setScrollRootElement] = useState<HTMLDivElement | null>(null);
  const tbodyRef = useRef<HTMLTableSectionElement>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [density, setDensity] = useState<DataGridDensity>("compact");
  const [selectedCell, setSelectedCell] = useState<{ rowIndex: number; column: string } | null>(null);
  const [inspect, setInspect] = useState<DataGridInspectState | null>(null);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});

  useEffect(() => {
    const columnSet = new Set(columns);
    setSorting((current) => current.filter((item) => columnSet.has(item.id)));
    setColumnFilters((current) => current.filter((item) => columnSet.has(item.id)));
    setColumnVisibility((current) => Object.fromEntries(Object.entries(current).filter(([column]) => columnSet.has(column))));
  }, [columns]);

  const table = useReactTable({
    data: rows,
    columns: tableColumns,
    state: {
      sorting,
      columnFilters,
      columnVisibility,
    },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const visibleColumns = table.getVisibleLeafColumns().map((column) => column.id);
  const visibleRows = table.getRowModel().rows;
  const sortState = useMemo<SortState>(() => {
    const activeSort = sorting[0];
    if (!activeSort) return null;
    return { column: activeSort.id, direction: activeSort.desc ? "desc" : "asc" };
  }, [sorting]);
  const filters = useMemo<Record<string, ColumnFilter>>(() => {
    return Object.fromEntries(columnFilters.map((filter) => [filter.id, filter.value as ColumnFilter]));
  }, [columnFilters]);
  const hiddenColumns = useMemo(() => {
    return new Set(Object.entries(columnVisibility).filter(([, visible]) => visible === false).map(([column]) => column));
  }, [columnVisibility]);

  const setSortState = useCallback((next: SortState) => {
    setSorting(next ? [{ id: next.column, desc: next.direction === "desc" }] : []);
  }, []);

  const setFilter = useCallback((column: string, mode: FilterMode, value?: string) => {
    const filterValue = buildColumnFilter(column, mode, value);
    setColumnFilters((current) => [
      ...current.filter((filter) => filter.id !== column),
      { id: column, value: filterValue },
    ]);
  }, []);

  const clearFilter = useCallback((column: string) => {
    setColumnFilters((current) => current.filter((filter) => filter.id !== column));
  }, []);

  const clearAllFilters = useCallback(() => {
    setColumnFilters([]);
  }, []);

  const toggleHideColumn = useCallback((column: string) => {
    setColumnVisibility((current) => ({ ...current, [column]: current[column] === false }));
  }, []);

  const showAllColumns = useCallback(() => {
    setColumnVisibility({});
  }, []);

  const rowVirtualizer = useVirtualizer({
    count: visibleRows.length,
    getScrollElement: () => scrollRootElement,
    estimateSize: () => density === "comfortable" ? 42 : 30,
    observeElementRect: observeDataGridRect,
    observeElementOffset: observeDataGridOffset,
    overscan: 8,
    initialRect: VIRTUAL_FALLBACK_RECT,
  });
  const virtualRows = rowVirtualizer.getVirtualItems();
  const firstVirtualRow = virtualRows[0];
  const lastVirtualRow = virtualRows[virtualRows.length - 1];
  const virtualPaddingTop = firstVirtualRow?.start ?? 0;
  const virtualPaddingBottom = lastVirtualRow ? rowVirtualizer.getTotalSize() - lastVirtualRow.end : 0;
  const tableColumnSpan = visibleColumns.length + 1;

  useEffect(() => {
    if (!tbodyRef.current) return;
    const rowNodes = tbodyRef.current.querySelectorAll("tr:not(.data-grid-virtual-spacer)");
    gsap.fromTo(rowNodes, { opacity: 0, y: 4 }, { opacity: 1, y: 0, duration: 0.16, stagger: 0.018, ease: "power1.out" });
  }, [virtualRows]);

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
  }, [copyText]);

  const handleCopySelectColumn = useCallback(async (column: string) => {
    if (!tableName) {
      showToast("缺少表名，无法生成 SELECT");
      return;
    }
    await copyText(makeSelectColumnSql(column, tableName, databaseName), "已复制 SELECT 当前列");
  }, [copyText, databaseName, showToast, tableName]);

  const handleHideColumn = useCallback((column: string) => {
    toggleHideColumn(column);
    showToast(`已隐藏列 ${column}`);
  }, [showToast, toggleHideColumn]);

  const handleResetView = useCallback(() => {
    clearAllFilters();
    showAllColumns();
    setSortState(null);
  }, [clearAllFilters, setSortState, showAllColumns]);

  const handleScrollRootRef = useCallback((node: HTMLDivElement | null) => {
    scrollRootRef.current = node;
    setScrollRootElement(node);
  }, []);

  if (columns.length === 0) {
    return <div className="data-grid-empty">暂无列信息</div>;
  }

  return (
    <div ref={handleScrollRootRef} className="data-grid-root" style={{ maxHeight: maxHeight ?? "100%" }}>
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
                    onSort={(direction) => {
                      setSortState({ column, direction });
                    }}
                    onClearSort={() => {
                      setSortState(null);
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
            {virtualPaddingTop > 0 && (
              <tr className="data-grid-virtual-spacer" aria-hidden="true">
                <td
                  className="data-grid-virtual-spacer-cell"
                  colSpan={tableColumnSpan}
                  style={{ "--data-grid-virtual-spacer-height": `${virtualPaddingTop}px` } as CSSProperties}
                />
              </tr>
            )}
            {virtualRows.map((virtualRow) => {
              const rowIndex = virtualRow.index;
              const tableRow = visibleRows[rowIndex];
              if (!tableRow) return null;
              const row = tableRow.original;
              const rowSelected = selectedCell?.rowIndex === rowIndex;
              return (
                <tr key={tableRow.id} data-index={rowIndex} className={rowSelected ? "data-grid-row--selected" : undefined}>
                  <ContextMenu>
                    <ContextMenuTrigger asChild>
                      <td className="data-grid-index-cell">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <button
                              type="button"
                              className="data-grid-row-menu-trigger"
                              aria-label={`行操作 ${rowIndex + 1}`}
                              onClick={(event) => event.stopPropagation()}
                            >
                              <MoreVertical size={11} />
                            </button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent className="data-grid-context-menu" align="start">
                            <DropdownMenuItem className="data-grid-menu-item" onSelect={() => void handleCopyRowJson(row)}>
                              <FileJson size={12} /> 复制行 JSON
                            </DropdownMenuItem>
                            <DropdownMenuItem className="data-grid-menu-item" onSelect={() => void handleCopyInsert(row)}>
                              <Copy size={12} /> 复制 INSERT SQL
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                        <span className="data-grid-row-number">{rowIndex + 1}</span>
                      </td>
                    </ContextMenuTrigger>
                    <DataGridContextMenu
                      row={row}
                      onCopyCell={handleCopyCell}
                      onCopyRowJson={handleCopyRowJson}
                      onCopyInsert={handleCopyInsert}
                      onFilterEquals={(column, value) => setFilter(column, "contains", normalizeFilterValue(value))}
                      onFilterNotNull={(column) => setFilter(column, "is_not_null")}
                      onClearColumnFilter={clearFilter}
                    />
                  </ContextMenu>

                  {visibleColumns.map((column) => {
                    const value = tableRow.getValue(column);
                    const numeric = numericSet.has(column) || isNumericValue(value);
                    const selected = selectedCell?.rowIndex === rowIndex && selectedCell.column === column;
                    return (
                      <ContextMenu key={`${rowIndex}-${column}`}>
                        <ContextMenuTrigger asChild>
                          <DataGridCell
                            value={value}
                            numeric={numeric}
                            selected={selected}
                            onSelect={() => {
                              setSelectedCell({ rowIndex, column });
                              void handleCopyCell(value);
                            }}
                            onContextMenu={() => {
                              setSelectedCell({ rowIndex, column });
                            }}
                            onInspect={(valueText, isJson) => setInspect({ column, value: valueText, isJson })}
                          />
                        </ContextMenuTrigger>
                        <DataGridContextMenu
                          row={row}
                          column={column}
                          value={value}
                          onCopyCell={handleCopyCell}
                          onCopyRowJson={handleCopyRowJson}
                          onCopyInsert={handleCopyInsert}
                          onFilterEquals={(column, value) => setFilter(column, "contains", normalizeFilterValue(value))}
                          onFilterNotNull={(column) => setFilter(column, "is_not_null")}
                          onClearColumnFilter={clearFilter}
                        />
                      </ContextMenu>
                    );
                  })}
                </tr>
              );
            })}
            {virtualPaddingBottom > 0 && (
              <tr className="data-grid-virtual-spacer" aria-hidden="true">
                <td
                  className="data-grid-virtual-spacer-cell"
                  colSpan={tableColumnSpan}
                  style={{ "--data-grid-virtual-spacer-height": `${virtualPaddingBottom}px` } as CSSProperties}
                />
              </tr>
            )}
          </tbody>
        </table>
      )}

      <DataGridInspector
        inspect={inspect}
        onClose={() => setInspect(null)}
        onCopy={(value) => copyText(value, "已复制完整内容")}
      />
    </div>
  );
}
