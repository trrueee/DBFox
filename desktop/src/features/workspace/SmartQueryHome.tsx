import { MessageSquare } from "lucide-react";
import type { ReactNode } from "react";

import type { WorkbenchReference } from "../../types/workspace";
import { useConversationStore } from "../../stores/conversationStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";
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
}

export function SmartQueryHome({
  askInputValue,
  onAskInputChange,
  onSubmitAsk,
  projectId,
  references,
  onRemoveReference,
  feedback,
}: SmartQueryHomeProps) {
  const summaries = useConversationStore((state) => state.summaries);
  const openConversation = useConversationStore((state) => state.openConversation);
  const openConversationCenter = useWorkspaceStore((state) => state.openConversationCenter);
  const recentWork = summaries
    .filter((item) => item.project_id === projectId)
    .slice(0, 4);

  return (
    <div className="smart-query-home">
      <div className="smart-query-home__content">
        <header className="smart-query-home__heading">
          <h1>今天要完成什么？</h1>
          <p>描述你想完成的事。</p>
        </header>

        <AskInputBox
          value={askInputValue}
          onChange={onAskInputChange}
          onSubmit={onSubmitAsk}
          projectId={projectId}
          references={references}
          onRemoveReference={onRemoveReference}
        />

        {feedback}

        <section className="smart-query-home__recent" aria-labelledby="recent-work-title">
          <div className="smart-query-home__recent-header">
            <h2 id="recent-work-title">最近工作</h2>
          </div>
          {recentWork.length ? (
            <div className="smart-query-home__recent-list">
              {recentWork.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  className="smart-query-home__recent-row"
                  onClick={() => {
                    void openConversation(item.id).then(() => openConversationCenter(item.id));
                  }}
                >
                  <MessageSquare size={16} aria-hidden="true" />
                  <span className="smart-query-home__recent-copy">
                    <strong>{item.title || "未命名任务"}</strong>
                    <small>{item.last_message || "继续这项工作"}</small>
                  </span>
                  <time className="smart-query-home__recent-time" dateTime={item.updated_at ?? undefined}>
                    {formatRecentTime(item.updated_at)}
                  </time>
                </button>
              ))}
            </div>
          ) : (
            <p className="smart-query-home__empty">完成的工作会出现在这里。</p>
          )}
        </section>
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
