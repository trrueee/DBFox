import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import type { ReactNode } from "react";
import { remarkDbfoxCitations } from "./remarkDbfoxCitations";
import { remarkSafeBreaks } from "./remarkSafeBreaks";
import "./MarkdownContent.css";
import { artifactKind, ResourceIcon } from "../../../components/resources/resourcePresentation";
import type { ConversationArtifact } from "../../../types/conversation";

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

const DBFOX_MARKDOWN_SCHEMA = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames ?? []), "dbfox-artifact-embed"],
  attributes: {
    ...defaultSchema.attributes,
    "dbfox-artifact-embed": ["dataArtifactId"],
  },
};

interface MarkdownCitation {
  artifact_id: string;
  label?: string;
}

interface ArtifactEmbedComponentProps {
  "data-artifact-id"?: string;
}

function shortCitationLabel(label: string): string {
  return label.length > 24 || /[\n*#]/.test(label) ? "数据来源" : label;
}

export function MarkdownContent({
  content,
  className = "",
  citations = [],
  artifactRefs = [],
  onCitation,
  renderArtifact,
  artifacts = [],
}: {
  content: string;
  className?: string;
  citations?: MarkdownCitation[];
  artifactRefs?: Array<{ artifact_id: string }>;
  onCitation?: (artifactId: string) => void;
  renderArtifact?: (artifactId: string) => ReactNode;
  artifacts?: readonly Pick<ConversationArtifact, "id" | "type" | "title">[];
}) {
  const citationIndex = new Map<string, number>();
  for (const citation of citations) {
    if (!citationIndex.has(citation.artifact_id)) citationIndex.set(citation.artifact_id, citationIndex.size + 1);
  }
  const artifactOrder = Array.from(citationIndex.keys());
  const allowedArtifactEmbeds = artifactRefs.map((item) => item.artifact_id);
  const unreferencedCitations = citations.filter(
    (citation) => !content.includes(`{{cite:${citation.artifact_id}}}`),
  );
  const components = {
    ...BASE_MARKDOWN_COMPONENTS,
    a: ({ children, href }) => {
      const prefix = "#dbfox-artifact:";
      if (href?.startsWith(prefix)) {
        const artifactId = decodeURIComponent(href.slice(prefix.length));
        const citation = citations.find((item) => item.artifact_id === artifactId);
        const artifact = artifacts.find(item => item.id === artifactId);
        const label = artifact?.title || citation?.label || "关联成果";
        return (
          <button
            type="button"
            className="hifi-md-citation"
            aria-label={`查看证据：${label}`}
            title={label}
            onClick={() => onCitation?.(artifactId)}
          >
            <ResourceIcon name={artifact?.title} kind={artifact ? artifactKind(artifact.type, artifact.title) : "document"} size={14} />
            <span className="hifi-md-citation__label">{artifact?.title || shortCitationLabel(label)}</span>
            <span className="hifi-md-citation__index">{children}</span>
          </button>
        );
      }
      return <a href={href} className="hifi-md-link" target="_blank" rel="noopener noreferrer">{children}</a>;
    },
    "dbfox-artifact-embed": (properties: ArtifactEmbedComponentProps) => {
      const artifactId = String(properties["data-artifact-id"] ?? "");
      return (
        <div className="hifi-md-artifact-embed" data-artifact-id={artifactId}>
          {renderArtifact?.(artifactId)}
        </div>
      );
    },
  } as Components;
  return (
    <div className={`hifi-markdown-content ${className}`.trim()}>
      <ReactMarkdown
        components={components}
        remarkPlugins={[
          remarkGfm,
          remarkSafeBreaks,
          [remarkDbfoxCitations, { artifactOrder, allowedArtifactEmbeds }],
        ]}
        rehypePlugins={[[rehypeSanitize, DBFOX_MARKDOWN_SCHEMA]]}
      >
        {content}
      </ReactMarkdown>
      {unreferencedCitations.length > 0 && (
        <nav className="hifi-md-sources" aria-label="回答证据">
          <span>证据</span>
          {unreferencedCitations.map((citation) => {
            const artifact = artifacts.find(item => item.id === citation.artifact_id);
            const label = artifact?.title || citation.label || "关联成果";
            return (
            <button
              key={citation.artifact_id}
              type="button"
              onClick={() => onCitation?.(citation.artifact_id)}
              className="hifi-md-citation"
              title={label}
              aria-label={`查看证据：${label}`}
            >
              <ResourceIcon name={artifact?.title} kind={artifact ? artifactKind(artifact.type, artifact.title) : "document"} size={14} />
              <span className="hifi-md-citation__label">{artifact?.title || shortCitationLabel(label)}</span>
              <span className="hifi-md-citation__index">{citationIndex.get(citation.artifact_id)}</span>
            </button>
            );
          })}
        </nav>
      )}
    </div>
  );
}
