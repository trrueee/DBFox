import { BookOpen, Braces, ChevronDown, Database, Table2 } from "lucide-react";
import {
  Sources,
  SourcesContent,
  SourcesTrigger,
} from "../../../components/ai-elements/sources";
import type { ConversationArtifact } from "../../../types/conversation";
import {
  buildDataReferences,
  referenceKey,
  referenceTitle,
  type DataReference,
} from "./dataReferences";

interface DataReferencePanelProps {
  artifacts: ConversationArtifact[];
  kind?: "evidence" | "saved";
  onSelectArtifact?: (artifactId: string) => void;
}

export function DataReferencePanel({
  artifacts,
  kind = "evidence",
  onSelectArtifact,
}: DataReferencePanelProps) {
  const references = buildDataReferences(artifacts);
  if (references.length === 0) return null;
  const label = kind === "evidence" ? "引用的数据来源" : "已保存结果";

  return (
    <Sources className="conv-data-refs" data-reference-kind={kind}>
      <SourcesTrigger count={references.length} aria-label={`${label}，${references.length} 项`}>
        <BookOpen size={14} aria-hidden="true" />
        <span className="conv-data-refs-label">{label}</span>
        <span className="conv-data-refs-count">{references.length}</span>
        <ChevronDown className="dbfox-sources__chevron" size={14} aria-hidden="true" />
      </SourcesTrigger>
      <SourcesContent className="conv-data-ref-list">
        {references.map((reference) => {
          const content = (
            <>
              {referenceIcon(reference.type)}
              <span>{reference.label}</span>
            </>
          );
          const className = `conv-data-ref conv-data-ref-${reference.type}`;
          const title = referenceTitle(reference);
          if ("artifactId" in reference && reference.artifactId && onSelectArtifact) {
            return (
              <button
                key={referenceKey(reference)}
                type="button"
                className={className}
                onClick={() => onSelectArtifact(reference.artifactId!)}
                title={title}
              >
                {content}
              </button>
            );
          }
          return (
            <span key={referenceKey(reference)} className={className} title={title}>
              {content}
            </span>
          );
        })}
      </SourcesContent>
    </Sources>
  );
}

function referenceIcon(type: DataReference["type"]) {
  if (type === "table") return <Database size={14} aria-hidden="true" />;
  if (type === "column") return <Braces size={14} aria-hidden="true" />;
  return <Table2 size={14} aria-hidden="true" />;
}
