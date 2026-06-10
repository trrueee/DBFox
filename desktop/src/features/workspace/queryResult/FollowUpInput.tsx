import { Send } from "lucide-react";

interface FollowUpInputProps {
  tabId: string;
  onSendFollowUp: (tabId: string, text: string) => void;
}

export function FollowUpInput({ tabId, onSendFollowUp }: FollowUpInputProps) {
  return (
    <div className="hifi-query-result-footer">
      <div className="hifi-chat-input-wrapper">
        <input
          type="text"
          className="hifi-chat-input"
          placeholder="针对此问数结果继续追问..."
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              onSendFollowUp(tabId, (event.target as HTMLInputElement).value);
              (event.target as HTMLInputElement).value = "";
            }
          }}
        />
        <button className="hifi-chat-send-btn"><Send size={13} /></button>
      </div>
    </div>
  );
}
