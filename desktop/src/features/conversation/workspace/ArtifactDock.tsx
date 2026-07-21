import { BarChart3, CheckCircle2, Code2, FileText, PanelRightClose, ShieldCheck, Table2 } from "lucide-react";
import { useMemo } from "react";
import type { ResultViewArtifact } from "../../../types/agentArtifact";
import type { ConversationArtifact } from "../../../types/conversation";
import { safetyCheckLabel } from "../../../lib/presentation";
import { DeferredChartArtifactView } from "../../workspace/artifacts/DeferredChartArtifactView";
import { MarkdownArtifactView } from "../../workspace/artifacts/MarkdownArtifactView";
import { SqlCodeBlock } from "../../workspace/artifacts/SqlCodeBlock";
import { SqlArtifactView } from "../../workspace/artifacts/SqlArtifactView";
import { TableArtifactView } from "../../workspace/artifacts/TableArtifactView";
import {
  conversationSqlText,
  isSqlBackedResultViewArtifact,
  payloadBoolean,
  safetyGuardrailResult,
  safetySchemaWarningsCount,
  sortConversationArtifacts,
  toChartArtifactModel,
  toMarkdownArtifactModel,
  toSqlArtifactModel,
  toResultViewArtifactModel,
} from "./conversationArtifactModels";

interface ArtifactDockProps {
  artifacts: ConversationArtifact[];
  selectedArtifactId?: string | null;
  onSelectArtifact?: (artifactId: string) => void;
  onOpenSqlConsole: (sql?: string) => void;
  onOpenResultTab?: (artifact: ResultViewArtifact) => void;
  onCollapse?: () => void;
}

type DockKind = "sql" | "safety" | "result" | "chart" | "note";

export function ArtifactDock({
  artifacts,
  selectedArtifactId,
  onSelectArtifact,
  onOpenSqlConsole,
  onOpenResultTab,
  onCollapse,
}: ArtifactDockProps) {
  const orderedArtifacts = useMemo(
    () => sortConversationArtifacts(artifacts).filter(isDockArtifact),
    [artifacts],
  );
  const activeArtifact = orderedArtifacts.find((artifact) => artifact.id === selectedArtifactId);

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
              onOpenSqlConsole={onOpenSqlConsole}
              onOpenResultTab={onOpenResultTab}
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
    artifact.type === "sql" ||
    artifact.type === "sql_suggestion" ||
    artifact.type === "safety" ||
    isSqlBackedResultViewArtifact(artifact) ||
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
  if (isSqlBackedResultViewArtifact(artifact)) return "result";
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
  onOpenResultTab?: (artifact: ResultViewArtifact) => void;
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

  if (isSqlBackedResultViewArtifact(artifact)) {
    return (
      <TableArtifactView
        artifact={toResultViewArtifactModel(artifact)}
        onOpenResultTab={onOpenResultTab}
        onToast={() => undefined}
      />
    );
  }

  if (artifact.type === "chart") {
    return <DeferredChartArtifactView artifact={toChartArtifactModel(artifact)} onToast={() => undefined} />;
  }

  if (artifact.type === "safety") {
    return <SafetyDockCard artifact={artifact} />;
  }

  return <MarkdownArtifactView artifact={toMarkdownArtifactModel(artifact)} onToast={() => undefined} />;
}

function SafetyDockCard({ artifact }: { artifact: ConversationArtifact }) {
  const canExecute = payloadBoolean(artifact.payload, ["canExecute"]);
  const requiresApproval = payloadBoolean(artifact.payload, ["requiresApproval"]);
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
        <span>{requiresApproval ? "需要批准" : "无需批准"}</span>
        <span>安全策略：{safetyCheckLabel(guardrail)}</span>
        <span>表结构提醒：{schemaWarnings}</span>
      </div>
      {sql && <SqlCodeBlock sql={sql} className="conv-dock-safety-sql" ariaLabel="安全检查 SQL" />}
    </section>
  );
}
