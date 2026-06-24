import { TableErPane } from "./table/TableErPane";
import { TablePreviewPane } from "./table/TablePreviewPane";
import { TableSchemaPane } from "./table/TableSchemaPane";

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
    <div className="hifi-table-workspace hifi-tab-pane">
      <div className="hifi-workspace-subtabs">
        {subTabs.map(([key, label]) => (
          <div key={key} className={`hifi-workspace-subtab ${currentSubTab === key ? "active" : ""}`} onClick={() => onSubTabChange(key)}>
            {label}
          </div>
        ))}
      </div>

      <div className="hifi-subtab-content flex-1 overflow-auto">
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
