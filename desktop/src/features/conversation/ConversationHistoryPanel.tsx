import { useState } from "react";
import { ChevronDown, ChevronRight, ChevronUp, Database, MessageSquare, Trash2 } from "lucide-react";
import { Button, EmptyState } from "../../components/ui";
import { WorkspaceShell } from "../appShell/WorkspaceShell";
import type { ConversationSummary } from "../../types/conversation";
import "./ConversationHistoryPanel.css";

interface ConversationHistoryPanelProps {
  conversations: ConversationSummary[];
  datasourceLabels?: Record<string, string>;
  activeConversationId?: string;
  onOpenConversation: (conversation: ConversationSummary) => void;
  onDeleteConversation: (conversationId: string) => void;
}

const DEFAULT_VISIBLE_CONVERSATIONS = 6;

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export function ConversationHistoryPanel({
  conversations,
  datasourceLabels = {},
  activeConversationId,
  onOpenConversation,
  onDeleteConversation,
}: ConversationHistoryPanelProps) {
  const [expandedDatasourceIds, setExpandedDatasourceIds] = useState<Set<string>>(() => new Set());

  return (
    <WorkspaceShell
      className="conversation-history"
      title="对话历史"
      showHeader={false}
      aria-label="对话历史"
      bodyClassName="conversation-history__body"
    >
      {conversations.length === 0 ? (
        <EmptyState
          title="暂无历史记录"
          description="提交问数后，会话会自动保存。"
        />
      ) : (
        <div className="conversation-history__groups">
          {groupConversations(conversations, datasourceLabels).map((group) => {
            const expanded = expandedDatasourceIds.has(group.datasourceId);
            const visibleConversations = getVisibleConversations(
              group.conversations,
              activeConversationId,
              expanded,
            );
            const hiddenCount = group.conversations.length - visibleConversations.length;

            return (
              <section className="conversation-history__group" key={group.datasourceId}>
              <div className="conversation-history__group-heading">
                <span className="conversation-history__group-icon" aria-hidden="true">
                  <Database size={15} />
                </span>
                <strong>{group.label}</strong>
                <span className="conversation-history__group-count">
                  {group.conversations.length} 个对话
                </span>
              </div>
              <div className="conversation-history__list">
                {visibleConversations.map((conversation) => {
                  const active = activeConversationId === conversation.id;
                  const details = formatDetails(conversation);
                  return (
                    <article
                      key={conversation.id}
                      className={cx(
                        "conversation-history__item",
                        active && "conversation-history__item--active",
                      )}
                    >
                      <button
                        type="button"
                        className="conversation-history__item-button"
                        aria-label={`打开 ${conversation.title}`}
                        aria-current={active ? "page" : undefined}
                        title={conversation.title}
                        onClick={() => onOpenConversation(conversation)}
                      >
                        <span className="conversation-history__item-icon" aria-hidden="true">
                          <MessageSquare size={14} />
                        </span>
                        <span className="conversation-history__copy">
                          <span className="conversation-history__title">{conversation.title}</span>
                          {details ? (
                            <span className="conversation-history__details">
                              {details}
                            </span>
                          ) : null}
                        </span>
                        <time
                          className="conversation-history__meta"
                          dateTime={isValidDate(conversation.updated_at) ? conversation.updated_at ?? undefined : undefined}
                        >
                          {formatTime(conversation.updated_at)}
                        </time>
                        <ChevronRight size={12} className="conversation-history__chevron" aria-hidden="true" />
                      </button>
                      <Button
                        className="conversation-history__delete"
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`删除 ${conversation.title}`}
                        title={`删除 ${conversation.title}`}
                        onClick={() => onDeleteConversation(conversation.id)}
                      >
                        <Trash2 size={14} aria-hidden="true" />
                      </Button>
                    </article>
                  );
                })}
                {group.conversations.length > DEFAULT_VISIBLE_CONVERSATIONS ? (
                  <button
                    type="button"
                    className="conversation-history__expand"
                    aria-expanded={expanded}
                    onClick={() => {
                      setExpandedDatasourceIds((current) => {
                        const next = new Set(current);
                        if (next.has(group.datasourceId)) next.delete(group.datasourceId);
                        else next.add(group.datasourceId);
                        return next;
                      });
                    }}
                  >
                    {expanded ? <ChevronUp size={14} aria-hidden="true" /> : <ChevronDown size={14} aria-hidden="true" />}
                    {expanded ? "收起" : `展开其余 ${hiddenCount} 个对话`}
                  </button>
                ) : null}
              </div>
              </section>
            );
          })}
        </div>
      )}
    </WorkspaceShell>
  );
}

function getVisibleConversations(
  conversations: ConversationSummary[],
  activeConversationId: string | undefined,
  expanded: boolean,
) {
  if (expanded || conversations.length <= DEFAULT_VISIBLE_CONVERSATIONS) return conversations;
  const visible = conversations.slice(0, DEFAULT_VISIBLE_CONVERSATIONS);
  const active = conversations.find((conversation) => conversation.id === activeConversationId);
  if (active && !visible.some((conversation) => conversation.id === active.id)) visible.push(active);
  return visible;
}

function groupConversations(
  conversations: ConversationSummary[],
  datasourceLabels: Record<string, string>,
) {
  const groups = new Map<string, { datasourceId: string; label: string; conversations: ConversationSummary[] }>();
  for (const conversation of conversations) {
    const datasourceId = conversation.datasource_id || "unassigned";
    const existing = groups.get(datasourceId);
    if (existing) {
      existing.conversations.push(conversation);
      continue;
    }
    groups.set(datasourceId, {
      datasourceId,
      label: datasourceLabels[datasourceId] || (datasourceId === "unassigned" ? "未关联数据源" : "已移除的数据源"),
      conversations: [conversation],
    });
  }
  return [...groups.values()];
}

function formatTime(value: string | null) {
  if (!value) return "未知时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "未知时间";
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "刚刚";
  if (diffMin < 60) return `${diffMin} 分钟前`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `${diffHours} 小时前`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays} 天前`;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function isValidDate(value: string | null) {
  return Boolean(value && !Number.isNaN(new Date(value).getTime()));
}

function formatDetails(conversation: ConversationSummary) {
  const details: string[] = [];
  if (conversation.message_count) details.push(`${conversation.message_count} 条消息`);
  if (conversation.artifact_count) details.push(`${conversation.artifact_count} 个工件`);

  const statusLabel = formatRunStatus(conversation.run_status);
  if (statusLabel) details.push(statusLabel);
  return details.join(" · ");
}

function formatRunStatus(status: ConversationSummary["run_status"]) {
  switch (status) {
    case "created":
    case "queued":
      return "等待运行";
    case "running":
    case "waiting_approval":
    case "waiting_input":
    case "cancelling":
      return "正在运行";
    case "failed":
      return "上次运行失败";
    case "cancelled":
      return "上次运行已取消";
    default:
      return "";
  }
}
