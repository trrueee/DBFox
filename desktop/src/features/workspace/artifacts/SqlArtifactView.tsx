import { Terminal } from "lucide-react";
import type { SqlArtifact } from "../../../types/agentArtifact";

interface SqlArtifactViewProps {
  artifact: SqlArtifact;
  onOpenSqlConsole: () => void;
  onSetSqlQuery: (sql: string) => void;
}

export function SqlArtifactView({ artifact, onOpenSqlConsole, onSetSqlQuery }: SqlArtifactViewProps) {
  return (
    <div className="hifi-ai-card">
      <div className="hifi-ai-card-header">{artifact.title}</div>
      <div className="hifi-ai-card-body">
        {artifact.description && <p className="text-[10px] text-slate-500 px-3 pt-2">{artifact.description}</p>}
        <pre className="hifi-sql-card font-mono text-[10px] leading-relaxed p-3 text-slate-800">{artifact.sql}</pre>
        <div className="hifi-sql-card-action">
          <button
            className="hifi-guide-btn-secondary flex items-center gap-1"
            style={{ height: "24px", fontSize: "10px" }}
            onClick={() => {
              onSetSqlQuery(artifact.sql);
              onOpenSqlConsole();
            }}
          >
            <Terminal size={10} />
            在 SQL 工作台打开
          </button>
        </div>
      </div>
    </div>
  );
}
