import { Copy } from "lucide-react";
import type { MarkdownArtifact } from "../../../types/agentArtifact";
import { MarkdownContent } from "../queryResult/MarkdownContent";
import { copyText } from "./artifactActions";

interface MarkdownArtifactViewProps {
  artifact: MarkdownArtifact;
  onToast: (message: string) => void;
}

export function MarkdownArtifactView({ artifact, onToast }: MarkdownArtifactViewProps) {
  const handleCopy = async () => {
    const ok = await copyText(artifact.content);
    onToast(ok ? "已复制" : "复制失败");
  };

  return (
    <div className="hifi-ai-card hifi-markdown-card mt-2">
      <div className="hifi-ai-card-header flex items-center justify-between gap-2">
        <span>{artifact.title}</span>
        <span className="hifi-artifact-chip hifi-artifact-chip-insight">分析</span>
      </div>
      <div className="hifi-ai-card-body p-3">
        {artifact.description && <p className="text-[10px] text-slate-500 mb-2">{artifact.description}</p>}
        <MarkdownContent content={artifact.content} />
        <div className="flex justify-end mt-3">
          <button className="hifi-guide-btn-secondary flex items-center gap-1" style={{ height: "24px", fontSize: "10px" }} onClick={handleCopy}>
            <Copy size={10} />
            复制
          </button>
        </div>
      </div>
    </div>
  );
}
