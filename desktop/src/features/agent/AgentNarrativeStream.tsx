import { InlineChartBlock } from "./blocks/InlineChartBlock";
import { InlineSafetyBlock } from "./blocks/InlineSafetyBlock";
import { InlineSqlBlock } from "./blocks/InlineSqlBlock";
import { InlineTableBlock } from "./blocks/InlineTableBlock";
import { ErrorArtifactView } from "./artifacts/ErrorArtifactView";
import { InsightArtifactView } from "./artifacts/InsightArtifactView";
import { SuggestionChips } from "./SuggestionChips";
import { TextBlock } from "./blocks/TextBlock";
import type { AgentAnswer, AgentArtifact, AgentMessageBlock, AgentVisibleEvent, FollowUpSuggestion } from "./types";

interface AgentNarrativeStreamProps {
  events: AgentVisibleEvent[];
  messageBlocks?: AgentMessageBlock[];
  fallbackAnswer?: AgentAnswer | null;
  fallbackArtifacts?: AgentArtifact[];
  fallbackSuggestions?: FollowUpSuggestion[];
  onOpenSql?: (sql: string) => void;
  onOpenArtifact?: (artifactId: string) => void;
  onAsk?: (question: string) => void;
  onSuggestion?: (suggestion: FollowUpSuggestion) => void;
}

export function AgentNarrativeStream({
  events,
  messageBlocks = [],
  fallbackAnswer,
  fallbackArtifacts = [],
  fallbackSuggestions = [],
  onOpenSql,
  onOpenArtifact,
  onAsk,
  onSuggestion,
}: AgentNarrativeStreamProps) {
  const visibleEvents = events.length ? events : fallbackEvents(fallbackAnswer, fallbackArtifacts, fallbackSuggestions);

  if (messageBlocks.length) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {messageBlocks.map((block, index) => (
          <NarrativeBlock
            key={block.block_id || `${block.type}-${index}`}
            block={block}
            artifacts={fallbackArtifacts}
            onOpenSql={onOpenSql}
            onOpenArtifact={onOpenArtifact}
            onAsk={onAsk}
            onSuggestion={onSuggestion}
          />
        ))}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {visibleEvents.map((event, index) => (
        <NarrativeEvent
          key={`${event.type}-${index}`}
          event={event}
          onOpenSql={onOpenSql}
          onOpenArtifact={onOpenArtifact}
          onAsk={onAsk}
          onSuggestion={onSuggestion}
        />
      ))}
    </div>
  );
}

function NarrativeBlock({
  block,
  artifacts,
  onOpenSql,
  onOpenArtifact,
  onAsk,
  onSuggestion,
}: {
  block: AgentMessageBlock;
  artifacts: AgentArtifact[];
  onOpenSql?: (sql: string) => void;
  onOpenArtifact?: (artifactId: string) => void;
  onAsk?: (question: string) => void;
  onSuggestion?: (suggestion: FollowUpSuggestion) => void;
}) {
  if (block.type === "text") {
    return block.content ? <TextBlock content={block.content} /> : null;
  }
  if (block.type === "artifact_ref" && block.artifact_id) {
    const artifact = artifacts.find((item) => item.id === block.artifact_id);
    return artifact ? <ArtifactBlock artifact={artifact} onOpenSql={onOpenSql} onOpenArtifact={onOpenArtifact} /> : null;
  }
  if (block.type === "answer" && block.answer) {
    return <AnswerBlock answer={block.answer} onOpenArtifact={onOpenArtifact} />;
  }
  if (block.type === "suggestions") {
    return <SuggestionChips suggestions={block.suggestions || []} onAsk={onAsk} onSuggestion={onSuggestion} />;
  }
  return null;
}

function NarrativeEvent({
  event,
  onOpenSql,
  onOpenArtifact,
  onAsk,
  onSuggestion,
}: {
  event: AgentVisibleEvent;
  onOpenSql?: (sql: string) => void;
  onOpenArtifact?: (artifactId: string) => void;
  onAsk?: (question: string) => void;
  onSuggestion?: (suggestion: FollowUpSuggestion) => void;
}) {
  if (event.type === "agent.narration.completed" || event.type === "agent.narration.delta") {
    return event.content ? <TextBlock content={event.content} /> : null;
  }
  if (event.type === "agent.artifact.created" && event.artifact) {
    return <ArtifactBlock artifact={event.artifact} onOpenSql={onOpenSql} onOpenArtifact={onOpenArtifact} />;
  }
  if (event.type === "agent.answer.completed" && event.answer) {
    return <AnswerBlock answer={event.answer} onOpenArtifact={onOpenArtifact} />;
  }
  if (event.type === "agent.suggestions.created") {
    return <SuggestionChips suggestions={event.suggestions || []} onAsk={onAsk} onSuggestion={onSuggestion} />;
  }
  return null;
}

