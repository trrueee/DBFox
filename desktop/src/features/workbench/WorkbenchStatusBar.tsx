import type { DataSource, Project } from "../../lib/api";
import type { WorkbenchTab } from "./types";

interface WorkbenchStatusBarProps {
  project: Project | null;
  datasource: DataSource | null;
  activeTab: WorkbenchTab | null;
  onOpenProjects: () => void;
  onOpenDataSources: () => void;
  onStopQuery: () => void;
}

function getEnvLabel(datasource: DataSource | null) {
  if (!datasource) return "OFFLINE";
  return (datasource.env || "dev").toUpperCase();
}

export function WorkbenchStatusBar({ project, datasource, activeTab, onOpenProjects, onOpenDataSources, onStopQuery }: WorkbenchStatusBarProps) {
  return (
    <div className="status-bar">
      <div className="status-bar__left">
        <span className={datasource ? "status-dot status-dot--online" : "status-dot"} />
        <button className="status-bar__button" onClick={onOpenProjects}>{project?.name || "未选择项目"}</button>
        {datasource ? (
          <>
            <span className="status-bar__sep" />
            <button className="status-bar__button" onClick={onOpenDataSources}>{datasource.name}</button>
            <span className="status-bar__sep" />
            <span>{datasource.db_type || "mysql"}</span>
            <span className="status-bar__sep" />
            <strong>{datasource.database_name}</strong>
            <span className={`env-pill env-pill--${datasource.env || "dev"}`}>{getEnvLabel(datasource)}</span>
            {datasource.is_read_only && <span className="readonly-pill">READ ONLY</span>}
          </>
        ) : (
          <span className="status-bar__muted">未连接数据库</span>
        )}
        {activeTab?.resultState === "running" && (
          <>
            <span className="status-bar__sep" />
            <span className="status-bar__running">执行中...</span>
            <button className="status-bar__danger" onClick={onStopQuery}>取消</button>
          </>
        )}
        {activeTab?.resultState === "error" && (
          <>
            <span className="status-bar__sep" />
            <span className="status-bar__error">SQL 执行报错</span>
          </>
        )}
      </div>
      <div className="status-bar__right">
        {activeTab?.lastExecutedAt && <span>已执行</span>}
      </div>
    </div>
  );
}
