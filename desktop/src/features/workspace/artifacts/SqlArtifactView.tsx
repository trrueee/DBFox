import { Copy, Download, Terminal } from "lucide-react";
import { Button } from "../../../components/ui";
import type { SqlArtifact } from "../../../types/agentArtifact";
import { ArtifactCard } from "./ArtifactCard";
import { SqlCodeBlock } from "./SqlCodeBlock";
import { copyText, downloadTextFile } from "./artifactActions";
import "./ArtifactViews.css";

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
    <ArtifactCard
      title={artifact.title}
      badge="SQL"
      tone="sql"
      description={artifact.description}
      meta={
        metadata.length > 0
          ? metadata.map((item) => (
              <span key={item} className="artifact-pill">{item}</span>
            ))
          : undefined
      }
      actions={
        <>
          <Button type="button" variant="outline" size="sm" className="artifact-action-button" onClick={handleCopy}>
            <Copy size={10} />
            复制 SQL
          </Button>
          <Button type="button" variant="outline" size="sm" className="artifact-action-button" onClick={handleDownload}>
            <Download size={10} />
            下载
          </Button>
          <Button type="button" variant="outline" size="sm" className="artifact-action-button" onClick={openInSqlConsole}>
            <Terminal size={10} />
            在 SQL 工作台打开
          </Button>
        </>
      }
    >
      <div className="sql-artifact__editor">
        <SqlCodeBlock sql={artifact.sql} ariaLabel={`${artifact.title} SQL`} />
      </div>
    </ArtifactCard>
  );
}
