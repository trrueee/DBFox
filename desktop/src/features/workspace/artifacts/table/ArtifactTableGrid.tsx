import type { SortState } from "./useArtifactTableData";

interface ArtifactTableGridProps {
  columns: string[];
  rows: string[][];
  sort: SortState | null;
  onSort: (columnIndex: number) => void;
  onCopyCell: (value: string) => void;
  emptyLabel: string;
}

export function ArtifactTableGrid({ columns, rows, sort, onSort, onCopyCell, emptyLabel }: ArtifactTableGridProps) {
  return (
    <table className="hifi-table artifact-table-grid min-w-full">
      <thead>
        <tr>
          {columns.map((column, columnIndex) => (
            <th key={`${column}-${columnIndex}`} className="artifact-table-head">
              <button type="button" className="artifact-table-head-button" onClick={() => onSort(columnIndex)}>
                <span>{column}</span>
                {sort?.columnIndex === columnIndex && (
                  <span className="hifi-artifact-sort-indicator">{sort.direction === "asc" ? "↑" : "↓"}</span>
                )}
              </button>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.length > 0 ? (
          rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (
                <td
                  key={`${rowIndex}-${cellIndex}`}
                  className={cellClassName(cell)}
                  onClick={() => onCopyCell(cell)}
                  title="点击复制单元格"
                >
                  {cell === "NULL" ? <span className="artifact-table-null-pill">NULL</span> : cell}
                </td>
              ))}
            </tr>
          ))
        ) : (
          <tr>
            <td colSpan={columns.length} className="hifi-result-empty">
              {emptyLabel}
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

function cellClassName(value: string): string {
  const classes = ["cursor-copy", "artifact-table-cell"];
  if (value === "NULL") classes.push("is-null");
  if (value.trim() !== "" && Number.isFinite(Number(value))) {
    classes.push("is-numeric", "text-right", "tabular-nums");
  }
  return classes.join(" ");
}
