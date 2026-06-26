export interface DataGridColumnType {
  dataType: string;
  isPrimaryKey: boolean;
  isForeignKey: boolean;
}

export type SortState = {
  column: string;
  direction: "asc" | "desc";
} | null;

export type FilterMode = "contains" | "is_null" | "is_not_null";

export type ColumnFilter = {
  column: string;
  mode: FilterMode;
  value?: string;
};

export interface DataGridColumnMenuState {
  column: string;
  filter?: ColumnFilter;
  sortState: SortState;
}

export interface DataGridInspectState {
  column: string;
  value: string;
  isJson: boolean;
}

export type DataGridDensity = "compact" | "comfortable";

export type SetColumnFilter = (column: string, mode: FilterMode, value?: string) => void;
