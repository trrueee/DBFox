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
  // Determine if a column is numeric by scanning all values in the column
  const numericColumns = columns.map((_, colIndex) => {
    if (rows.length === 0) return false;
    let numericCount = 0;
    let validCount = 0;
    for (const row of rows) {
      const cell = row[colIndex];
      if (cell !== undefined && cell !== "NULL" && cell.trim() !== "") {
        validCount++;
        if (Number.isFinite(Number(cell))) {
          numericCount++;
        }
      }
    }
    return validCount > 0 && numericCount === validCount;
  });

  return (
    <table className="hifi-table artifact-table-grid min-w-full">
      <thead>
        <tr>
          {columns.map((column, columnIndex) => {
            const isNumeric = numericColumns[columnIndex];
            return (
              <th
                key={`${column}-${columnIndex}`}
                className={`artifact-table-head ${isNumeric ? "text-right" : "text-left"}`}
                style={{ textAlign: isNumeric ? "right" : "left" }}
              >
                <button
                  type="button"
                  className="artifact-table-head-button"
                  style={{ justifyContent: isNumeric ? "flex-end" : "flex-start" }}
                  onClick={() => onSort(columnIndex)}
                >
                  <span>{column}</span>
                  {sort?.columnIndex === columnIndex && (
                    <span className="hifi-artifact-sort-indicator">{sort.direction === "asc" ? "↑" : "↓"}</span>
                  )}
                </button>
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody>
        {rows.length > 0 ? (
          rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => {
                const isNumeric = numericColumns[cellIndex];
                const classes = ["cursor-copy", "artifact-table-cell"];
                if (cell === "NULL") classes.push("is-null");
                if (isNumeric) {
                  classes.push("is-numeric", "text-right", "tabular-nums");
                } else {
                  classes.push("text-left");
                }
                return (
                  <td
                    key={`${rowIndex}-${cellIndex}`}
                    className={classes.join(" ")}
                    onClick={() => onCopyCell(cell)}
                    title="点击复制单元格"
                  >
                    {cell === "NULL" ? <span className="artifact-table-null-pill">NULL</span> : cell}
                  </td>
                );
              })}
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
