import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { remarkDbfoxCitations } from "./remarkDbfoxCitations";
import { remarkSafeBreaks } from "./remarkSafeBreaks";
import "./MarkdownContent.css";

const BASE_MARKDOWN_COMPONENTS: Components = {
  h1: ({ children }) => <h1 className="hifi-md-h1">{children}</h1>,
  h2: ({ children }) => <h2 className="hifi-md-h2">{children}</h2>,
  h3: ({ children }) => <h3 className="hifi-md-h3">{children}</h3>,
  p: ({ children }) => <p className="hifi-md-p">{children}</p>,
  ul: ({ children }) => <ul className="hifi-md-ul">{children}</ul>,
  ol: ({ children }) => <ol className="hifi-md-ol">{children}</ol>,
  li: ({ children }) => <li className="hifi-md-li">{children}</li>,
  strong: ({ children }) => <strong className="hifi-md-strong">{children}</strong>,
  em: ({ children }) => <em className="hifi-md-em">{children}</em>,
  code: ({ children }) => <code className="hifi-md-code">{children}</code>,
  pre: ({ children }) => <pre className="hifi-md-pre">{children}</pre>,
  blockquote: ({ children }) => <blockquote className="hifi-md-quote">{children}</blockquote>,
  table: ({ children }) => <div className="hifi-md-table-wrap"><table className="hifi-md-table">{children}</table></div>,
  img: () => null,
};

interface MarkdownCitation {
  artifact_id: string;
  label?: string;
}

export function MarkdownContent({
  content,
  className = "",
  citations = [],
  onCitation,
}: {
  content: string;
  className?: string;
  citations?: MarkdownCitation[];
  onCitation?: (artifactId: string) => void;
}) {
  const citationIndex = new Map<string, number>();
  for (const citation of citations) {
    if (!citationIndex.has(citation.artifact_id)) citationIndex.set(citation.artifact_id, citationIndex.size + 1);
  }
  const artifactOrder = Array.from(citationIndex.keys());
  const unreferencedCitations = citations.filter(
    (citation) => !content.includes(`{{cite:${citation.artifact_id}}}`),
  );
  const components: Components = {
    ...BASE_MARKDOWN_COMPONENTS,
    a: ({ children, href }) => {
      const prefix = "#dbfox-artifact:";
      if (href?.startsWith(prefix)) {
        const artifactId = decodeURIComponent(href.slice(prefix.length));
        const citation = citations.find((item) => item.artifact_id === artifactId);
        return (
          <button
            type="button"
            className="hifi-md-citation"
            aria-label={`查看证据：${citation?.label || artifactId}`}
            title={citation?.label || "查看关联数据工件"}
            onClick={() => onCitation?.(artifactId)}
          >
            {children}
          </button>
        );
      }
      return <a href={href} className="hifi-md-link" target="_blank" rel="noopener noreferrer">{children}</a>;
    },
  };
  return (
    <div className={`hifi-markdown-content ${className}`.trim()}>
      <ReactMarkdown
        components={components}
        remarkPlugins={[remarkGfm, remarkSafeBreaks, [remarkDbfoxCitations, { artifactOrder }]]}
        rehypePlugins={[rehypeSanitize]}
      >
        {content}
      </ReactMarkdown>
      {unreferencedCitations.length > 0 && (
        <nav className="hifi-md-sources" aria-label="回答证据">
          <span>证据</span>
          {unreferencedCitations.map((citation) => (
            <button
              key={citation.artifact_id}
              type="button"
              onClick={() => onCitation?.(citation.artifact_id)}
              aria-label={`查看证据：${citation.label || citation.artifact_id}`}
            >
              [{citationIndex.get(citation.artifact_id)}] {citation.label || "数据工件"}
            </button>
          ))}
        </nav>
      )}
    </div>
  );
}
