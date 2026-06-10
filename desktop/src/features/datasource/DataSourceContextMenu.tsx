import { GitMerge, Sparkles, Table2, Terminal, Trash2 } from "lucide-react";
import type { DataSourceContextMenuState, TableSubTab } from "../../types/workspace";

type DataSourceContextMenuProps = {
  menu: DataSourceContextMenuState;
  selectedTables: string[];
  onOpenTable: (tableName: string, initialSubTab?: TableSubTab) => void;
  onOpenSql: () => void;
  onOpenMultiTableWorkspace: () => void;
  onAddQueryContext: () => void;
};

export default function DataSourceContextMenu({
  menu,
  selectedTables,
  onOpenTable,
  onOpenSql,
  onOpenMultiTableWorkspace,
  onAddQueryContext,
}: DataSourceContextMenuProps) {
  return (
    <div className="menu" style={{ left: menu.x, top: menu.y }} onClick={(event) => event.stopPropagation()}>
      {menu.kind === "table" && (
        <>
          <button onClick={() => onOpenTable(menu.target, "preview")}>
            <Table2 size={14} />
            预览表数据
          </button>
          <button onClick={() => onOpenTable(menu.target, "schema")}>
            <Table2 size={14} />
            查看字段结构
          </button>
          <button onClick={onOpenSql}>
            <Terminal size={14} />
            打开 SQL 控制台
          </button>
          <button onClick={onAddQueryContext}>
            <Sparkles size={14} />
            作为问数上下文
          </button>
          <hr />
          <button className="danger">
            <Trash2 size={14} />
            删除表
          </button>
        </>
      )}
      {menu.kind === "multi-table" && (
        <button onClick={onOpenMultiTableWorkspace} disabled={selectedTables.length < 2}>
          <GitMerge size={14} />
          作为联合 Workspace 打开
        </button>
      )}
      {menu.kind !== "table" && menu.kind !== "multi-table" && (
        <button onClick={onOpenSql}>
          <Terminal size={14} />
          打开 SQL 控制台
        </button>
      )}
    </div>
  );
}
