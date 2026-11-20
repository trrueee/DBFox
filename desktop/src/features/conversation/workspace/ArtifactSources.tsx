import { BookOpenIcon, CaretDownIcon } from "@/components/icons";
import { ReferenceCard } from "../../../components/resources/ReferenceCard";
import { artifactKind } from "../../../components/resources/resourcePresentation";
import { Sources, SourcesContent, SourcesTrigger } from "../../../components/ai-elements/sources";
import type { ConversationArtifact } from "../../../types/conversation";

/** Source collection only; each inline evidence occurrence keeps its own identity. */
export function ArtifactSources({ artifacts, kind = "evidence", onSelectArtifact }: {
  artifacts: readonly ConversationArtifact[];
  kind?: "evidence" | "saved";
  onSelectArtifact?: (artifactId: string) => void;
}) {
  if (!artifacts.length) return null;
  const label = kind === "evidence" ? "引用来源" : "已保存结果";
  return <Sources className="conv-data-refs" data-reference-kind={kind}>
    <SourcesTrigger count={artifacts.length} aria-label={`${label}，${artifacts.length} 项`}>
      <BookOpenIcon size={16} aria-hidden="true" />
      <span className="conv-data-refs-label">{label}</span>
      <span className="conv-data-refs-count">{artifacts.length}</span>
      <CaretDownIcon className="dbfox-sources__chevron" size={16} aria-hidden="true" />
    </SourcesTrigger>
    <SourcesContent className="conv-data-ref-list">
      {artifacts.map(artifact => <ReferenceCard key={artifact.id} name={artifact.title}
        kind={artifactKind(artifact.type, artifact.title)} description={artifact.summary ?? undefined}
        onOpen={onSelectArtifact ? () => onSelectArtifact(artifact.id) : undefined} />)}
    </SourcesContent>
  </Sources>;
}
