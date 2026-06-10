import { Copy } from "lucide-react";
import type { MarkdownArtifact } from "../../../types/agentArtifact";
import { copyText } from "./artifactActions";

export function MarkdownArtifactView({ artifact }: { artifact: MarkdownArtifact }) {
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
          <button className="hifi-guide-btn-secondary flex items-center gap-1" style={{ height: "24px", fontSize: "10px" }} onClick={() => copyText(artifact.content)}>
            <Copy size={10} />
            复制结论
          </button>
        </div>
      </div>
    </div>
  );
}
