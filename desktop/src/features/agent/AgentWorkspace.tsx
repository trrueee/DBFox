import { useEffect, useState } from "react";
import { ArtifactInspector } from "./ArtifactInspector";
import { AgentComposer } from "./AgentComposer";
import { AgentNarrativeStream } from "./AgentNarrativeStream";
import { TraceDrawer } from "./TraceDrawer";
import type { AgentRunResponse, FollowUpSuggestion } from "./types";

interface AgentWorkspaceProps {
  result: AgentRunResponse;
  disabled?: boolean;
  onOpenSql?: (sql: string) => void;
  onAsk?: (question: string) => void;
  onSuggestion?: (suggestion: FollowUpSuggestion, result: AgentRunResponse) => void;
}

export function AgentWorkspace({ result, disabled, onOpenSql, onAsk, onSuggestion }: AgentWorkspaceProps) {
  const artifacts = result.artifacts || [];
  const events = result.events || [];
  const messageBlocks = result.message_blocks || [];
  const suggestions = result.suggestions || [];
  const [activeArtifactId, setActiveArtifactId] = useState(artifacts[0]?.id || "");

  useEffect(() => {
    setActiveArtifactId((current) => {
      if (current && artifacts.some((artifact) => artifact.id === current)) return current;
      return artifacts[0]?.id || "";
    });
  }, [result]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: "0.68rem", lineHeight: 1.45 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6 }}>
        <span className={`status-badge ${result.success ? "status-badge-success" : "status-badge-error"}`}>
          {result.success ? "Agent answer" : "Agent stopped"}
        </span>
        {result.error ? <span style={{ color: "var(--accent-red)", textAlign: "right" }}>{result.error}</span> : null}
      </div>

      <AgentNarrativeStream
        events={events}
        messageBlocks={messageBlocks}
        fallbackAnswer={result.answer}
        fallbackArtifacts={artifacts}
        fallbackSuggestions={suggestions}
        onOpenSql={onOpenSql}
        onOpenArtifact={setActiveArtifactId}
        onAsk={onAsk}
        onSuggestion={onSuggestion ? (suggestion) => onSuggestion(suggestion, result) : undefined}
      />

      <ArtifactInspector
        artifacts={artifacts}
        activeArtifactId={activeArtifactId}
        onActiveArtifactChange={setActiveArtifactId}
        onOpenSql={onOpenSql}
      />
      {onAsk ? (
        <AgentComposer
          disabled={disabled}
          placeholder="Ask a follow-up about this result"
          onSubmit={onAsk}
        />
      ) : null}
      <TraceDrawer steps={result.steps} traceEvents={result.trace_events || []} />
    </div>
  );
}
