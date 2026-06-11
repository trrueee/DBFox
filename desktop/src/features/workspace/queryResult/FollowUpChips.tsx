import { ChevronRight } from "lucide-react";
import type { FollowUpSuggestion } from "../../../lib/api/types";

interface FollowUpChipsProps {
  suggestions: FollowUpSuggestion[];
  onSendFollowUp: (tabId: string, text: string) => void;
  tabId: string;
}

export function FollowUpChips({ suggestions, onSendFollowUp, tabId }: FollowUpChipsProps) {
  if (!suggestions || suggestions.length === 0) return null;

  const visible = suggestions.slice(0, 4);

  return (
    <div className="hifi-followup-chips">
      <span className="hifi-followup-label">你可能还想问：</span>
      <div className="hifi-followup-list">
        {visible.map((s, i) => (
          <button
            key={i}
            className="hifi-followup-chip"
            onClick={() => onSendFollowUp(tabId, s.question)}
          >
            <span>{s.question}</span>
            <ChevronRight size={11} />
          </button>
        ))}
      </div>
    </div>
  );
}
