import { useState } from "react";
import type { AgentWorkspaceContext } from "./types";

interface AgentComposerProps {
  disabled?: boolean;
  placeholder?: string;
  workspaceContext?: AgentWorkspaceContext | null;
  onSubmit: (question: string, workspaceContext?: AgentWorkspaceContext | null) => void;
}

export function AgentComposer({ disabled, placeholder = "Ask DataBox...", workspaceContext, onSubmit }: AgentComposerProps) {
  const [question, setQuestion] = useState("");
  const [focused, setFocused] = useState(false);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 8 }}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const trimmed = question.trim();
          if (!trimmed) return;
          onSubmit(trimmed, workspaceContext);
          setQuestion("");
        }}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "6px 10px",
          background: "var(--bg-secondary)",
          border: focused ? "1px solid var(--accent-primary)" : "1px solid var(--border-medium)",
          borderRadius: 8,
          boxShadow: focused ? "0 0 0 2px var(--accent-primary-light)" : "none",
          transition: "border-color 0.15s, box-shadow 0.15s",
        }}
      >
        <span style={{ fontSize: "0.8rem", color: focused ? "var(--accent-primary)" : "var(--text-muted)" }}>
          ✨
        </span>
        <input
          value={question}
          disabled={disabled}
          placeholder={placeholder}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onChange={(event) => setQuestion(event.target.value)}
          style={{
            flex: 1,
            minWidth: 0,
            border: "none",
            outline: "none",
            background: "transparent",
            fontFamily: "var(--font-body)",
            fontSize: "0.76rem",
            color: "var(--text-primary)",
            padding: "2px 0",
          }}
        />
        <button
          className="btn-primary"
          disabled={disabled || !question.trim()}
          style={{
            fontSize: "0.68rem",
            padding: "4px 10px",
            borderRadius: 6,
            height: 24,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          Ask
        </button>
      </form>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: "0.58rem",
          color: "var(--text-muted)",
          padding: "0 4px",
        }}
      >
        <span>Tip: Use <strong>@</strong> to mention tables, <strong>/</strong> for commands</span>
        {question.trim().length > 0 && (
          <span>{question.trim().length} chars</span>
        )}
      </div>
    </div>
  );
}
