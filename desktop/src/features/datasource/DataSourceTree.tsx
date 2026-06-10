import type { MouseEvent } from "react";
import { Database, FileText, Search } from "lucide-react";
import { dataSourceModules } from "../../mock/schema";
import type { DataSourceContextMenuKind } from "../../types/workspace";

type DataSourceTreeProps = {
  selectedTables: string[];
  onTableClick: (event: MouseEvent, tableName: string) => void;
  onContextMenu: (event: MouseEvent, kind: DataSourceContextMenuKind, target: string) => void;
};

export default function DataSourceTree({ selectedTables, onTableClick, onContextMenu }: DataSourceTreeProps) {
  return (
    <>
      <h3>数据源</h3>
      <div className="source" onContextMenu={(event) => onContextMenu(event, "database", "prod-mysql")}>
        <Database size={18} />
        <b>prod-mysql</b>
        <small>MySQL 8.0</small>
      </div>
      <label className="source-search">
        <Search size={14} />
        <input placeholder="搜索表或字段" />
      </label>
      <div className="tree">
        <p onContextMenu={(event) => onContextMenu(event, "schema", "小红书数据")}>
          <Database size={14} />
          小红书数据
        </p>
        {dataSourceModules.map((module) => (
          <section key={module.name}>
            <h4>{module.name}</h4>
            {module.tables.map((table) => (
              <button
                key={table}
                className={selectedTables.includes(table) ? "sel" : ""}
                draggable
                onDragStart={(event) => event.dataTransfer.setData("text/plain", table)}
                onClick={(event) => onTableClick(event, table)}
                onDoubleClick={(event) => onTableClick(event, table)}
                onContextMenu={(event) => onContextMenu(event, "table", table)}
              >
                <FileText size={13} />
                {table}
              </button>
            ))}
          </section>
        ))}
      </div>
    </>
  );
}
