import { TableErPane } from "./table/TableErPane";
import { TablePreviewPane } from "./table/TablePreviewPane";
import { TableSchemaPane } from "./table/TableSchemaPane";
import "./TableWorkspace.css";

interface TableWorkspaceProps {
  tableId: string;
  datasourceId: string;
  datasourceDbType?: string | null;
  currentSubTab: string;
  onSubTabChange: (subTab: string) => void;
  onOpenSqlConsole: (initialSql?: string) => void;
  onToast: (message: string) => void;
}

const subTabs = [
  ["preview", "数据预览"],
  ["schema", "字段结构"],
  ["er", "关系图"],
] as const;

export function TableWorkspace({
  tableId,
  datasourceId,
  datasourceDbType,
  currentSubTab,
  onSubTabChange,
  onOpenSqlConsole,
  onToast,
}: TableWorkspaceProps) {
  return (
    <div className="table-workspace">
      <div className="table-workspace__tabs" role="tablist" aria-label="表格工作区视图">
        {subTabs.map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={`table-workspace__tab ${currentSubTab === key ? "is-active" : ""}`}
            role="tab"
            aria-selected={currentSubTab === key}
            onClick={() => onSubTabChange(key)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="table-workspace__body">
        {currentSubTab === "preview" && (
          <TablePreviewPane
            tableId={tableId}
            datasourceId={datasourceId}
            datasourceDbType={datasourceDbType}
            onOpenSqlConsole={onOpenSqlConsole}
            onToast={onToast}
          />
        )}
        {currentSubTab === "schema" && <TableSchemaPane tableId={tableId} datasourceId={datasourceId} />}
        {currentSubTab === "er" && <TableErPane tableId={tableId} datasourceId={datasourceId} />}
      </div>
    </div>
  );
}
