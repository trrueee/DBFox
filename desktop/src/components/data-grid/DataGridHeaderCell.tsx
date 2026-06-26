import { MoreVertical } from "lucide-react";
import type { ColumnFilter, DataGridColumnType, FilterMode, SortState } from "./types";
import { DataGridColumnMenu } from "./DataGridColumnMenu";
import { DropdownMenu, DropdownMenuTrigger, Tooltip, TooltipContent, TooltipTrigger } from "../ui";

interface DataGridHeaderCellProps {
  column: string;
  typeInfo?: DataGridColumnType;
  filter?: ColumnFilter;
  sortState: SortState;
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
        <div className="data-grid-header-actions">
          {sortState?.column === column && <span className="data-grid-header-sort-indicator">{sortState.direction === "asc" ? "▲" : "▼"}</span>}
          {filter && <span className="data-grid-header-filter-indicator">●</span>}
          <DropdownMenu>
            <Tooltip>
              <TooltipTrigger asChild>
                <DropdownMenuTrigger asChild>
                  <button
                    className="data-grid-column-menu-trigger"
                    type="button"
                    aria-label={`列操作 ${column}`}
                    onClick={(event) => event.stopPropagation()}
                  >
                    <MoreVertical size={12} />
                  </button>
                </DropdownMenuTrigger>
              </TooltipTrigger>
              <TooltipContent>列操作</TooltipContent>
            </Tooltip>
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
          </DropdownMenu>
        </div>
      </div>
      <div className="data-grid-column-type">
        <span>{typeBadge.icon}</span>
        <span>{typeBadge.label}</span>
      </div>
    </div>
  );
}
