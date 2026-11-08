import {
  BookOpenIcon,
  CaretDownIcon,
} from "@/components/icons";
import { ReferenceCard } from "../../../components/resources/ReferenceCard";
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
        <BookOpenIcon size={16} aria-hidden="true" />
        <span className="conv-data-refs-label">{label}</span>
        <span className="conv-data-refs-count">{references.length}</span>
        <CaretDownIcon className="dbfox-sources__chevron" size={16} aria-hidden="true" />
      </SourcesTrigger>
      <SourcesContent className="conv-data-ref-list">
        {references.map((reference) => {
          return <ReferenceCard key={referenceKey(reference)} name={reference.label}
            kind={reference.type === "sql" ? "code" : "table"} description={referenceTitle(reference)}
            onOpen={"artifactId" in reference && reference.artifactId && onSelectArtifact ? () => onSelectArtifact(reference.artifactId) : undefined} />;
        })}
      </SourcesContent>
    </Sources>
  );
}
