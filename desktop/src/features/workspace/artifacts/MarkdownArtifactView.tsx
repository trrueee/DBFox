import { Copy } from "lucide-react";
import ReactMarkdown from "react-markdown";
import type { MarkdownArtifact } from "../../../types/agentArtifact";
import { copyText } from "./artifactActions";

interface MarkdownArtifactViewProps {
  artifact: MarkdownArtifact;
  onToast: (message: string) => void;
}

const MARKDOWN_COMPONENTS = {
  h1: ({ children }: any) => <h3 className="text-[13px] font-bold text-slate-800 mt-3 mb-1">{children}</h3>,
  h2: ({ children }: any) => <h4 className="text-[12px] font-semibold text-slate-700 mt-2 mb-1">{children}</h4>,
  h3: ({ children }: any) => <h5 className="text-[11px] font-semibold text-slate-600 mt-2 mb-1">{children}</h5>,
  p: ({ children }: any) => <p className="text-[11px] leading-relaxed text-slate-700 my-1">{children}</p>,
  ul: ({ children }: any) => <ul className="list-disc pl-4 text-[11px] text-slate-700 space-y-0.5 my-1">{children}</ul>,
  ol: ({ children }: any) => <ol className="list-decimal pl-4 text-[11px] text-slate-700 space-y-0.5 my-1">{children}</ol>,
  li: ({ children }: any) => <li className="text-[11px]">{children}</li>,
  strong: ({ children }: any) => <strong className="font-semibold text-slate-800">{children}</strong>,
  em: ({ children }: any) => <em className="italic">{children}</em>,
  code: ({ children }: any) => <code className="bg-slate-100 text-[10px] px-1 py-0.5 rounded font-mono text-slate-700">{children}</code>,
  pre: ({ children }: any) => <pre className="bg-slate-50 border border-slate-200 rounded p-2 text-[10px] font-mono text-slate-700 overflow-auto my-2">{children}</pre>,
  a: ({ children, href }: any) => <a href={href} className="text-indigo-600 underline" target="_blank" rel="noopener">{children}</a>,
  blockquote: ({ children }: any) => <blockquote className="border-l-2 border-slate-300 pl-3 text-[10px] text-slate-500 italic my-2">{children}</blockquote>,
};

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
        <div className="hifi-markdown-content">
          <ReactMarkdown components={MARKDOWN_COMPONENTS}>
            {artifact.content}
          </ReactMarkdown>
        </div>
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
