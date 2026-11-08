import type { ReactNode } from "react";

import type { WorkbenchReference } from "../../types/workspace";
import { AskInputBox } from "./smartQuery/AskInputBox";
import "./SmartQueryHome.css";

interface SmartQueryHomeProps {
  askInputValue: string;
  onAskInputChange: (value: string) => void;
  onSubmitAsk: () => void;
  projectId?: string;
  references?: readonly WorkbenchReference[];
  onRemoveReference?: (reference: WorkbenchReference) => void;
  feedback?: ReactNode;
  onAddAttachment?: () => void;
  onOpenReference?: (reference: WorkbenchReference) => void;
  attachmentBusy?: boolean;
  submitting?: boolean;
  attachmentError?: string;
  onRetryAttachment?: () => void;
  context?: ReactNode;
}

export function SmartQueryHome({
  askInputValue,
  onAskInputChange,
  onSubmitAsk,
  projectId,
  references,
  onRemoveReference,
  feedback,
  onAddAttachment, onOpenReference, attachmentBusy, attachmentError, onRetryAttachment,
  context, submitting,
}: SmartQueryHomeProps) {
  return (
    <div className="smart-query-home">
      <div className="smart-query-home__content">
        <header className="smart-query-home__heading">
          <h1>今天要完成什么？</h1>
        </header>

        <AskInputBox
          value={askInputValue}
          onChange={onAskInputChange}
          onSubmit={onSubmitAsk}
          projectId={projectId}
          context={context}
          submitting={submitting}
          references={references}
          onRemoveReference={onRemoveReference}
          onOpenReference={onOpenReference}
          onAddAttachment={onAddAttachment}
          attachmentBusy={attachmentBusy}
          attachmentError={attachmentError}
          onRetryAttachment={onRetryAttachment}
        />

        {feedback}
      </div>
    </div>
  );
}
