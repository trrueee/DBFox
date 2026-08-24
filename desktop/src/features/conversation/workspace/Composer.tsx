import { ArrowUp, Square } from "lucide-react";
import { useState } from "react";
import type { RequestedResourceRef } from "../../../lib/api/generated/types.gen";
import type { ConversationDeliveryMode } from "../../../types/conversation";
import { ResourceContextPicker } from "../ResourceContextPicker";

export function Composer({
  disabled,
  running,
  submitting = false,
  cancelling = false,
  error,
  onSend,
  onCancel,
  projectId = "",
  resourceIntents = [],
  onResourceIntentsChange,
  updatingResourceIntents = false,
  resourceIntentError,
  requestedResources = [],
  onRequestedResourcesChange,
}: {
  disabled?: string | null;
  running: boolean;
  submitting?: boolean;
  cancelling?: boolean;
  error?: string | null;
  onSend: (
    text: string,
    mode: ConversationDeliveryMode,
    requestedResources: readonly RequestedResourceRef[],
  ) => Promise<void>;
  onCancel: () => Promise<void>;
  projectId?: string;
  resourceIntents?: readonly RequestedResourceRef[];
  onResourceIntentsChange?: (next: RequestedResourceRef[]) => Promise<void>;
  updatingResourceIntents?: boolean;
  resourceIntentError?: string | null;
  requestedResources?: readonly RequestedResourceRef[];
  onRequestedResourcesChange?: (next: RequestedResourceRef[]) => void;
}) {
  const [value, setValue] = useState("");
  const [deliveryMode, setDeliveryMode] = useState<ConversationDeliveryMode>("queue");
  const submit = async () => {
    const text = value.trim();
    if (!text || disabled || submitting) return;
    try {
      await onSend(text, running ? deliveryMode : "queue", requestedResources);
      setValue("");
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
            {requestedResources.length > 0 && (
              <div className="resource-context-picker__chips" aria-label="本次消息上下文">
                {requestedResources.map((ref) => (
                  <span className="resource-context-chip" key={`${ref.kind}:${ref.id}`}>
                    <span aria-hidden="true">♪</span>
                    <span>{ref.kind === "dbfox.music.library" ? "Music Library" : ref.id}</span>
                    <button
                      type="button"
                      onClick={() => onRequestedResourcesChange?.(
                        requestedResources.filter(
                          (candidate) => candidate.kind !== ref.kind || candidate.id !== ref.id,
                        ),
                      )}
                      aria-label={`从本次消息移除 ${ref.id}`}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
            {projectId && onResourceIntentsChange && (
              <ResourceContextPicker
                projectId={projectId}
                selected={resourceIntents}
                onChange={onResourceIntentsChange}
                disabled={updatingResourceIntents}
                error={resourceIntentError}
              />
            )}
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
