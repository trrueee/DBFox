import type { MouseEvent } from "react";
import { CellValuePreview } from "./CellValuePreview";
import { cellValueToText, getCellPreviewJson, isCellValuePreviewable } from "./cellValue";

interface DataGridCellProps {
  value: unknown;
  selected: boolean;
  numeric: boolean;
  onSelect: () => void;
  onContextMenu: (event: MouseEvent<HTMLTableCellElement>) => void;
  onInspect: (value: string, isJson: boolean) => void;
}

export function DataGridCell({ value, selected, numeric, onSelect, onContextMenu, onInspect }: DataGridCellProps) {
  const valueText = cellValueToText(value);
  const parsedJson = getCellPreviewJson(value, valueText);
  const isJson = parsedJson !== null;
  const cellClassName = [
    "data-grid-cell",
    selected ? "data-grid-cell--selected" : "",
    numeric ? "data-grid-cell--numeric" : "data-grid-cell--text",
  ].filter(Boolean).join(" ");

  if (value === null || value === undefined) {
    return (
      <td className={cellClassName} onClick={onSelect} onContextMenu={onContextMenu}>
        <span className="data-grid-null">NULL</span>
      </td>
    );
  }

  return (
    <td
      className={cellClassName}
      onClick={onSelect}
      onDoubleClick={() => onInspect(valueText, isJson)}
      onContextMenu={onContextMenu}
      title={isCellValuePreviewable(value, valueText) ? "悬停预览，双击查看完整内容" : valueText}
    >
      <CellValuePreview value={value} displayValue={valueText} detailHint={isJson ? "双击打开完整 JSON" : "双击打开完整内容"} />
    </td>
  );
}