function ArtifactBlock({
  artifact,
  onOpenSql,
  onOpenArtifact,
}: {
  artifact: AgentArtifact;
  onOpenSql?: (sql: string) => void;
  onOpenArtifact?: (artifactId: string) => void;
}) {
  const artifactView = (() => {
    if (artifact.type === "table") return <InlineTableBlock artifact={artifact} />;
    if (artifact.type === "chart") return <InlineChartBlock artifact={artifact} />;
    if (artifact.type === "sql") return <InlineSqlBlock artifact={artifact} onOpenSql={onOpenSql} />;
    if (artifact.type === "safety") return <InlineSafetyBlock artifact={artifact} />;
    if (artifact.type === "insight") return <InsightArtifactView artifact={artifact} />;
    if (artifact.type === "recommendation") {
      const recommendations = Array.isArray(artifact.payload.recommendations)
        ? artifact.payload.recommendations.map(String)
        : [];
      return recommendations.length ? <TextBlock content={recommendations.join("\n")} /> : null;
    }
    if (artifact.type === "error") return <ErrorArtifactView artifact={artifact} />;
    return null;
  })();

  if (!artifactView) return null;

  return (
    <div>
      {artifactView}
      {onOpenArtifact && artifact.presentation.mode !== "hidden" ? (
        <button
          className="btn-secondary"
          onClick={() => onOpenArtifact(artifact.id)}
          style={{ marginTop: 5, fontSize: "0.62rem", padding: "2px 7px" }}
        >
          Inspect evidence
        </button>
      ) : null}
    </div>
  );
}

function AnswerBlock({ answer, onOpenArtifact }: { answer: AgentAnswer; onOpenArtifact?: (artifactId: string) => void }) {
  const evidenceItems = answer.evidence.filter((item) => item.artifact_id);

  return (
    <section style={{ padding: 8, background: "var(--bg-secondary)" }}>
      <strong>Answer</strong>
      <div style={{ marginTop: 5, lineHeight: 1.55 }}>{answer.answer}</div>
      {answer.key_findings.length ? (
        <ul style={{ margin: "6px 0 0", paddingLeft: 16 }}>
          {answer.key_findings.map((finding) => <li key={finding}>{finding}</li>)}
        </ul>
      ) : null}
      {answer.caveats.length ? (
        <div style={{ marginTop: 6, color: "var(--text-muted)" }}>Caveats: {answer.caveats.join(" | ")}</div>
      ) : null}
      {evidenceItems.length ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 7 }}>
          {evidenceItems.map((item) => {
            const label = `${item.label}${item.value !== null && item.value !== undefined ? `: ${item.value}` : ""}`;
            return onOpenArtifact ? (
              <button
                key={`${item.artifact_id}-${item.label}`}
                className="status-badge status-badge-neutral"
                onClick={() => onOpenArtifact(item.artifact_id)}
                title={`Open ${item.artifact_id} in inspector`}
                style={{ border: "none", cursor: "pointer" }}
              >
                {label}
              </button>
            ) : (
              <span
                key={`${item.artifact_id}-${item.label}`}
                className="status-badge status-badge-neutral"
                title={item.artifact_id}
              >
                {label}
              </span>
            );
          })}
        </div>
      ) : null}
      {answer.recommendations.length ? (
        <div style={{ marginTop: 7 }}>
          <strong style={{ fontSize: "0.64rem" }}>Recommendations</strong>
          <ul style={{ margin: "4px 0 0", paddingLeft: 16 }}>
            {answer.recommendations.map((recommendation) => <li key={recommendation}>{recommendation}</li>)}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function fallbackEvents(
  answer?: AgentAnswer | null,
  artifacts: AgentArtifact[] = [],
  suggestions: FollowUpSuggestion[] = [],
): AgentVisibleEvent[] {
  const events: AgentVisibleEvent[] = [];
  for (const artifact of artifacts.filter((item) => item.presentation.mode === "inline" || item.presentation.mode === "both")) {
    events.push({ type: "agent.artifact.created", artifact });
  }
  if (answer) events.push({ type: "agent.answer.completed", answer });
  if (suggestions.length) events.push({ type: "agent.suggestions.created", suggestions });
  return events;
}
