import { useMemo, useState } from "react";
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { CellValuePreview } from "../../../../components/data-grid/CellValuePreview";
import type { SortState } from "./useArtifactTableData";

interface ArtifactTableGridProps {
  columns: string[];
  columnTypes?: Array<string | undefined>;
  rows: string[][];
  sort: SortState | null;
  onSort: (columnIndex: number) => void;
  onCopyCell: (value: string) => void;
  emptyLabel: string;
}

interface ArtifactTableRow {
  rowIndex: number;
  values: string[];
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
  const [selectedCell, setSelectedCell] = useState<{ rowIndex: number; cellIndex: number } | null>(null);
  const tableRows = useMemo<ArtifactTableRow[]>(
    () => rows.map((values, rowIndex) => ({ rowIndex, values })),
    [rows],
  );
  const numericColumnFlags = useMemo(() => computeNumericColumns(columns, rows), [columns, rows]);
  const tableColumns = useMemo<Array<ColumnDef<ArtifactTableRow, string>>>(
    () =>
      columns.map((column, columnIndex) => {
        const columnType = columnTypes[columnIndex];
        const isNumeric = numericColumnFlags[columnIndex];
        const alignmentClass = isNumeric ? "is-numeric" : "is-text";
        return {
          id: `${columnIndex}-${column}`,
          accessorFn: (row) => row.values[columnIndex] ?? "",
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

  return (
    <table className="artifact-table-grid">
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
                const value = cell.getValue<string>();
                const isSelected =
                  selectedCell?.rowIndex === row.original.rowIndex && selectedCell.cellIndex === meta.columnIndex;
                const classes = ["artifact-table-cell"];
                if (value === "NULL") classes.push("is-null");
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
                    aria-selected={isSelected ? "true" : undefined}
                    onClick={() => {
                      setSelectedCell({ rowIndex: row.original.rowIndex, cellIndex: meta.columnIndex });
                      onCopyCell(value);
                    }}
                    title="点击复制单元格"
                  >
                    {value === "NULL" ? (
                      <span className="artifact-table-null-pill">NULL</span>
                    ) : (
                      <CellValuePreview value={value} displayValue={value} detailHint="点击复制单元格" />
                    )}
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

function computeNumericColumns(columns: string[], rows: string[][]): boolean[] {
  return columns.map((_, columnIndex) => {
    if (rows.length === 0) return false;
    let numericCount = 0;
    let validCount = 0;
    for (const row of rows) {
      const cell = row[columnIndex];
      if (cell !== undefined && cell !== "NULL" && cell.trim() !== "") {
        validCount++;
        if (Number.isFinite(Number(cell))) {
          numericCount++;
        }
      }
    }
    return validCount > 0 && numericCount === validCount;
  });
}
