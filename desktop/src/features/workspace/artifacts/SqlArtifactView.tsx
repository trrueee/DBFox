import { Copy, Download, Terminal } from "lucide-react";
import type { SqlArtifact } from "../../../types/agentArtifact";
import { copyText, downloadTextFile } from "./artifactActions";

interface SqlArtifactViewProps {
  artifact: SqlArtifact;
  onOpenSqlConsole: () => void;
  onSetSqlQuery: (sql: string) => void;
}

export function SqlArtifactView({ artifact, onOpenSqlConsole, onSetSqlQuery }: SqlArtifactViewProps) {
  const openInSqlConsole = () => {
    onSetSqlQuery(artifact.sql);
    onOpenSqlConsole();
  };

  return (
    <div className="hifi-ai-card">
      <div className="hifi-ai-card-header flex items-center justify-between gap-2">
        <span>{artifact.title}</span>
        <span className="hifi-guide-chip-prod">SQL</span>
      </div>
      <div className="hifi-ai-card-body">
        {artifact.description && <p className="text-[10px] text-slate-500 px-3 pt-2">{artifact.description}</p>}
        <pre className="hifi-sql-card font-mono text-[10px] leading-relaxed p-3 text-slate-800">{artifact.sql}</pre>
        <div className="hifi-sql-card-action flex gap-2">
          <button className="hifi-guide-btn-secondary flex items-center gap-1" style={{ height: "24px", fontSize: "10px" }} onClick={() => copyText(artifact.sql)}>
            <Copy size={10} />
            复制 SQL
          </button>
          <button className="hifi-guide-btn-secondary flex items-center gap-1" style={{ height: "24px", fontSize: "10px" }} onClick={() => downloadTextFile(`${artifact.id}.sql`, artifact.sql, "text/sql;charset=utf-8")}>
            <Download size={10} />
            下载
          </button>
          <button className="hifi-guide-btn-secondary flex items-center gap-1" style={{ height: "24px", fontSize: "10px" }} onClick={openInSqlConsole}>
            <Terminal size={10} />
            在 SQL 工作台打开
          </button>
        </div>
      </div>
    </div>
  );
}
