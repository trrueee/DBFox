import { useState, type ReactNode } from "react";
import type { WorkbenchReference } from "../../../types/workspace";
import type { ConversationDeliveryMode } from "../../../types/conversation";
import { UnifiedComposer } from "../../../components/agent/UnifiedComposer";
import { useAttachmentInput } from "../useAttachmentInput";
import { openWorkbenchReference } from "../../resources/openWorkbenchReference";
import { getUserErrorMessage } from "../../../lib/api/client";

export function Composer({
  disabled,
  running,
  submitting = false,
  cancelling = false,
  error,
  onSend,
  onCancel,
  references,
  onRemoveReference,
  onClearReferences,
  conversationId,
  context,
}: {
  disabled?: string | null;
  running: boolean;
  submitting?: boolean;
  cancelling?: boolean;
  error?: unknown;
  onSend: (
    text: string,
    mode: ConversationDeliveryMode,
    references: readonly WorkbenchReference[],
  ) => Promise<void>;
  onCancel: () => Promise<void>;
  references?: readonly WorkbenchReference[];
  onRemoveReference?: (reference: WorkbenchReference) => void;
  onClearReferences?: () => void;
  conversationId?: string;
  context?: ReactNode;
}) {
  const [value, setValue] = useState("");
  const [previewError, setPreviewError] = useState<string | undefined>();
  const attachment = useAttachmentInput(async () => {
    if (!conversationId) throw new Error("当前会话不可用。");
    return conversationId;
  }, references ?? []);
  const [deliveryMode, setDeliveryMode] = useState<ConversationDeliveryMode>("queue");
  const submit = async () => {
    const text = value.trim();
    if (!text || disabled || submitting || attachment.busy) return;
    try {
      await onSend(
        text,
        running ? deliveryMode : "queue",
        references ?? [],
      );
      setValue("");
      onClearReferences?.();
    } catch {
      // The mutation exposes a user-facing error; preserve the draft for retry.
    }
  };
  return (
    <footer className="conv-composer" aria-label="对话输入区">
      <div className="conv-composer-rail">
        <UnifiedComposer
          value={value}
          onChange={setValue}
          context={context}
          onSubmit={submit}
          placeholder="继续追问…"
          ariaLabel="继续提问"
          references={references}
          onRemoveReference={(ref) => { attachment.remove(ref, conversationId); onRemoveReference?.(ref); }}
          onOpenReference={(ref) => {
              try { openWorkbenchReference(ref, conversationId); setPreviewError(undefined); }
              catch (error) { setPreviewError(getUserErrorMessage(error, "文件暂不可预览。")); }
          }}
          onAddAttachment={conversationId ? () => { setPreviewError(undefined); void attachment.add(); } : undefined}
          attachmentBusy={attachment.busy}
          attachmentError={previewError ?? attachment.error}
          onRetryAttachment={attachment.retryable ? () => void attachment.retry() : undefined}
          running={running}
          submitting={submitting}
          cancelling={cancelling}
          disabled={disabled}
          error={error}
          deliveryMode={deliveryMode}
          onDeliveryModeChange={setDeliveryMode}
          onCancel={() => onCancel().catch(() => undefined)}
        />
      </div>
    </footer>
  );
}
