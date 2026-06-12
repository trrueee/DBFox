import { useRef } from "react";
import { Send } from "lucide-react";

interface FollowUpInputProps {
  tabId: string;
  onSendFollowUp: (tabId: string, text: string) => void;
}

export function FollowUpInput({ tabId, onSendFollowUp }: FollowUpInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  const send = () => {
    const value = inputRef.current?.value.trim() || "";
    if (!value) return;
    onSendFollowUp(tabId, value);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div className="hifi-query-result-footer">
      <div className="hifi-chat-input-wrapper">
        <input
          ref={inputRef}
          type="text"
          className="hifi-chat-input"
          placeholder="继续提问..."
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              send();
            }
          }}
        />
        <button className="hifi-chat-send-btn" onClick={send} aria-label="发送追问" title="发送追问">
          <Send size={13} />
        </button>
      </div>
    </div>
  );
}
