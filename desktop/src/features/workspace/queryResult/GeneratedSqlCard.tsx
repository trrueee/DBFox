import { Terminal } from "lucide-react";
import { generatedSql } from "../../../mock/databoxMock";

interface GeneratedSqlCardProps {
  onOpenSqlConsole: () => void;
  onSetSqlQuery: (sql: string) => void;
}

export function GeneratedSqlCard({ onOpenSqlConsole, onSetSqlQuery }: GeneratedSqlCardProps) {
  return (
    <div className="hifi-ai-card">
      <div className="hifi-ai-card-header">生成的 SQL 查询</div>
      <div className="hifi-ai-card-body">
        <pre className="hifi-sql-card font-mono text-[10px] leading-relaxed p-3 text-slate-800">{generatedSql}</pre>
        <div className="hifi-sql-card-action">
          <button
            className="hifi-guide-btn-secondary flex items-center gap-1"
            style={{ height: "24px", fontSize: "10px" }}
            onClick={() => {
              onSetSqlQuery(generatedSql);
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
