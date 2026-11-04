import { LoaderCircle, MessageSquare } from "lucide-react";
import { useState, type ReactNode } from "react";

import type { WorkbenchReference } from "../../types/workspace";
import { useConversationStore } from "../../stores/conversationStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { AskInputBox } from "./smartQuery/AskInputBox";
import "./SmartQueryHome.css";
import { conversationTitle } from "../conversation/conversationTitle";
import { Alert, AlertDescription, Button } from "../../components/ui";
import { getUserErrorMessage } from "../../lib/api/client";

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
  const [recentError, setRecentError] = useState<{ id: string; error: unknown } | null>(null);
  const [openingId, setOpeningId] = useState<string | null>(null);
  const summaries = useConversationStore((state) => state.summaries);
  const openConversation = useConversationStore((state) => state.openConversation);
  const openConversationCenter = useWorkspaceStore((state) => state.openConversationCenter);
  const recentWork = summaries
    .filter((item) => item.project_id === projectId)
    .slice(0, 4);

  const openRecent = async (id: string) => {
    setRecentError(null);
    setOpeningId(id);
    try {
      await openConversation(id);
      if (useWorkspaceStore.getState().activeProjectId === projectId) openConversationCenter(id);
    } catch (error) { setRecentError({ id, error }); }
    finally { setOpeningId(null); }
  };

  return (
    <div className="smart-query-home">
      <div className="smart-query-home__content">
        <header className="smart-query-home__heading">
          <h1>今天要完成什么？</h1>
          <p>描述目标，或添加文件开始。</p>
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

        {recentWork.length > 0 ? <section className="smart-query-home__recent" aria-labelledby="recent-work-title">
          <div className="smart-query-home__recent-header">
            <h2 id="recent-work-title">最近工作</h2>
          </div>
            <div className="smart-query-home__recent-list">
              {recentWork.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  className="smart-query-home__recent-row"
                  disabled={openingId !== null}
                  aria-busy={openingId === item.id || undefined}
                  title={item.title}
                  onClick={() => void openRecent(item.id)}
                >
                  {openingId === item.id ? <LoaderCircle size={16} className="dbfox-composer__loading" aria-hidden="true" /> : <MessageSquare size={16} aria-hidden="true" />}
                  <span className="smart-query-home__recent-copy">
                    <strong>{conversationTitle(item.title)}</strong>
                    {item.last_message ? <small>{item.last_message}</small> : null}
                  </span>
                  <time className="smart-query-home__recent-time" dateTime={item.updated_at ?? undefined}>
                    {formatRecentTime(item.updated_at)}
                  </time>
                </button>
              ))}
            </div>
          {recentError ? <Alert variant="destructive"><AlertDescription>
            {getUserErrorMessage(recentError.error, "无法打开这项工作。")}
            <Button type="button" variant="ghost" size="sm" onClick={() => void openRecent(recentError.id)}>重试打开</Button>
          </AlertDescription></Alert> : null}
        </section> : null}
      </div>
    </div>
  );
}

function formatRecentTime(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
}
