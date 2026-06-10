import type { DataSource, Project } from "../../lib/api";
import type { WorkbenchTab } from "./types";

interface WorkbenchStatusBarProps {
  activeProject: Project | null;
  activeDataSource: DataSource | null;
  activeTab: WorkbenchTab | null;
  onOpenProjectDialog: () => void;
  onOpenDatasourceDialog: () => void;
  onStopQuery: () => void;
}

function getEnvBadge(datasource: DataSource | null) {
  if (!datasource) return { label: "OFFLINE", bg: "rgba(148, 163, 184, 0.12)", color: "var(--text-muted)" };
  if (datasource.env === "prod") return { label: "PROD", bg: "rgba(239, 68, 68, 0.12)", color: "var(--accent-red)" };
  if (datasource.env === "test") return { label: "TEST", bg: "rgba(245, 158, 11, 0.12)", color: "var(--accent-amber)" };
  return { label: "DEV", bg: "rgba(16, 185, 129, 0.12)", color: "var(--accent-green)" };
}

export function WorkbenchStatusBar({
  activeProject,
  activeDataSource,
  activeTab,
  onOpenProjectDialog,
  onOpenDatasourceDialog,
  onStopQuery,
}: WorkbenchStatusBarProps) {
  const env = getEnvBadge(activeDataSource);

  return (
    <footer className="wb-status-bar">
      <div className="wb-status-left">
        <span className="font-black text-[var(--accent-green)]">● ONLINE</span>
        {activeProject && (
          <>
            <span className="opacity-40">|</span>
            <button className="wb-status-link" type="button" onClick={onOpenProjectDialog}>{activeProject.name}</button>
          </>
        )}
        {activeDataSource && (
          <>
            <span className="opacity-40">|</span>
            <button className="wb-status-link" type="button" onClick={onOpenDatasourceDialog}>{activeDataSource.name}</button>
            <span className="opacity-40">|</span>
            <span className="font-mono text-[0.66rem]">{activeDataSource.db_type || "mysql"}</span>
            <span className="opacity-40">|</span>
            <span className="font-mono text-[0.66rem] font-bold text-[var(--accent-indigo)]">{activeDataSource.database_name}</span>
            <span className="wb-status-pill" style={{ background: env.bg, color: env.color }}>{env.label}</span>
            <span>只读: <strong className="text-[var(--text-primary)]">{activeDataSource.is_read_only ? "是" : "否"}</strong></span>
          </>
        )}
        {activeTab?.resultState === "running" && (
          <>
            <span className="opacity-40">|</span>
            <span className="animate-pulse font-black text-[var(--accent-indigo)]">执行中...</span>
            <button className="wb-text-button" type="button" onClick={onStopQuery}>取消</button>
          </>
        )}
        {activeTab?.resultState === "error" && (
          <>
            <span className="opacity-40">|</span>
            <span className="font-black text-[var(--accent-red)]">SQL 执行报错</span>
          </>
        )}
      </div>
      <div className="wb-status-right">
        {activeTab?.lastExecutedAt && <span className="font-mono text-[0.64rem] opacity-70">已执行</span>}
      </div>
    </footer>
  );
}
