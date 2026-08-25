import { ArrowUp, Square } from "lucide-react";
import { useState } from "react";
import type { WorkbenchReference } from "../../../../../sdk/frontend/index";
import type { ConversationDeliveryMode } from "../../../types/conversation";

export function Composer({
  disabled,
  running,
  submitting = false,
  cancelling = false,
  error,
  onSend,
  onCancel,
  reference,
  onClearReference,
}: {
  disabled?: string | null;
  running: boolean;
  submitting?: boolean;
  cancelling?: boolean;
  error?: string | null;
  onSend: (
    text: string,
    mode: ConversationDeliveryMode,
    references: readonly WorkbenchReference[],
  ) => Promise<void>;
  onCancel: () => Promise<void>;
  reference?: WorkbenchReference | null;
  onClearReference?: () => void;
}) {
  const [value, setValue] = useState("");
  const [deliveryMode, setDeliveryMode] = useState<ConversationDeliveryMode>("queue");
  const submit = async () => {
    const text = value.trim();
    if (!text || disabled || submitting) return;
    try {
      await onSend(
        text,
        running ? deliveryMode : "queue",
        reference ? [reference] : [],
      );
      setValue("");
      onClearReference?.();
    } catch {
      // The mutation exposes a user-facing error; preserve the draft for retry.
    }
  };
  return (
    <footer className="conv-composer" aria-label="对话输入区">
      <form
        className="conv-composer-rail"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <div className="conv-composer-card">
          {reference && (
            <div className="conv-composer-reference" aria-label="当前引用语境">
              <span className="conv-composer-reference__badge">
                {reference.object?.kind || reference.authority?.kind || "引用"}
              </span>
              <span className="conv-composer-reference__label">{reference.label}</span>
              {onClearReference && (
                <button
                  type="button"
                  className="conv-composer-reference__clear"
                  onClick={onClearReference}
                  aria-label="清除引用"
                >
                  ×
                </button>
              )}
            </div>
          )}
          <textarea
            aria-label="继续提问"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void submit();
              }
            }}
            placeholder={disabled || "继续追问…"}
            disabled={Boolean(disabled) || submitting}
            rows={2}
          />
          <div className="conv-composer-toolbar">
            <span className="conv-composer-spacer" aria-hidden="true" />
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
            ) : null}
            {running ? (
              <div className="conv-composer-running-actions">
                <button
                  type="button"
                  className="conv-composer-submit is-pausing"
                  onClick={() => void onCancel().catch(() => undefined)}
                  disabled={cancelling}
                  aria-label="停止当前任务"
                  title="停止当前任务"
                >
                  <Square size={13} fill="currentColor" />
                </button>
                <button
                  type="submit"
                  className="conv-composer-submit"
                  aria-label="发送"
                  title="发送"
                  disabled={submitting}
                >
                  <ArrowUp size={18} />
                </button>
              </div>
            ) : (
              <button
                type="submit"
                className="conv-composer-submit"
                aria-label="发送"
                title="发送"
                disabled={Boolean(disabled) || submitting}
              >
                <ArrowUp size={18} />
              </button>
            )}
          </div>
          {error && <p className="conv-action-error" role="alert">{error}</p>}
        </div>
      </form>
    </footer>
  );
}
