import { Copy, Download } from "lucide-react";
import { Button } from "../../../components/ui";
import { ArtifactCard } from "./ArtifactCard";
import { SqlCodeBlock } from "./SqlCodeBlock";
import { copyText, downloadTextFile } from "./artifactActions";
import "./ArtifactViews.css";

export interface CodeArtifactViewProps {
  title: string;
  code: string;
  language?: "sql" | "text";
  badge?: string;
  description?: string;
  metadata?: readonly string[];
  fileName: string;
  mimeType?: string;
  ariaLabel?: string;
  onToast: (message: string) => void;
}

export function CodeArtifactView({
  title,
  code,
  language = "text",
  badge = language.toUpperCase(),
  description,
  metadata = [],
  fileName,
  mimeType = "text/plain;charset=utf-8",
  ariaLabel = `${title} ${badge}`,
  onToast,
}: CodeArtifactViewProps) {
  const handleCopy = async () => {
    const ok = await copyText(code);
    onToast(ok ? `已复制 ${badge}` : "复制失败，请手动选择复制");
  };

  const handleDownload = () => {
    const ok = downloadTextFile(fileName, code, mimeType);
    onToast(ok ? `已下载 ${badge} 文件` : `${badge} 下载失败`);
  };

  return (
    <ArtifactCard
      title={title}
      badge={badge}
      tone={language === "sql" ? "sql" : "insight"}
      description={description}
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
            <Copy size={14} />
            复制 SQL
          </Button>
          <Button type="button" variant="outline" size="sm" className="artifact-action-button" onClick={handleDownload}>
            <Download size={14} />
            下载
          </Button>
        </>
      }
    >
      {language === "sql" ? (
        <div className="sql-artifact__editor">
          <SqlCodeBlock sql={code} ariaLabel={ariaLabel} />
        </div>
      ) : (
        <pre className="sql-code-block" aria-label={ariaLabel} tabIndex={0}><code>{code}</code></pre>
      )}
    </ArtifactCard>
  );
}
