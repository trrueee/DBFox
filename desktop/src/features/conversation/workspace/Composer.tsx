import { Send, Square } from "lucide-react";
import { useState } from "react";

export function Composer({
  disabled,
  running,
  onSend,
  onCancel,
}: {
  disabled?: string | null;
  running: boolean;
  onSend: (text: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState("");
  const submit = () => {
    const text = value.trim();
    if (!text || disabled || running) return;
    setValue("");
    onSend(text);
  };
  return (
    <footer className="conv-composer">
      <div className="conv-composer-box">
        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder={disabled || "Continue asking..."}
          disabled={Boolean(disabled)}
        />
        {running ? (
          <button type="button" onClick={onCancel} title="Cancel">
            <Square size={16} />
          </button>
        ) : (
          <button type="button" onClick={submit} title="Send">
            <Send size={16} />
          </button>
        )}
      </div>
    </footer>
  );
}
