import { compactJsonPreview, tryParseJson } from "./json";

interface DataGridCellProps {
  value: unknown;
  selected: boolean;
  numeric: boolean;
  onSelect: () => void;
  onContextMenu: (event: React.MouseEvent<HTMLTableCellElement>) => void;
  onInspect: (value: string, isJson: boolean) => void;
  onPreviewChange: (preview: { value: string; isJson: boolean; rect: DOMRect } | null) => void;
}

function stringifyValue(value: unknown) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function DataGridCell({ value, selected, numeric, onSelect, onContextMenu, onInspect, onPreviewChange }: DataGridCellProps) {
  const parsedJson = tryParseJson(value);
  const isJson = parsedJson !== null;
  const valueText = stringifyValue(value);

  const handleMouseEnter = (event: React.MouseEvent<HTMLTableCellElement>) => {
    if (isJson || valueText.length > 40) {
      onPreviewChange({ value: valueText, isJson, rect: event.currentTarget.getBoundingClientRect() });
    }
  };

  if (value === null || value === undefined) {
    return (
      <td className={selected ? "data-grid-cell--selected" : undefined} onClick={onSelect} onContextMenu={onContextMenu}>
        <span className="data-grid-null">NULL</span>
      </td>
    );
  }

  if (isJson && parsedJson) {
    return (
      <td
        className={selected ? "data-grid-cell--selected" : undefined}
        onClick={onSelect}
        onDoubleClick={() => onInspect(valueText, true)}
        onContextMenu={onContextMenu}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={() => onPreviewChange(null)}
        title="双击查看完整 JSON"
      >
        <span className="data-grid-json-pill">JSON · {compactJsonPreview(parsedJson)}</span>
      </td>
    );
  }

  return (
    <td
      className={selected ? "data-grid-cell--selected" : undefined}
      onClick={onSelect}
      onDoubleClick={() => onInspect(valueText, false)}
      onContextMenu={onContextMenu}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={() => onPreviewChange(null)}
      style={{ textAlign: numeric ? "right" : "left", fontFamily: numeric ? "var(--font-mono)" : undefined }}
      title={valueText.length > 80 ? "双击查看完整内容" : valueText}
    >
      {valueText}
    </td>
  );
}
