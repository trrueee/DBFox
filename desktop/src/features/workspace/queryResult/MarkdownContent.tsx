import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import { createContext, useContext, type ReactNode } from "react";
import { Portal as TooltipPortal } from "@radix-ui/react-tooltip";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../../../components/ui/tooltip";
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
  id?: string;
  artifact_id: string;
  label?: string;
  locator?: Record<string, unknown>;
}

interface ArtifactEmbedComponentProps {
  "data-artifact-id"?: string;
}

function shortCitationLabel(label: string): string {
  return label.length > 24 || /[\n*#]/.test(label) ? "数据来源" : label;
}

// The renderer types stay stable while their callbacks/metadata change. Inline
// function components here would remount focused links and embedded views.
const MarkdownRenderingContext = createContext<{
  citations: MarkdownCitation[];
  renderCitation: (citation: MarkdownCitation, index: number) => ReactNode;
  renderArtifact?: (artifactId: string) => ReactNode;
} | null>(null);

function MarkdownLink({ children, href }: { children?: ReactNode; href?: string }) {
  const context = useContext(MarkdownRenderingContext);
  if (!context) throw new Error("Markdown links require their rendering context");
  const prefix = "#dbfox-citation:";
  if (href?.startsWith(prefix)) {
    const index = Number(href.slice(prefix.length));
    const citation = context.citations[index];
    return citation ? context.renderCitation(citation, index) : <span>〔来源不可用〕</span>;
  }
  return <a href={href} className="hifi-md-link" target="_blank" rel="noopener noreferrer">{children}</a>;
}

function MarkdownArtifactEmbed(properties: ArtifactEmbedComponentProps) {
  const context = useContext(MarkdownRenderingContext);
  if (!context) throw new Error("Markdown artifacts require their rendering context");
  const artifactId = String(properties["data-artifact-id"] ?? "");
  return <div className="hifi-md-artifact-embed" data-artifact-id={artifactId}>{context.renderArtifact?.(artifactId)}</div>;
}

const MARKDOWN_COMPONENTS = {
  ...BASE_MARKDOWN_COMPONENTS,
  a: MarkdownLink,
  "dbfox-artifact-embed": MarkdownArtifactEmbed,
} as Components;

export function MarkdownContent({
  content,
  streaming = false,
  className = "",
  citations = [],
  artifactRefs = [],
  onCitation,
  onEvidence,
  renderArtifact,
  artifacts = [],
}: {
  content: string;
  streaming?: boolean;
  className?: string;
  citations?: MarkdownCitation[];
  artifactRefs?: Array<{ artifact_id: string }>;
  onCitation?: (artifactId: string) => void;
  onEvidence?: (evidenceId: string) => void;
  renderArtifact?: (artifactId: string) => ReactNode;
  artifacts?: readonly Pick<ConversationArtifact, "id" | "type" | "title">[];
}) {
  const allowedArtifactEmbeds = artifactRefs.map((item) => item.artifact_id);
  const unreferencedCitations = citations.filter(
    (citation) => !content.includes(`{{cite:${citation.artifact_id}}}`),
  );
  const renderCitation = (citation: MarkdownCitation, index: number) => {
    const artifact = artifacts.find(item => item.id === citation.artifact_id);
    const label = artifact?.title || citation.label || "关联成果";
    const href = citation.id ? `#dbfox-evidence:${encodeURIComponent(citation.id)}` : `#dbfox-artifact:${encodeURIComponent(citation.artifact_id)}`;
    return <Tooltip key={citation.id ?? `${citation.artifact_id}-${index}`}>
      <TooltipTrigger asChild>
        <a href={href} className="hifi-md-citation" data-evidence-id={citation.id} aria-label={`查看证据：${label}`}
          onClick={event => {
            event.preventDefault();
            if (citation.id && onEvidence) onEvidence(citation.id);
            else onCitation?.(citation.artifact_id);
          }}>
          <ResourceIcon name={artifact?.title} kind={artifact ? artifactKind(artifact.type, artifact.title) : "document"} size={14} />
          <span className="hifi-md-citation__label">{artifact?.title || shortCitationLabel(label)}</span>
          <sup className="hifi-md-citation__index">{index + 1}</sup>
        </a>
      </TooltipTrigger>
      <TooltipPortal><TooltipContent className="hifi-md-citation-preview" side="top">
        <strong>{label}</strong>
        {citation.label && citation.label !== label ? <span>{citation.label}</span> : null}
        <small>在工作台查看来源</small>
      </TooltipContent></TooltipPortal>
    </Tooltip>;
  };
  return (
    <MarkdownRenderingContext.Provider value={{ citations, renderCitation, renderArtifact }}>
    <TooltipProvider delayDuration={350}><div className={`hifi-markdown-content ${className}`.trim()}>
      <ReactMarkdown
        components={MARKDOWN_COMPONENTS}
        remarkPlugins={[
          remarkGfm,
          remarkSafeBreaks,
          [remarkDbfoxCitations, { citations, allowedArtifactEmbeds, streaming }],
        ]}
        rehypePlugins={[[rehypeSanitize, DBFOX_MARKDOWN_SCHEMA]]}
      >
        {content}
      </ReactMarkdown>
      {unreferencedCitations.length > 0 && (
        <nav className="hifi-md-sources" aria-label="回答证据">
          <span>证据</span>
          {unreferencedCitations.map(citation => renderCitation(citation, citations.indexOf(citation)))}
        </nav>
      )}
    </div></TooltipProvider>
    </MarkdownRenderingContext.Provider>
  );
}
