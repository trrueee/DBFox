import type { MouseEvent } from "react";
import DataSourceTree from "../features/datasource/DataSourceTree";
import type { DataSourceContextMenuKind } from "../types/workspace";

type SidebarProps = {
  selectedTables: string[];
  onTableClick: (event: MouseEvent, tableName: string) => void;
  onContextMenu: (event: MouseEvent, kind: DataSourceContextMenuKind, target: string) => void;
};

export default function Sidebar(props: SidebarProps) {
  return (
    <aside className="app-sidebar hifi-sidebar-col">
      <DataSourceTree {...props} />
    </aside>
  );
}
