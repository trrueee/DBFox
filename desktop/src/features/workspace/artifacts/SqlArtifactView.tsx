import { Copy, Download, Terminal } from "lucide-react";
import type { SqlArtifact } from "../../../types/agentArtifact";
import { copyText, downloadTextFile } from "./artifactActions";

interface SqlArtifactViewProps {
  artifact: SqlArtifact;
  onOpenSqlConsole: (initialSql?: string) => void;
  onToast: (message: string) => void;
}

export function SqlArtifactView({ artifact, onOpenSqlConsole, onToast }: SqlArtifactViewProps) {
  const metadata = [
    artifact.purpose,
    ...(artifact.usedTables || []),
    artifact.validationStatus ? `校验 ${artifact.validationStatus}` : "",
    artifact.executionStatus ? `执行 ${artifact.executionStatus}` : "",
    artifact.rowCount !== undefined ? `${artifact.rowCount} 行` : "",
    artifact.latencyMs !== undefined ? `${artifact.latencyMs}ms` : "",
  ].filter(Boolean);

  const openInSqlConsole = () => {
    onOpenSqlConsole(artifact.sql);
  };

  const handleCopy = async () => {
    const ok = await copyText(artifact.sql);
    onToast(ok ? "已复制 SQL" : "复制失败，请手动选择复制");
  };

  const handleDownload = () => {
    const ok = downloadTextFile(`${artifact.id}.sql`, artifact.sql, "text/sql;charset=utf-8");
    onToast(ok ? "已下载 SQL 文件" : "SQL 下载失败");
  };

  return (
    <div className="hifi-ai-card">
      <div className="hifi-ai-card-header flex items-center justify-between gap-2">
        <span>{artifact.title}</span>
        <span className="hifi-artifact-chip hifi-artifact-chip-sql">SQL</span>
      </div>
      <div className="hifi-ai-card-body">
        {artifact.description && <p className="text-[10px] text-slate-500 px-3 pt-2">{artifact.description}</p>}
        {metadata.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-3 pt-2 text-[10px] text-slate-500">
            {metadata.map((item) => (
              <span key={item} className="rounded border border-slate-200 bg-slate-50 px-2 py-1">{item}</span>
            ))}
          </div>
        )}
        <pre className="hifi-sql-card font-mono text-[10px] leading-relaxed p-3 text-slate-800">{artifact.sql}</pre>
        <div className="hifi-sql-card-action flex gap-2">
          <button className="hifi-guide-btn-secondary flex items-center gap-1" style={{ height: "24px", fontSize: "10px" }} onClick={handleCopy}>
            <Copy size={10} />
            复制 SQL
          </button>
          <button className="hifi-guide-btn-secondary flex items-center gap-1" style={{ height: "24px", fontSize: "10px" }} onClick={handleDownload}>
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
