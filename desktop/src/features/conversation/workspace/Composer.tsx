import { useState } from "react";
import type { WorkbenchReference } from "../../../types/workspace";
import type { ConversationDeliveryMode } from "../../../types/conversation";
import { UnifiedComposer } from "../../../components/agent/UnifiedComposer";

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
          onSubmit={submit}
          placeholder="继续追问…"
          ariaLabel="继续提问"
          references={references}
          onRemoveReference={onRemoveReference}
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
