import { useState } from "react";

interface AgentComposerProps {
  disabled?: boolean;
  placeholder?: string;
  onSubmit: (question: string) => void;
}

export function AgentComposer({ disabled, placeholder = "Ask a data question", onSubmit }: AgentComposerProps) {
  const [question, setQuestion] = useState("");

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        const trimmed = question.trim();
        if (!trimmed) return;
        onSubmit(trimmed);
        setQuestion("");
      }}
      style={{ display: "flex", gap: 6 }}
    >
      <input
        value={question}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(event) => setQuestion(event.target.value)}
        style={{ flex: 1, minWidth: 0 }}
      />
      <button className="btn-primary" disabled={disabled || !question.trim()} style={{ fontSize: "0.66rem" }}>
        Ask
      </button>
    </form>
  );
}
