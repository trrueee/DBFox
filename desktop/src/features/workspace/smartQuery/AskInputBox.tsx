import { UnifiedComposer } from "../../../components/agent/UnifiedComposer";
import type { WorkbenchReference } from "../../../types/workspace";
import type { ReactNode } from "react";

interface AskInputBoxProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  projectId?: string;
  context?: ReactNode;
  references?: readonly WorkbenchReference[];
  onRemoveReference?: (reference: WorkbenchReference) => void;
  onOpenReference?: (reference: WorkbenchReference) => void;
  onAddAttachment?: () => void;
  attachmentBusy?: boolean;
  submitting?: boolean;
  attachmentError?: string;
  onRetryAttachment?: () => void;
}

export function AskInputBox({
  value,
  onChange,
  onSubmit,
  context, submitting,
  references,
  onRemoveReference,
  onOpenReference, onAddAttachment, attachmentBusy, attachmentError, onRetryAttachment,
}: AskInputBoxProps) {
  return (
    <UnifiedComposer
      value={value}
      onChange={onChange}
      onSubmit={onSubmit}
      context={context}
      submitting={submitting}
      placeholder=""
      ariaLabel="新任务"
      references={references}
      onRemoveReference={onRemoveReference}
      onOpenReference={onOpenReference}
      onAddAttachment={onAddAttachment}
      attachmentBusy={attachmentBusy}
      attachmentError={attachmentError}
      onRetryAttachment={onRetryAttachment}
      autoFocus
    />
  );
}
