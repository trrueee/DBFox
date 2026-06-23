import { ArrowUp, Square } from "lucide-react";
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
    <footer className="conv-composer" aria-label="对话输入区">
      <form
        className="conv-composer-rail"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <div className="conv-composer-card">
          <textarea
            aria-label="继续提问"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder={disabled || "Continue asking..."}
            disabled={Boolean(disabled)}
            rows={2}
          />
          <div className="conv-composer-toolbar">
            <span className="conv-composer-spacer" aria-hidden="true" />
            {running ? (
              <button
                type="button"
                className="conv-composer-submit is-pausing"
                onClick={onCancel}
                aria-label="暂停生成"
                title="暂停生成"
              >
                <Square size={13} fill="currentColor" />
              </button>
            ) : (
              <button
                type="submit"
                className="conv-composer-submit"
                aria-label="发送"
                title="发送"
                disabled={Boolean(disabled)}
              >
                <ArrowUp size={18} />
              </button>
            )}
          </div>
        </div>
      </form>
    </footer>
  );
}
