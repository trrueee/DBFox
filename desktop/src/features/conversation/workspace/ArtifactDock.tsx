import { BarChart3, FileText, PanelRightClose, Table2 } from "lucide-react";
import { useMemo } from "react";
import type { ResultViewArtifact, SqlArtifact } from "../../../types/agentArtifact";
import type { ConversationArtifact } from "../../../types/conversation";
import { DeferredChartArtifactView } from "../../workspace/artifacts/DeferredChartArtifactView";
import { MarkdownArtifactView } from "../../workspace/artifacts/MarkdownArtifactView";
import { TableArtifactView } from "../../workspace/artifacts/TableArtifactView";
import {
  isPrimaryConversationArtifact,
  isSqlConversationArtifact,
  isSqlBackedResultViewArtifact,
  sortConversationArtifacts,
  toChartArtifactModel,
  toMarkdownArtifactModel,
  toResultViewArtifactModel,
  toSqlArtifactModel,
} from "./conversationArtifactModels";

interface ArtifactDockProps {
  artifacts: ConversationArtifact[];
  selectedArtifactId?: string | null;
  onSelectArtifact?: (artifactId: string) => void;
  onOpenResultTab?: (artifact: ResultViewArtifact) => void;
  onOpenSqlConsole?: (sql?: string) => void;
  onCollapse?: () => void;
}

type DockKind = "result" | "chart" | "note";

export function ArtifactDock({
  artifacts,
  selectedArtifactId,
  onSelectArtifact,
  onOpenResultTab,
  onOpenSqlConsole,
  onCollapse,
}: ArtifactDockProps) {
  const orderedArtifacts = useMemo(
    () => sortConversationArtifacts(artifacts).filter(isPrimaryConversationArtifact).filter(isDockArtifact),
    [artifacts],
  );
  const activeArtifact = orderedArtifacts.find((artifact) => artifact.id === selectedArtifactId)
    || orderedArtifacts.at(-1);

  if (orderedArtifacts.length === 0) return null;

  const handleSelect = (artifact: ConversationArtifact) => {
    onSelectArtifact?.(artifact.id);
  };

  return (
    <aside className="conv-artifact-dock" aria-label="Artifact dock">
      <header className="conv-artifact-dock-header">
        <strong>工件</strong>
        {onCollapse && (
          <button type="button" onClick={onCollapse} aria-label="收起工件区" title="收起工件区">
            <PanelRightClose size={15} aria-hidden="true" />
          </button>
        )}
      </header>
      <div className="conv-artifact-dock-body">
        <nav className="conv-artifact-dock-list" aria-label="Artifact list">
          {orderedArtifacts.map((artifact) => {
            const kind = artifactKind(artifact);
            const kindLabel = artifactKindLabel(kind);
            return (
              <button
                key={artifact.id}
                type="button"
                className="conv-artifact-dock-item"
                aria-label={`${artifact.title} ${kindLabel}`}
                aria-pressed={activeArtifact?.id === artifact.id}
                onClick={() => handleSelect(artifact)}
              >
                <ArtifactIcon kind={kind} />
                <span>{artifact.title}</span>
                <em>{kindLabel}</em>
              </button>
            );
          })}
        </nav>
        <section className="conv-artifact-dock-preview" aria-live="polite">
          {activeArtifact ? (
            <DockArtifactPreview
              artifact={activeArtifact}
              artifacts={artifacts}
              onOpenResultTab={onOpenResultTab}
              onOpenSqlConsole={onOpenSqlConsole}
            />
          ) : (
            <div className="conv-artifact-dock-empty">选择一个工件查看详情</div>
          )}
        </section>
      </div>
    </aside>
  );
}

function isDockArtifact(artifact: ConversationArtifact): boolean {
  return (
    isSqlBackedResultViewArtifact(artifact) ||
    artifact.type === "chart" ||
    artifact.type === "markdown"
  );
}

function artifactKind(artifact: ConversationArtifact): DockKind {
  if (isSqlBackedResultViewArtifact(artifact)) return "result";
  if (artifact.type === "chart") return "chart";
  return "note";
}

function artifactKindLabel(kind: DockKind): string {
  if (kind === "result") return "Result";
  if (kind === "chart") return "Chart";
  return "Note";
}

function ArtifactIcon({ kind }: { kind: DockKind }) {
  if (kind === "result") return <Table2 size={14} aria-hidden="true" />;
  if (kind === "chart") return <BarChart3 size={14} aria-hidden="true" />;
  return <FileText size={14} aria-hidden="true" />;
}

function DockArtifactPreview({
  artifact,
  artifacts,
  onOpenResultTab,
  onOpenSqlConsole,
}: {
  artifact: ConversationArtifact;
  artifacts: ConversationArtifact[];
  onOpenResultTab?: (artifact: ResultViewArtifact) => void;
  onOpenSqlConsole?: (sql?: string) => void;
}) {
  if (isSqlBackedResultViewArtifact(artifact)) {
    const resultArtifact = toResultViewArtifactModel(artifact);
    const sourceSqlArtifact = resolveSourceSqlArtifact(resultArtifact, artifacts);
    return (
      <TableArtifactView
        artifact={resultArtifact}
        sourceSqlArtifact={sourceSqlArtifact}
        onOpenResultTab={onOpenResultTab}
        onOpenSqlConsole={onOpenSqlConsole}
        onToast={() => undefined}
      />
    );
  }

  if (artifact.type === "chart") {
    return <DeferredChartArtifactView artifact={toChartArtifactModel(artifact)} onToast={() => undefined} />;
  }

  return <MarkdownArtifactView artifact={toMarkdownArtifactModel(artifact)} onToast={() => undefined} />;
}

function resolveSourceSqlArtifact(
  resultArtifact: ResultViewArtifact,
  artifacts: ConversationArtifact[],
): SqlArtifact | undefined {
  if (!resultArtifact.sourceSqlArtifactId) return undefined;
  const source = artifacts.find((candidate) => (
    candidate.id === resultArtifact.sourceSqlArtifactId && isSqlConversationArtifact(candidate)
  ));
  if (!source) return undefined;
  const model = toSqlArtifactModel(source);
  return model.sql.trim() ? model : undefined;
}
