import { useState } from "react";
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
  const [mountedSubTabs, setMountedSubTabs] = useState<Record<string, boolean>>({
    [currentSubTab]: true,
  });

  const activateSubTab = (subTab: string) => {
    setMountedSubTabs((current) => current[subTab] ? current : { ...current, [subTab]: true });
    onSubTabChange(subTab);
  };

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
            aria-controls={`table-workspace-panel-${key}`}
            onClick={() => activateSubTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="table-workspace__body">
        {(mountedSubTabs.preview || currentSubTab === "preview") && (
          <div id="table-workspace-panel-preview" className="table-workspace__panel" role="tabpanel" hidden={currentSubTab !== "preview"}>
            <TablePreviewPane
              key={`${datasourceId}:${tableId}`}
              tableId={tableId}
              datasourceId={datasourceId}
              datasourceDbType={datasourceDbType}
              onOpenSqlConsole={onOpenSqlConsole}
              onToast={onToast}
            />
          </div>
        )}
        {(mountedSubTabs.schema || currentSubTab === "schema") && (
          <div id="table-workspace-panel-schema" className="table-workspace__panel" role="tabpanel" hidden={currentSubTab !== "schema"}>
            <TableSchemaPane tableId={tableId} datasourceId={datasourceId} />
          </div>
        )}
        {(mountedSubTabs.er || currentSubTab === "er") && (
          <div id="table-workspace-panel-er" className="table-workspace__panel" role="tabpanel" hidden={currentSubTab !== "er"}>
            <TableErPane tableId={tableId} datasourceId={datasourceId} />
          </div>
        )}
      </div>
    </div>
  );
}
