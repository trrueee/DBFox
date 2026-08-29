import { useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { CellValuePreview } from "../../../../components/data-grid/CellValuePreview";
import { classifyCellValue, isNumericCellType } from "../../../../components/data-grid/cellValue";
import type { SortState } from "./useArtifactTableData";

interface ArtifactTableGridProps {
  columns: string[];
  columnTypes?: Array<string | undefined>;
  rows: unknown[][];
  sort: SortState | null;
  onSort: (columnIndex: number) => void;
  onCopyCell: (value: unknown, dataType?: string) => void;
  emptyLabel: string;
}

interface ArtifactTableRow {
  rowIndex: number;
  values: unknown[];
}

interface ArtifactColumnMeta {
  columnIndex: number;
  columnType?: string;
  isNumeric: boolean;
  name: string;
}

export function ArtifactTableGrid({
  columns,
  columnTypes = [],
  rows,
  sort,
  onSort,
  onCopyCell,
  emptyLabel,
}: ArtifactTableGridProps) {
  const tableRef = useRef<HTMLTableElement>(null);
  const [selectedCell, setSelectedCell] = useState<{ rowIndex: number; cellIndex: number } | null>(null);
  const tableRows = useMemo<ArtifactTableRow[]>(
    () => rows.map((values, rowIndex) => ({ rowIndex, values })),
    [rows],
  );
  const numericColumnFlags = useMemo(() => computeNumericColumns(columns, rows), [columns, rows]);
  const tableColumns = useMemo<Array<ColumnDef<ArtifactTableRow, unknown>>>(
    () =>
      columns.map((column, columnIndex) => {
        const columnType = columnTypes[columnIndex];
        const isNumeric = isNumericCellType(columnType) || numericColumnFlags[columnIndex];
        const alignmentClass = isNumeric ? "is-numeric" : "is-text";
        return {
          id: `${columnIndex}-${column}`,
          accessorFn: (row) => row.values[columnIndex],
          header: () => (
            <button
              type="button"
              className={`artifact-table-head-button ${alignmentClass}`}
              aria-label={column}
              onClick={() => onSort(columnIndex)}
            >
              <span className="artifact-table-column-name">{column}</span>
              {columnType && <span className="artifact-table-type-badge">{columnType}</span>}
              {sort?.columnIndex === columnIndex && (
                <span className="artifact-table-sort-indicator">{sort.direction === "asc" ? "↑" : "↓"}</span>
              )}
            </button>
          ),
          cell: (info) => info.getValue(),
          meta: {
            columnIndex,
            columnType,
            isNumeric,
            name: column,
          } satisfies ArtifactColumnMeta,
        };
      }),
    [columns, columnTypes, numericColumnFlags, onSort, sort],
  );
  const table = useReactTable({
    data: tableRows,
    columns: tableColumns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => String(row.rowIndex),
  });

  const openCell = (
    cellElement: HTMLTableCellElement,
    rowIndex: number,
    cellIndex: number,
    value: unknown,
    dataType?: string,
  ) => {
    setSelectedCell({ rowIndex, cellIndex });
    const trigger = cellElement.querySelector<HTMLButtonElement>("[data-cell-value-trigger]");
    if (trigger) {
      trigger.click();
      return;
    }
    onCopyCell(value, dataType);
  };

  const handleCellKeyDown = (
    event: ReactKeyboardEvent<HTMLTableCellElement>,
    rowIndex: number,
    cellIndex: number,
    value: unknown,
    dataType?: string,
  ) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "c") {
      event.preventDefault();
      onCopyCell(value, dataType);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      openCell(event.currentTarget, rowIndex, cellIndex, value, dataType);
      return;
    }
    const movement: Record<string, [number, number]> = {
      ArrowUp: [-1, 0],
      ArrowDown: [1, 0],
      ArrowLeft: [0, -1],
      ArrowRight: [0, 1],
    };
    const delta = movement[event.key];
    if (!delta) return;
    const targetRow = rowIndex + delta[0];
    const targetColumn = cellIndex + delta[1];
    const target = tableRef.current?.querySelector<HTMLTableCellElement>(
      `[data-row-index="${targetRow}"][data-column-index="${targetColumn}"]`,
    );
    if (!target) return;
    event.preventDefault();
    target.focus();
    setSelectedCell({ rowIndex: targetRow, cellIndex: targetColumn });
  };

  return (
    <table
      ref={tableRef}
      className="artifact-table-grid"
      role="grid"
      aria-label="查询结果"
      aria-colcount={columns.length}
      aria-rowcount={tableRows.length + 1}
    >
      <thead>
        {table.getHeaderGroups().map((headerGroup) => (
          <tr key={headerGroup.id} className="artifact-table-row">
            {headerGroup.headers.map((header) => {
              const meta = header.column.columnDef.meta as ArtifactColumnMeta;
              const alignmentClass = meta.isNumeric ? "is-numeric" : "is-text";
              return (
              <th
                key={header.id}
                className={`artifact-table-head ${alignmentClass}`}
                aria-label={meta.columnType ? `${meta.name} ${meta.columnType}` : meta.name}
                aria-sort={sort?.columnIndex === meta.columnIndex
                  ? sort.direction === "asc" ? "ascending" : "descending"
                  : undefined}
              >
                {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
              </th>
              );
            })}
          </tr>
        ))}
      </thead>
      <tbody>
        {tableRows.length > 0 ? (
          table.getRowModel().rows.map((row) => (
            <tr key={row.id} className="artifact-table-row">
              {row.getVisibleCells().map((cell) => {
                const meta = cell.column.columnDef.meta as ArtifactColumnMeta;
                const value = cell.getValue<unknown>();
                const presentation = classifyCellValue(value, { dataType: meta.columnType });
                const isSelected =
                  selectedCell?.rowIndex === row.original.rowIndex && selectedCell.cellIndex === meta.columnIndex;
                const classes = ["artifact-table-cell"];
                if (presentation.kind === "null") classes.push("is-null");
                if (meta.isNumeric) {
                  classes.push("is-numeric");
                } else {
                  classes.push("is-text");
                }
                if (isSelected) classes.push("is-selected");
                return (
                  <td
                    key={cell.id}
                    className={classes.join(" ")}
                    role="gridcell"
                    aria-selected={isSelected ? "true" : undefined}
                    tabIndex={isSelected || (!selectedCell && row.original.rowIndex === 0 && meta.columnIndex === 0) ? 0 : -1}
                    data-row-index={row.original.rowIndex}
                    data-column-index={meta.columnIndex}
                    onClick={() => setSelectedCell({ rowIndex: row.original.rowIndex, cellIndex: meta.columnIndex })}
                    onDoubleClick={(event) => {
                      if ((event.target as HTMLElement).closest("[data-cell-value-trigger]")) return;
                      openCell(event.currentTarget, row.original.rowIndex, meta.columnIndex, value, meta.columnType);
                    }}
                    onKeyDown={(event) => handleCellKeyDown(
                      event,
                      row.original.rowIndex,
                      meta.columnIndex,
                      value,
                      meta.columnType,
                    )}
                    title="单击选择，Ctrl+C 复制，双击查看"
                  >
                    <CellValuePreview
                      value={value}
                      dataType={meta.columnType}
                      columnName={meta.name}
                      detailHint="单击选择，Ctrl+C 复制"
                      onCopyValue={(copyValue) => onCopyCell(copyValue)}
                    />
                  </td>
                );
              })}
            </tr>
          ))
        ) : (
          <tr>
            <td colSpan={columns.length} className="artifact-table-empty">
              {emptyLabel}
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

function computeNumericColumns(columns: string[], rows: unknown[][]): boolean[] {
  return columns.map((_, columnIndex) => {
    if (rows.length === 0) return false;
    let numericCount = 0;
    let validCount = 0;
    for (const row of rows) {
      const cell = row[columnIndex];
      if (cell !== undefined && cell !== null && String(cell).trim() !== "") {
        validCount++;
        if (Number.isFinite(Number(cell))) {
          numericCount++;
        }
      }
    }
    return validCount > 0 && numericCount === validCount;
  });
}
