import { BarChart3, CheckCircle2, Code2, FileText, ShieldCheck, Table2 } from "lucide-react";
import type { CSSProperties, KeyboardEvent, PointerEvent as ReactPointerEvent } from "react";
import { useCallback, useMemo, useRef, useState } from "react";
import type { TableArtifact, ResultViewArtifact } from "../../../types/agentArtifact";
import type { ConversationArtifact } from "../../../types/conversation";
import { ChartArtifactView } from "../../workspace/artifacts/ChartArtifactView";
import { MarkdownArtifactView } from "../../workspace/artifacts/MarkdownArtifactView";
import { SqlArtifactView } from "../../workspace/artifacts/SqlArtifactView";
import { TableArtifactView } from "../../workspace/artifacts/TableArtifactView";
import {
  conversationSqlText,
  payloadBoolean,
  safetyGuardrailResult,
  safetySchemaWarningsCount,
  sortConversationArtifacts,
  toChartArtifactModel,
  toMarkdownArtifactModel,
  toSqlArtifactModel,
  toTableArtifactModel,
} from "./conversationArtifactModels";

interface ArtifactDockProps {
  artifacts: ConversationArtifact[];
  selectedArtifactId?: string | null;
  onSelectArtifact?: (artifactId: string) => void;
  onOpenSqlConsole: (sql?: string) => void;
  onOpenResultTab?: (artifact: TableArtifact | ResultViewArtifact) => void;
}

type DockKind = "sql" | "safety" | "result" | "chart" | "note";

const MIN_DOCK_WIDTH = 340;
const DEFAULT_DOCK_WIDTH = 420;
const MAX_DOCK_WIDTH = 680;

type DockStyle = CSSProperties & {
  "--conv-artifact-width": string;
};

export function ArtifactDock({
  artifacts,
  selectedArtifactId,
  onSelectArtifact,
  onOpenSqlConsole,
  onOpenResultTab,
}: ArtifactDockProps) {
  const [dockWidth, setDockWidth] = useState(DEFAULT_DOCK_WIDTH);
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null);
  const orderedArtifacts = useMemo(
    () => sortConversationArtifacts(artifacts).filter(isDockArtifact),
    [artifacts],
  );
  const preferredArtifactId = useMemo(() => {
    const selected = orderedArtifacts.find((artifact) => artifact.id === selectedArtifactId);
    if (selected) return selected.id;
    const result = orderedArtifacts.find((artifact) => artifact.type === "result_view" || artifact.type === "table");
    return result?.id || orderedArtifacts[0]?.id || null;
  }, [orderedArtifacts, selectedArtifactId]);
  const [localSelectedId, setLocalSelectedId] = useState<string | null>(preferredArtifactId);
  const activeId = selectedArtifactId || localSelectedId || preferredArtifactId;
  const activeArtifact = orderedArtifacts.find((artifact) => artifact.id === activeId) || orderedArtifacts[0];

  const applyDockWidth = useCallback((value: number) => {
    setDockWidth(clampDockWidth(value));
  }, []);

  const handleResizePointerDown = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    dragRef.current = { startX: event.clientX, startWidth: dockWidth };

    const handlePointerMove = (moveEvent: PointerEvent) => {
      const dragState = dragRef.current;
      if (!dragState) return;
      applyDockWidth(dragState.startWidth + dragState.startX - moveEvent.clientX);
    };

    const handlePointerUp = () => {
      dragRef.current = null;
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
  }, [applyDockWidth, dockWidth]);

  const handleResizeKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 40 : 20;
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      applyDockWidth(dockWidth + step);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      applyDockWidth(dockWidth - step);
    } else if (event.key === "Home") {
      event.preventDefault();
      applyDockWidth(MIN_DOCK_WIDTH);
    } else if (event.key === "End") {
      event.preventDefault();
      applyDockWidth(MAX_DOCK_WIDTH);
    }
  };

  const dockStyle: DockStyle = {
    "--conv-artifact-width": `${dockWidth}px`,
  };

  if (orderedArtifacts.length === 0) return null;

  const handleSelect = (artifact: ConversationArtifact) => {
    setLocalSelectedId(artifact.id);
    onSelectArtifact?.(artifact.id);
  };

  return (
    <aside className="conv-artifact-dock" aria-label="Artifact dock" style={dockStyle}>
      <div
        role="separator"
        aria-label="调整工件区宽度"
        aria-orientation="vertical"
        aria-valuemin={MIN_DOCK_WIDTH}
        aria-valuemax={MAX_DOCK_WIDTH}
        aria-valuenow={dockWidth}
        className="conv-artifact-resizer"
        tabIndex={0}
        onPointerDown={handleResizePointerDown}
        onKeyDown={handleResizeKeyDown}
      />
      <header className="conv-artifact-dock-header">
        <div>
          <strong>产物</strong>
          <span>{orderedArtifacts.length} items</span>
        </div>
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
              onOpenSqlConsole={onOpenSqlConsole}
              onOpenResultTab={onOpenResultTab}
            />
          ) : (
            <div className="conv-artifact-dock-empty">暂无可查看产物</div>
          )}
        </section>
      </div>
    </aside>
  );
}

