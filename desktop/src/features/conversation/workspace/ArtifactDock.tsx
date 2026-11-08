import {
  SidebarSimpleIcon,
} from "@/components/icons";
import { artifactKind, ResourceIcon, resourceLabel } from "../../../components/resources/resourcePresentation";
import { useMemo } from "react";
import type { ConversationArtifact } from "../../../types/conversation";
import { toArtifactEnvelope } from "../../workspace/artifacts/artifactEnvelope";
import { ArtifactViewHost } from "../../workspace/artifacts/ArtifactViewHost";
import { isPrimaryConversationArtifact, sortConversationArtifacts } from "./conversationArtifactSelectors";

interface ArtifactDockProps {
  artifacts: ConversationArtifact[];
  selectedArtifactId?: string | null;
  onSelectArtifact?: (artifactId: string) => void;
  onOpenArtifact?: (artifact: ConversationArtifact) => void;
  onCollapse?: () => void;
}

export function ArtifactDock({
  artifacts,
  selectedArtifactId,
  onSelectArtifact,
  onOpenArtifact,
  onCollapse,
}: ArtifactDockProps) {
  const orderedArtifacts = useMemo(
    () => sortConversationArtifacts(artifacts).filter(isPrimaryConversationArtifact),
    [artifacts],
  );
  const activeArtifact = orderedArtifacts.find((artifact) => artifact.id === selectedArtifactId)
    ?? orderedArtifacts.at(-1);

  if (orderedArtifacts.length === 0) return null;

  return (
    <aside className="conv-artifact-dock" aria-label="Artifact dock">
      <header className="conv-artifact-dock-header">
        <strong>成果</strong>
        {onCollapse && (
          <button type="button" onClick={onCollapse} aria-label="收起工件区" title="收起工件区">
            <SidebarSimpleIcon size={16} aria-hidden="true" />
          </button>
        )}
      </header>
      <div className="conv-artifact-dock-body">
        <nav className="conv-artifact-dock-list" aria-label="Artifact list">
          {orderedArtifacts.map((artifact) => (
            <button
              key={artifact.id}
              type="button"
              className="conv-artifact-dock-item"
              aria-label={`${artifact.title} ${artifactTypeLabel(artifact.type, artifact.title)}`}
              aria-pressed={activeArtifact?.id === artifact.id}
              onClick={() => onSelectArtifact?.(artifact.id)}
            >
              <ResourceIcon name={artifact.title} kind={artifactKind(artifact.type, artifact.title)} size={16} />
              <span>{artifact.title}</span>
              <em>{artifactTypeLabel(artifact.type, artifact.title)}</em>
            </button>
          ))}
        </nav>
        <section className="conv-artifact-dock-preview" aria-live="polite">
          {activeArtifact ? (
            <ArtifactViewHost
              artifact={toArtifactEnvelope(activeArtifact)}
              surface="inline"
              onToast={() => undefined}
              resolveArtifact={(artifactId) => {
                const resolved = artifacts.find((candidate) => candidate.id === artifactId);
                return resolved ? toArtifactEnvelope(resolved) : null;
              }}
              openArtifact={(envelope) => {
                const resolved = artifacts.find((candidate) => candidate.id === envelope.id);
                if (resolved) onOpenArtifact?.(resolved);
              }}
            />
          ) : (
            <div className="conv-artifact-dock-empty">选择成果查看详情</div>
          )}
        </section>
      </div>
    </aside>
  );
}

function artifactTypeLabel(type: string, title: string): string {
  return resourceLabel(artifactKind(type, title));
}
