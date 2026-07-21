import { ArrowUp, Square } from "lucide-react";
import { useState } from "react";
import type { ConversationDeliveryMode } from "../../../types/conversation";

export function Composer({
  disabled,
  running,
  onSend,
  onCancel,
}: {
  disabled?: string | null;
  running: boolean;
  onSend: (text: string, mode: ConversationDeliveryMode) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState("");
  const [deliveryMode, setDeliveryMode] = useState<ConversationDeliveryMode>("queue");
  const submit = () => {
    const text = value.trim();
    if (!text || disabled) return;
    setValue("");
    onSend(text, running ? deliveryMode : "queue");
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
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
            placeholder={disabled || "继续追问…"}
            disabled={Boolean(disabled)}
            rows={2}
          />
          <div className="conv-composer-toolbar">
            {running ? (
              <label className="conv-delivery-control">
                <span>发送方式</span>
                <select
                  aria-label="发送方式"
                  value={deliveryMode}
                  onChange={(event) => setDeliveryMode(event.target.value as ConversationDeliveryMode)}
                >
                  <option value="queue">排队执行</option>
                  <option value="steer">补充当前任务</option>
                  <option value="cancel_and_replace">停止并改做此任务</option>
                </select>
              </label>
            ) : <span className="conv-composer-spacer" aria-hidden="true" />}
            {running ? (
              <div className="conv-composer-running-actions">
                <button
                  type="button"
                  className="conv-composer-submit is-pausing"
                  onClick={onCancel}
                  aria-label="停止当前任务"
                  title="停止当前任务"
                >
                  <Square size={13} fill="currentColor" />
                </button>
                <button type="submit" className="conv-composer-submit" aria-label="发送" title="发送">
                  <ArrowUp size={18} />
                </button>
              </div>
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
