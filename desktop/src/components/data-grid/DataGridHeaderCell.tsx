import { MoreVertical } from "lucide-react";
import type { ColumnFilter, FilterMode, SortState } from "../../hooks/useDataTableView";
import type { DataGridColumnType } from "./types";
import { DataGridColumnMenu } from "./DataGridColumnMenu";

interface DataGridHeaderCellProps {
  column: string;
  typeInfo?: DataGridColumnType;
  filter?: ColumnFilter;
  sortState: SortState;
  menuOpen: boolean;
  onToggleMenu: () => void;
  onSort: (direction: "asc" | "desc") => void;
  onClearSort: () => void;
  onFilter: (mode: FilterMode, value?: string) => void;
  onClearFilter: () => void;
  onCopyColumnName: () => void;
  onCopySelectColumn: () => void;
  onHideColumn: () => void;
}

function getTypeBadge(typeInfo?: DataGridColumnType) {
  if (!typeInfo) return { icon: "abc", label: "varchar" };
  const type = typeInfo.dataType.toLowerCase();
  if (typeInfo.isPrimaryKey) return { icon: "key", label: type };
  if (typeInfo.isForeignKey) return { icon: "ref", label: type };
  if (["int", "decimal", "double", "float", "number"].some((part) => type.includes(part))) return { icon: "#", label: type };
  if (type.includes("json")) return { icon: "{}", label: type };
  if (type.includes("date") || type.includes("time")) return { icon: "date", label: type };
  return { icon: "abc", label: type };
}

export function DataGridHeaderCell({
  column,
  typeInfo,
  filter,
  sortState,
  menuOpen,
  onToggleMenu,
  onSort,
  onClearSort,
  onFilter,
  onClearFilter,
  onCopyColumnName,
  onCopySelectColumn,
  onHideColumn,
}: DataGridHeaderCellProps) {
  const typeBadge = getTypeBadge(typeInfo);

  return (
    <div className="data-grid-header-cell">
      <div className="data-grid-header-top">
        <span className="data-grid-column-name">{column}</span>
        <div className="flex items-center gap-1">
          {sortState?.column === column && <span className="text-[var(--accent-indigo)]">{sortState.direction === "asc" ? "▲" : "▼"}</span>}
          {filter && <span className="text-[var(--accent-teal)]">●</span>}
          <button className="data-grid-button !h-5 !min-w-5 !px-1" type="button" onClick={(event) => { event.stopPropagation(); onToggleMenu(); }}>
            <MoreVertical size={12} />
          </button>
        </div>
      </div>
      <div className="data-grid-column-type">
        <span>{typeBadge.icon}</span>
        <span>{typeBadge.label}</span>
      </div>
      {menuOpen && (
        <DataGridColumnMenu
          column={column}
          filter={filter}
          sortState={sortState}
          onSort={onSort}
          onClearSort={onClearSort}
          onFilter={onFilter}
          onClearFilter={onClearFilter}
          onCopyColumnName={onCopyColumnName}
          onCopySelectColumn={onCopySelectColumn}
          onHideColumn={onHideColumn}
        />
      )}
    </div>
  );
}
