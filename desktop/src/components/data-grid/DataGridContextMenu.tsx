import { Copy, FileJson, ListPlus, X } from "lucide-react";
import type { DataGridContextMenuState } from "./types";

interface DataGridContextMenuProps {
  menu: DataGridContextMenuState | null;
  row?: Record<string, unknown>;
  value?: unknown;
  onClose: () => void;
  onCopyCell: (value: unknown) => Promise<void>;
  onCopyRowJson: (row: Record<string, unknown>) => Promise<void>;
  onCopyInsert: (row: Record<string, unknown>) => Promise<void>;
  onFilterEquals: (column: string, value: unknown) => void;
  onFilterNotNull: (column: string) => void;
  onClearColumnFilter: (column: string) => void;
}

export function DataGridContextMenu({
  menu,
  row,
  value,
  onClose,
  onCopyCell,
  onCopyRowJson,
  onCopyInsert,
  onFilterEquals,
  onFilterNotNull,
  onClearColumnFilter,
}: DataGridContextMenuProps) {
  if (!menu || !row) return null;

  const run = async (action: () => void | Promise<void>) => {
    await action();
    onClose();
  };

  return (
    <>
      <div style={{ position: "fixed", inset: 0, zIndex: 2999 }} onClick={onClose} onContextMenu={(event) => { event.preventDefault(); onClose(); }} />
      <div className="data-grid-context-menu" style={{ left: menu.x, top: menu.y }} onClick={(event) => event.stopPropagation()}>
        {menu.column && (
          <div className="data-grid-menu-section">
            <button className="data-grid-menu-item" type="button" onClick={() => void run(() => onCopyCell(value))}>
              <Copy size={12} /> 复制单元格
            </button>
            <button className="data-grid-menu-item" type="button" onClick={() => void run(() => onFilterEquals(menu.column!, value))}>
              <ListPlus size={12} /> 按当前值筛选
            </button>
            <button className="data-grid-menu-item" type="button" onClick={() => void run(() => onFilterNotNull(menu.column!))}>
              <ListPlus size={12} /> 只看非 NULL
            </button>
            <button className="data-grid-menu-item" type="button" onClick={() => void run(() => onClearColumnFilter(menu.column!))}>
              <X size={12} /> 清除该列筛选
            </button>
          </div>
        )}

        <div className="data-grid-menu-section">
          <button className="data-grid-menu-item" type="button" onClick={() => void run(() => onCopyRowJson(row))}>
            <FileJson size={12} /> 复制行 JSON
          </button>
          <button className="data-grid-menu-item" type="button" onClick={() => void run(() => onCopyInsert(row))}>
            <Copy size={12} /> 复制 INSERT SQL
          </button>
        </div>
      </div>
    </>
  );
}
