import { Button } from "../../components/ui/button";
import type { FollowUpSuggestion } from "./types";

interface SuggestionChipsProps {
  suggestions: FollowUpSuggestion[];
  onAsk?: (question: string) => void;
  onSuggestion?: (suggestion: FollowUpSuggestion) => void;
}

export function SuggestionChips({ suggestions, onAsk, onSuggestion }: SuggestionChipsProps) {
  if (!suggestions.length) return null;

  return (
    <div className="flex flex-wrap gap-1.5">
      {suggestions.map((suggestion) => (
        <Button
          key={`${suggestion.action_type}-${suggestion.label}`}
          variant="outline"
          size="sm"
          onClick={() => onSuggestion ? onSuggestion(suggestion) : onAsk?.(suggestion.question)}
          title={suggestion.reason}
          className="text-[0.66rem] h-7"
        >
          {suggestion.label}
        </Button>
      ))}
    </div>
  );
}
