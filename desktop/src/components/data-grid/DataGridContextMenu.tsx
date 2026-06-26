import { Copy, FileJson, ListPlus, X } from "lucide-react";
import { ContextMenuContent, ContextMenuItem, ContextMenuSeparator } from "../ui";

interface DataGridContextMenuProps {
  row: Record<string, unknown>;
  column?: string;
  value?: unknown;
  onCopyCell: (value: unknown) => Promise<void>;
  onCopyRowJson: (row: Record<string, unknown>) => Promise<void>;
  onCopyInsert: (row: Record<string, unknown>) => Promise<void>;
  onFilterEquals: (column: string, value: unknown) => void;
  onFilterNotNull: (column: string) => void;
  onClearColumnFilter: (column: string) => void;
}

export function DataGridContextMenu({
  row,
  column,
  value,
  onCopyCell,
  onCopyRowJson,
  onCopyInsert,
  onFilterEquals,
  onFilterNotNull,
  onClearColumnFilter,
}: DataGridContextMenuProps) {
  return (
    <ContextMenuContent className="data-grid-context-menu">
      {column && (
        <div className="data-grid-menu-section">
          <ContextMenuItem className="data-grid-menu-item" onSelect={() => void onCopyCell(value)}>
            <Copy size={12} /> 复制单元格
          </ContextMenuItem>
          <ContextMenuItem className="data-grid-menu-item" onSelect={() => onFilterEquals(column, value)}>
            <ListPlus size={12} /> 按当前值筛选
          </ContextMenuItem>
          <ContextMenuItem className="data-grid-menu-item" onSelect={() => onFilterNotNull(column)}>
            <ListPlus size={12} /> 只看非 NULL
          </ContextMenuItem>
          <ContextMenuItem className="data-grid-menu-item" onSelect={() => onClearColumnFilter(column)}>
            <X size={12} /> 清除该列筛选
          </ContextMenuItem>
        </div>
      )}

      {column && <ContextMenuSeparator className="data-grid-menu-separator" />}

      <div className="data-grid-menu-section">
        <ContextMenuItem className="data-grid-menu-item" onSelect={() => void onCopyRowJson(row)}>
          <FileJson size={12} /> 复制行 JSON
        </ContextMenuItem>
        <ContextMenuItem className="data-grid-menu-item" onSelect={() => void onCopyInsert(row)}>
          <Copy size={12} /> 复制 INSERT SQL
        </ContextMenuItem>
      </div>
    </ContextMenuContent>
  );
}
