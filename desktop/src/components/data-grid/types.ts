import type { ColumnFilter, FilterMode, SortState } from "../../hooks/useDataTableView";

export interface DataGridColumnType {
  dataType: string;
  isPrimaryKey: boolean;
  isForeignKey: boolean;
}

export interface DataGridColumnMenuState {
  column: string;
  filter?: ColumnFilter;
  sortState: SortState;
}

export interface DataGridContextMenuState {
  rowIndex: number;
  column?: string;
  x: number;
  y: number;
}

export interface DataGridInspectState {
  column: string;
  value: string;
  isJson: boolean;
}

export type DataGridDensity = "compact" | "comfortable";

export type SetColumnFilter = (column: string, mode: FilterMode, value?: string) => void;
