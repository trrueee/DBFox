import type { FollowUpSuggestion } from "./types";

interface SuggestionChipsProps {
  suggestions: FollowUpSuggestion[];
  onAsk?: (question: string) => void;
  onSuggestion?: (suggestion: FollowUpSuggestion) => void;
}

export function SuggestionChips({ suggestions, onAsk, onSuggestion }: SuggestionChipsProps) {
  if (!suggestions.length) return null;

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {suggestions.map((suggestion) => (
        <button
          key={`${suggestion.action_type}-${suggestion.label}`}
          className="btn-secondary"
          onClick={() => onSuggestion ? onSuggestion(suggestion) : onAsk?.(suggestion.question)}
          title={suggestion.reason}
          style={{ fontSize: "0.64rem", padding: "3px 8px" }}
        >
          {suggestion.label}
        </button>
      ))}
    </div>
  );
}
