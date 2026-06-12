import { TableErPane } from "./table/TableErPane";
import { TablePreviewPane } from "./table/TablePreviewPane";
import { TableSchemaPane } from "./table/TableSchemaPane";

interface TableWorkspaceProps {
  tableId: string;
  currentSubTab: string;
  onSubTabChange: (subTab: string) => void;
  onOpenSqlConsole: () => void;
  onToast: (message: string) => void;
}

const subTabs = [
  ["preview", "数据预览"],
  ["schema", "字段结构"],
  ["er", "关系图"],
] as const;

export function TableWorkspace({ tableId, currentSubTab, onSubTabChange, onOpenSqlConsole, onToast }: TableWorkspaceProps) {
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
        {currentSubTab === "preview" && <TablePreviewPane tableId={tableId} onOpenSqlConsole={onOpenSqlConsole} onToast={onToast} />}
        {currentSubTab === "schema" && <TableSchemaPane tableId={tableId} />}
        {currentSubTab === "er" && <TableErPane tableId={tableId} />}
      </div>
    </div>
  );
}
