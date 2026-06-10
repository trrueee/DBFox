import type { MarkdownArtifact } from "../../../types/agentArtifact";

export function MarkdownArtifactView({ artifact }: { artifact: MarkdownArtifact }) {
  return (
    <div className="hifi-ai-card">
      <div className="hifi-ai-card-header">{artifact.title}</div>
      <div className="hifi-ai-card-body p-3">
        {artifact.description && <p className="text-[10px] text-slate-500 mb-2">{artifact.description}</p>}
        <p className="text-[10px] leading-relaxed text-slate-700 whitespace-pre-wrap">{artifact.content}</p>
      </div>
    </div>
  );
}
