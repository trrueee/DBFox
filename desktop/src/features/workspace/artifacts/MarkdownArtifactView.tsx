import { Copy } from "lucide-react";
import type { MarkdownArtifact } from "../../../types/agentArtifact";
import { copyText } from "./artifactActions";

interface MarkdownArtifactViewProps {
  artifact: MarkdownArtifact;
  onToast: (message: string) => void;
}

export function MarkdownArtifactView({ artifact, onToast }: MarkdownArtifactViewProps) {
  const handleCopy = async () => {
    const ok = await copyText(artifact.content);
    onToast(ok ? "已复制结论" : "复制失败，请手动选择复制");
  };

  return (
    <div className="hifi-ai-card">
      <div className="hifi-ai-card-header flex items-center justify-between gap-2">
        <span>{artifact.title}</span>
        <span className="hifi-guide-chip-prod">MARKDOWN</span>
      </div>
      <div className="hifi-ai-card-body p-3">
        {artifact.description && <p className="text-[10px] text-slate-500 mb-2">{artifact.description}</p>}
        <p className="text-[10px] leading-relaxed text-slate-700 whitespace-pre-wrap">{artifact.content}</p>
        <div className="flex justify-end mt-3">
          <button className="hifi-guide-btn-secondary flex items-center gap-1" style={{ height: "24px", fontSize: "10px" }} onClick={handleCopy}>
            <Copy size={10} />
            复制结论
          </button>
        </div>
      </div>
    </div>
  );
}