function clampDockWidth(value: number): number {
  return Math.min(MAX_DOCK_WIDTH, Math.max(MIN_DOCK_WIDTH, Math.round(value)));
}

function isDockArtifact(artifact: ConversationArtifact): boolean {
  return (
    artifact.type === "sql" ||
    artifact.type === "sql_suggestion" ||
    artifact.type === "safety" ||
    artifact.type === "table" ||
    artifact.type === "result_view" ||
    artifact.type === "chart" ||
    artifact.type === "markdown" ||
    artifact.type === "query_plan" ||
    artifact.type === "agent_plan" ||
    artifact.type === "error"
  );
}

function artifactKind(artifact: ConversationArtifact): DockKind {
  if (artifact.type === "sql" || artifact.type === "sql_suggestion") return "sql";
  if (artifact.type === "safety") return "safety";
  if (artifact.type === "table" || artifact.type === "result_view") return "result";
  if (artifact.type === "chart") return "chart";
  return "note";
}

function artifactKindLabel(kind: DockKind): string {
  if (kind === "sql") return "SQL";
  if (kind === "safety") return "Safety";
  if (kind === "result") return "Result";
  if (kind === "chart") return "Chart";
  return "Note";
}

function ArtifactIcon({ kind }: { kind: DockKind }) {
  if (kind === "sql") return <Code2 size={14} aria-hidden="true" />;
  if (kind === "safety") return <ShieldCheck size={14} aria-hidden="true" />;
  if (kind === "result") return <Table2 size={14} aria-hidden="true" />;
  if (kind === "chart") return <BarChart3 size={14} aria-hidden="true" />;
  return <FileText size={14} aria-hidden="true" />;
}

function DockArtifactPreview({
  artifact,
  onOpenSqlConsole,
  onOpenResultTab,
}: {
  artifact: ConversationArtifact;
  onOpenSqlConsole: (sql?: string) => void;
  onOpenResultTab?: (artifact: TableArtifact | ResultViewArtifact) => void;
}) {
  if (artifact.type === "sql" || artifact.type === "sql_suggestion") {
    return (
      <SqlArtifactView
        artifact={toSqlArtifactModel(artifact)}
        onOpenSqlConsole={onOpenSqlConsole}
        onToast={() => undefined}
      />
    );
  }

  if (artifact.type === "table" || artifact.type === "result_view") {
    return (
      <TableArtifactView
        artifact={toTableArtifactModel(artifact)}
        onOpenResultTab={onOpenResultTab}
        onToast={() => undefined}
      />
    );
  }

  if (artifact.type === "chart") {
    return <ChartArtifactView artifact={toChartArtifactModel(artifact)} onToast={() => undefined} />;
  }

  if (artifact.type === "safety") {
    return <SafetyDockCard artifact={artifact} />;
  }

  return <MarkdownArtifactView artifact={toMarkdownArtifactModel(artifact)} onToast={() => undefined} />;
}

function SafetyDockCard({ artifact }: { artifact: ConversationArtifact }) {
  const canExecute = payloadBoolean(artifact.payload, ["can_execute", "canExecute"]);
  const requiresConfirmation = payloadBoolean(artifact.payload, ["requires_confirmation", "requiresConfirmation"]);
  const passed = payloadBoolean(artifact.payload, ["passed"]) || canExecute;
  const guardrail = safetyGuardrailResult(artifact.payload);
  const schemaWarnings = safetySchemaWarningsCount(artifact.payload);
  const sql = conversationSqlText(artifact);

  return (
    <section className={`conv-dock-safety-card ${passed ? "is-safe" : "is-warning"}`}>
      <header>
        <CheckCircle2 size={16} />
        <div>
          <strong>安全检查</strong>
          <span>{passed ? "校验通过" : "需要处理"}</span>
        </div>
      </header>
      <div className="conv-dock-safety-grid">
        <span>{canExecute ? "可执行" : "不可执行"}</span>
        <span>{requiresConfirmation ? "需要确认" : "无需确认"}</span>
        <span>Guardrail: {guardrail}</span>
        <span>Schema warnings: {schemaWarnings}</span>
      </div>
      {sql && <pre>{sql}</pre>}
    </section>
  );
}
